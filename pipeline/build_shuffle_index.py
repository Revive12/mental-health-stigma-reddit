#!/usr/bin/env python3
"""Build a deterministic, post-grouped index of eligible comment references.

Each TSV row contains: key, month, post_name, subreddit, comment_name,
tree_offset, post_offset. The 32-character MD5 key is shared by all comments
from a post. Only posts in the required externally prepared selection manifest are indexed.
This orders selected posts pseudorandomly; it does NOT implement
proportionate stratified sampling or guarantee subreddit/month quotas.
MD5 is used only for deterministic ordering, not security or anonymization.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import common

REPO = common.OUTPUT_ROOT
OUT_DIR = REPO / "stage_stigma_annotate"
STAGE4C = "stage4c_filter"
STAGE7 = "stage7_trees"
_POST_SEED = "stigma_postcluster_v1"


def discover_months() -> list[str]:
    """Find existing stage-7 month directories."""
    trees = REPO / STAGE7
    return sorted(p.name for p in trees.iterdir()
                  if p.is_dir() and len(p.name) == 7 and p.name[4] == "-") if trees.is_dir() else []


def process_month(month: str, repo=None, out_dir=None, seed=_POST_SEED, selected_posts=None):
    """Write references for one month; paths are explicit for spawn workers."""
    repo = Path(repo) if repo is not None else REPO
    out_dir = Path(out_dir) if out_dir is not None else OUT_DIR
    posts_file = repo / STAGE4C / month / "posts_prefiltered.jsonl"
    tree_file = repo / STAGE7 / month / "comment_trees.jsonl"
    sub_of, post_off = {}, {}
    with posts_file.open("rb") as f:
        off = 0
        for line in f:
            d = json.loads(line)
            nm = d.get("name")
            if not isinstance(nm, str) or not nm.startswith("t3_"):
                raise ValueError(f"Invalid post identifier at {posts_file}:{off}")
            if selected_posts is not None and nm not in selected_posts:
                off += len(line)
                continue
            if nm in post_off:
                raise ValueError(f"Duplicate post identifier: {nm}")
            sub_of[nm] = d.get("subreddit") or "UNKNOWN"
            post_off[nm] = off
            off += len(line)
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f".refs_{month}.tsv"
    n = 0
    indexed_posts = set()
    with tree_file.open("rb") as f, tmp.open("w", encoding="utf-8") as out:
        off = 0
        for line in f:
            d = json.loads(line)
            pnm = d.get("name")
            if selected_posts is not None and pnm not in selected_posts:
                off += len(line)
                continue
            if pnm not in post_off:
                raise ValueError(f"Tree {pnm!r} has no corresponding post record")
            indexed_posts.add(pnm)
            pkey = hashlib.md5((seed + pnm).encode()).hexdigest()
            stack, seen = list(d.get("comments", [])), set()
            while stack:
                c = stack.pop()
                cnm = c.get("name")
                if not isinstance(cnm, str) or not cnm.startswith("t1_"):
                    raise ValueError(f"Invalid comment identifier in {pnm}")
                if cnm in seen:
                    raise ValueError(f"Duplicate comment {cnm} in tree {pnm}")
                seen.add(cnm)
                fields = [pkey, month, pnm, sub_of[pnm], cnm, str(off), str(post_off[pnm])]
                if any("\t" in x or "\n" in x for x in fields):
                    raise ValueError("TSV fields must not contain tabs or newlines")
                out.write("\t".join(fields) + "\n")
                n += 1
                stack.extend(c.get("replies") or [])
            off += len(line)
    return month, n, set(post_off), indexed_posts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selected-posts", required=True, help="External sample manifest: one unique t3_ post ID per line; no header")
    ap.add_argument("--month", help="Process one YYYY-MM directory; otherwise process all discovered months")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", default=_POST_SEED, help="Deterministic post-ordering seed")
    ap.add_argument("--no-sort", action="store_true", help="Write reference parts only")
    ap.add_argument("--data-root", default=None, help="Data directory; default: MH_DATA_ROOT or ./data")
    args = ap.parse_args()
    if args.workers < 1:
        ap.error("--workers must be positive")
    common.set_data_root(args.data_root)
    global REPO, OUT_DIR
    REPO = common.OUTPUT_ROOT
    OUT_DIR = REPO / "stage_stigma_annotate"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    months = [args.month] if args.month else discover_months()
    if not months:
        ap.error("No stage7_trees month directories were found")
    selection_path = Path(args.selected_posts)
    selection_bytes = selection_path.read_bytes()
    selected = [line.strip() for line in selection_bytes.decode("utf-8").splitlines() if line.strip()]
    if not selected or len(selected) != len(set(selected)):
        ap.error("Selection manifest must contain nonempty, unique post IDs")
    if any(not item.startswith("t3_") or not item[3:].isalnum() for item in selected):
        ap.error("Every selected post ID must have t3_ followed by letters or digits")
    selected = set(selected)
    counts, found, indexed = {}, set(), set()
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(process_month, m, REPO, OUT_DIR, args.seed, selected) for m in months]
        for fut in as_completed(futs):
            month, n, found_month, indexed_month = fut.result()
            found.update(found_month)
            indexed.update(indexed_month)
            counts[month] = n
            print(f"[{month}] indexed {n:,} comments", flush=True)
    missing = selected - found
    if missing:
        raise ValueError(f"{len(missing)} selected posts are absent from the processed month files; check the manifest and --month")
    if args.no_sort:
        return
    # No shell interpolation: supports spaces and non-ASCII directory names.
    parts = [OUT_DIR / f".refs_{m}.tsv" for m in months]
    out_index = OUT_DIR / "shuffle_index.tsv"
    tmp_index = OUT_DIR / "shuffle_index.tsv.tmp"
    subprocess.run(["sort", "-o", str(tmp_index), *map(str, parts)],
                   env={**os.environ, "LC_ALL": "C"}, check=True)
    with tmp_index.open("rb") as f:
        lines = sum(1 for _ in f)
    if lines != sum(counts.values()):
        raise RuntimeError("Sorted index line count does not match emitted references")
    os.replace(tmp_index, out_index)
    manifest = {"schema_version": 1, "ordering": "post_grouped_md5",
                "selection": "external_manifest", "sampling_code_included": False, "seed": args.seed,
                "selected_posts_sha256": hashlib.sha256(selection_bytes).hexdigest(),
                "selected_post_count": len(selected), "indexed_post_count": len(indexed),
                "selected_without_tree_count": len(found - indexed),
                "comments_by_month": counts, "reference_count": lines,
                "note": "Sampling was performed upstream. This index only orders externally selected posts. Selected posts without retained trees have no comment references."}
    (OUT_DIR / "shuffle_index.manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for part in parts:
        part.unlink()
    print(f"Wrote {lines:,} references to {out_index}")


if __name__ == "__main__":
    main()
