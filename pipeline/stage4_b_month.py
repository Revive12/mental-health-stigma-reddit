#!/usr/bin/env python3
"""Filter one month using the existing stage 4 subreddit selection.

Requires stage4_top16/top16_subreddits.json produced by the main stage 4 script.
Run independent months in parallel after the global subreddit counts exist.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import common


def normalize_sub(value) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 4b: filter one month using the global subreddit list")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)
    month = args.month

    # Read the global subreddit selection from stage 4.
    top_meta_path = common.stage_dir(4) / "top16_subreddits.json"
    if not top_meta_path.is_file():
        raise SystemExit(
            f"top16_subreddits.json not found: {top_meta_path}; run stage 4 global counting first"
        )
    top_meta = json.loads(top_meta_path.read_text(encoding="utf-8"))
    top = top_meta["top_subreddits"]
    top_set = {s.lower() for s in top}
    num = top_meta.get("num", len(top))

    month_started = time.monotonic()
    in_posts = common.stage_dir(3, month) / "posts_length_filtered.jsonl"
    in_comments = common.stage_dir(2, month) / "post_comments.jsonl"
    out_dir = common.stage_dir(4, month)
    out_posts = out_dir / "posts_top16.jsonl"
    out_comments = out_dir / "comments_top16.jsonl"

    for required in (in_posts, in_comments):
        if not required.is_file():
            raise FileNotFoundError(f"Required input not found: {required}")

    # Retain selected subreddits and collect post identifiers.
    post_names: set[str] = set()
    kept_posts = 0
    tmp_p = out_posts.with_name(f".{out_posts.name}.tmp.{os.getpid()}")
    common.remove_if_exists(tmp_p)
    try:
        with in_posts.open("rb", buffering=common.BUFFER_SIZE) as fin,\
             tmp_p.open("wb", buffering=common.BUFFER_SIZE) as fout:
            for row in common.iter_jsonl_bytes(in_posts):
                if normalize_sub(row.get("subreddit")) not in top_set:
                    continue
                name = row.get("name")
                if name:
                    post_names.add(name)
                fout.write(common.json_dumps_bytes(row))
                fout.write(b"\n")
                kept_posts += 1
        os.replace(tmp_p, out_posts)
    except BaseException:
        common.remove_if_exists(tmp_p)
        raise

    # Scan stage 2 comments and match them to retained posts.
    kept_comments = 0
    scanned_comments = 0
    tmp_c = out_comments.with_name(f".{out_comments.name}.tmp.{os.getpid()}")
    common.remove_if_exists(tmp_c)
    if in_comments.is_file():
        try:
            with in_comments.open("rb", buffering=common.BUFFER_SIZE) as fin,\
                 tmp_c.open("wb", buffering=common.BUFFER_SIZE) as fout:
                for row in common.iter_jsonl_bytes(in_comments):
                    scanned_comments += 1
                    if scanned_comments % 5_000_000 == 0:
                        print(f"    [{month}] scanned {scanned_comments:,} comments...", flush=True)
                    if row.get("link_id") in post_names:
                        fout.write(common.json_dumps_bytes(row))
                        fout.write(b"\n")
                        kept_comments += 1
            os.replace(tmp_c, out_comments)
        except BaseException:
            common.remove_if_exists(tmp_c)
            raise
    else:
        out_comments.write_text("")

    elapsed = time.monotonic() - month_started
    meta = {
        "status": "completed",
        "stage": 4,
        "month": month,
        "num": num,
        "top_subreddits": top,
        "completed_at": common.utc_now(),
        "posts_input": common.file_signature(in_posts),
        "comments_input": (
            common.file_signature(in_comments) if in_comments.is_file() else None
        ),
        "kept_posts": kept_posts,
        "scanned_comments": scanned_comments,
        "kept_comments": kept_comments,
        "elapsed_seconds": round(elapsed, 3),
    }
    common.atomic_write_json(out_dir / "top16_filter_metadata.json", meta)
    print(
        f"[{month}] posts {kept_posts:,}, comments {kept_comments:,}/{scanned_comments:,} "
        f"({elapsed:.1f}s)",
        flush=True,
    )


if __name__ == "__main__":
    main()
