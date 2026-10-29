#!/usr/bin/env python3
"""Stage 6: match comments to retained posts and exclude predicted AI content.

Read stage4c posts_prefiltered.jsonl and stage5 comments_bot_labeled.jsonl.
Retain comments whose link_id matches a retained post and whose
slop_detection.is_ai_generated is false. Write stage6_clean/YYYY-MM/
comments_cleaned.jsonl and cleaning_metadata.json.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import common


def run_month(month: str) -> dict:
    posts_path = common.stage_dir("4c", month) / "posts_prefiltered.jsonl"
    comments_path = common.stage_dir(5, month) / "comments_bot_labeled.jsonl"
    out_path = common.stage_dir(6, month) / "comments_cleaned.jsonl"
    meta_path = common.stage_dir(6, month) / "cleaning_metadata.json"

    if not posts_path.is_file():
        raise FileNotFoundError(f"Stage 4 posts file not found: {posts_path}")
    if not comments_path.is_file():
        raise FileNotFoundError(f"Stage 5 comments file not found: {comments_path}")

    # Collect retained post identifiers.
    post_names: set[str] = set()
    for row in common.iter_jsonl_bytes(posts_path):
        name = row.get("name")
        if name:
            post_names.add(name)
    print(f"  [{month}] Target post IDs: {len(post_names):,}")

    tmp = out_path.with_name(f".{out_path.name}.tmp.{os.getpid()}")
    common.remove_if_exists(tmp)
    total = matched = removed_ai = kept = 0
    started = time.monotonic()

    try:
        with comments_path.open("rb", buffering=common.BUFFER_SIZE) as fin,\
             tmp.open("wb", buffering=common.BUFFER_SIZE) as fout:
            for row in common.iter_jsonl_bytes(comments_path):
                total += 1
                if total % 1_000_000 == 0:
                    print(f"    [{month}] scanned {total:,}", flush=True)

                detection = row.get("slop_detection")
                if not isinstance(detection, dict):
                    raise ValueError(f"Row {total} comment is missing slop_detection")
                is_ai = detection.get("is_ai_generated")
                if not isinstance(is_ai, bool):
                    raise ValueError(f"Row {total} comment has an invalid AI detection label")

                if row.get("link_id") not in post_names:
                    continue
                matched += 1
                if is_ai:
                    removed_ai += 1
                    continue

                fout.write(common.json_dumps_bytes(row))
                fout.write(b"\n")
                kept += 1
        os.replace(tmp, out_path)
    except BaseException:
        common.remove_if_exists(tmp)
        raise

    elapsed = time.monotonic() - started
    meta = {
        "status": "completed",
        "stage": 6,
        "month": month,
        "completed_at": common.utc_now(),
        "posts_input": common.file_signature(posts_path),
        "comments_input": common.file_signature(comments_path),
        "output_bytes": out_path.stat().st_size,
        "target_post_count": len(post_names),
        "input_comments": total,
        "matched_comments": matched,
        "removed_ai_comments": removed_ai,
        "kept_comments": kept,
        "elapsed_seconds": round(elapsed, 3),
    }
    common.atomic_write_json(meta_path, meta)
    print(
        f"  Stage 6 [{month}]: comments {total:,} -> matched {matched:,} "
        f"-> excluded AI {removed_ai:,} -> retained {kept:,} ({elapsed:.1f}s)"
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 6: Match comments and exclude predicted AI content")
    parser.add_argument("--month", help="One YYYY-MM month; default: all downloaded months")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    months = common.resolve_months([args.month] if args.month else None)
    print(f"Stage 6 months to process ({len(months)}): {', '.join(months)}")
    for m in months:
        run_month(m)


if __name__ == "__main__":
    main()
