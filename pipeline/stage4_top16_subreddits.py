#!/usr/bin/env python3
"""Stage 4: select the top N subreddits by post count across requested months.

Require stage 2 and stage 3 for every requested month. Count the top-level
subreddit field, save top16_subreddits.json, and retain posts and their linked
comments in posts_top16.jsonl and comments_top16.jsonl per month.
The output filenames retain the historical top16 convention for any N.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections import Counter
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import common

DEFAULT_NUM = 16


def normalize_sub(value) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def run(months: list[str], num: int) -> None:
    if num < 1:
        raise ValueError("Number of subreddits must be positive")
    if not months:
        raise ValueError("No input months were specified or discovered")
    for month in months:
        for required in (
            common.stage_dir(3, month) / "posts_length_filtered.jsonl",
            common.stage_dir(2, month) / "post_comments.jsonl",
        ):
            if not required.is_file():
                raise FileNotFoundError(f"Required input not found: {required}")
    print(f"=== Stage 4: top{num} subreddit ===")
    print(f"months to aggregate ({len(months)}): {', '.join(months)}")

    # Count subreddit posts across months.
    counter: Counter[str] = Counter()
    counted_months: list[str] = []
    missing: list[str] = []
    started = time.monotonic()
    for m in months:
        posts_path = common.stage_dir(3, m) / "posts_length_filtered.jsonl"
        if not posts_path.is_file():
            missing.append(m)
            continue
        counted_months.append(m)
        for row in common.iter_jsonl_bytes(posts_path):
            subreddit = normalize_sub(row.get("subreddit"))
            if subreddit:
                counter[subreddit] += 1

    if missing:
        print(f"  WARNING: missing stage 3 months skipped: {missing}")
    if not counted_months:
        raise SystemExit("No stage 3 data are available for aggregation")

    top = [sub for sub, _ in counter.most_common(num)]
    top_set = {sub.lower() for sub in top}
    print(f"  counting elapsed {time.monotonic() - started:.1f}s, distinct subreddits {len(counter)}")
    print(f"  top{num}: {top}")

    top_meta = {
        "status": "completed",
        "stage": 4,
        "completed_at": common.utc_now(),
        "num": num,
        "months_counted": counted_months,
        "months_missing": missing,
        "subreddit_post_counts": dict(counter.most_common()),
        "top_subreddits": top,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }
    common.atomic_write_json(common.stage_dir(4) / "top16_subreddits.json", top_meta)

    # Filter each month.
    for m in months:
        month_started = time.monotonic()
        in_posts = common.stage_dir(3, m) / "posts_length_filtered.jsonl"
        in_comments = common.stage_dir(2, m) / "post_comments.jsonl"
        out_dir = common.stage_dir(4, m)
        out_posts = out_dir / "posts_top16.jsonl"
        out_comments = out_dir / "comments_top16.jsonl"

        if not in_posts.is_file():
            print(f"  [{m}] skipping: missing {in_posts}")
            continue

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

        # Match comment link_id to retained posts in this month.
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
                        if row.get("link_id") in post_names:
                            fout.write(common.json_dumps_bytes(row))
                            fout.write(b"\n")
                            kept_comments += 1
                os.replace(tmp_c, out_comments)
            except BaseException:
                common.remove_if_exists(tmp_c)
                raise
        else:
            print(f"  [{m}] WARNING: missing stage 2 comments file {in_comments}; writing empty comment output")
            out_comments.write_text("")

        meta = {
            "status": "completed",
            "stage": 4,
            "month": m,
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
            "elapsed_seconds": round(time.monotonic() - month_started, 3),
        }
        common.atomic_write_json(out_dir / "top16_filter_metadata.json", meta)
        print(
            f"  [{m}] posts {kept_posts}, comments {kept_comments}/{scanned_comments} "
            f"({time.monotonic() - month_started:.1f}s)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 4: top-N subreddit selection")
    parser.add_argument("--month", nargs="*", help="Requested months; default: all downloaded months")
    parser.add_argument("--num", type=int, default=DEFAULT_NUM,
                        help=f"Number of top subreddits (default: {DEFAULT_NUM})")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    months = common.resolve_months(args.month)
    run(months, args.num)


if __name__ == "__main__":
    main()
