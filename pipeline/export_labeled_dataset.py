#!/usr/bin/env python3
"""Export validated final A-H comment labels and prune disconnected branches.

Coarse H maps to final H; coarse I requires a valid fine A-H label. Missing or
invalid labels stop export instead of being interpreted as non-stigmatizing.
Source batch range is [lo, hi). Output replaces the destination only on success.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import json
import os
from pathlib import Path
import tempfile

import common

DATA = common.OUTPUT_ROOT / "stage_stigma_annotate"
LABELS = set("ABCDEFGH")


def load_corrections(data):
    fixes = {}
    path = Path(data) / "err_reannotated.jsonl"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                lab = row.get("new_output", {}).get("label")
                if lab in {"H", "I"}:
                    fixes[row["comment_name"]] = lab
    return fixes


def load_fine_labels(data):
    fine = {}
    path = Path(data) / "finelabel_output.jsonl"
    if path.is_file():
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                lab = row.get("finelabel", {}).get("label")
                if lab in LABELS:
                    fine[row["comment_name"]] = lab
    return fine


def resolve_label(row, fine, fixes):
    name = row["comment_name"]
    coarse = row.get("output", {}).get("label")
    if coarse not in {"H", "I"}:
        coarse = fixes.get(name, coarse)
    if coarse not in {"H", "I"}:
        raise ValueError(f"Unresolved coarse annotation for {name}: {coarse!r}")
    fl = fine.get(name) if coarse == "I" else None
    if coarse == "I" and fl not in LABELS:
        raise ValueError(f"Missing valid fine annotation for coarse-I comment {name}")
    return coarse, fl, fl if coarse == "I" else "H"


def export(data, lo, hi, out):
    data, out = Path(data), Path(out)
    if not 0 <= lo < hi:
        raise ValueError("Require 0 <= lo < hi")
    fine, fixes = load_fine_labels(data), load_corrections(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=out.parent,
                                         prefix=out.name + ".", suffix=".tmp", delete=False)
    tmp = Path(handle.name)
    locations, parents, children = {}, {}, {}
    try:
        with handle as f:
            for bn in range(lo, hi):
                with (data / f"batches/batch_{bn:06d}.jsonl").open(encoding="utf-8") as source:
                    for line in source:
                        row = json.loads(line)
                        coarse, fl, label = resolve_label(row, fine, fixes)
                        name = row["comment_name"]
                        if name in locations:
                            raise ValueError(f"Duplicate comment in selected batches: {name}")
                        tc, ctx, post = (row["input"][key] for key in ("target_comment", "context_chain", "post_data"))
                        post_name, pid = post.get("name"), tc.get("parent_id")
                        if not isinstance(post_name, str) or not post_name.startswith("t3_"):
                            raise ValueError(f"Invalid post identifier for {name}")
                        locations[name], parents[name] = post_name, pid
                        children.setdefault(pid, []).append(name)
                        f.write(json.dumps({
                            "comment_name": name, "post_name": post_name,
                            "subreddit": row.get("subreddit"), "month": row.get("month"),
                            "body": tc.get("body"), "score": tc.get("score"),
                            "created_utc": tc.get("created_utc"), "author_fullname": tc.get("author_fullname"),
                            "depth": len(ctx) + 1, "parent_id": pid,
                            "post_author_fullname": post.get("author_fullname"),
                            "coarse": coarse, "fine": fl, "label": label,
                        }, ensure_ascii=False) + "\n")
        # Reachability excludes missing parents, cross-post edges, and cycles.
        reachable = set()
        queue = deque(name for name, pid in parents.items() if pid == locations[name])
        while queue:
            name = queue.popleft()
            if name in reachable:
                continue
            reachable.add(name)
            queue.extend(child for child in children.get(name, ())
                         if locations[child] == locations[name])
        counts = Counter()
        clean = tmp.with_suffix(".clean.tmp")
        try:
            with tmp.open(encoding="utf-8") as source, clean.open("w", encoding="utf-8") as target:
                for line in source:
                    row = json.loads(line)
                    if row["comment_name"] in reachable:
                        target.write(line)
                        counts[row["label"]] += 1
            os.replace(clean, out)
        finally:
            clean.unlink(missing_ok=True)
        n, removed = sum(counts.values()), len(locations) - len(reachable)
        ag = sum(counts[k] for k in "ABCDEFG")
        print(f"Exported {n:,} comments to {out}; pruned {removed:,} disconnected comments")
        print(f"Final labels: {dict(sorted(counts.items()))}")
        print(f"A-G: {ag:,} ({100 * ag / n if n else 0:.2f}%)")
        return {"comments": n, "pruned": removed, "labels": dict(counts)}
    finally:
        tmp.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lo", type=int, default=0, help="First coarse batch, inclusive")
    ap.add_argument("--hi", type=int, required=True, help="Last coarse batch, exclusive")
    ap.add_argument("--out", default=None)
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--data-root", default=None, help="Data directory; default: MH_DATA_ROOT or ./data")
    args = ap.parse_args()
    common.set_data_root(args.data_root)
    data = common.OUTPUT_ROOT / "stage_stigma_annotate"
    out = Path(args.out) if args.out else Path(args.out_dir) / f"labeled_flat_b{args.lo}_{args.hi-1}.jsonl"
    export(data, args.lo, args.hi, out)


if __name__ == "__main__":
    main()
