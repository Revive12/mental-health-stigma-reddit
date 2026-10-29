#!/usr/bin/env python3
"""Stage 3: retain posts with at least ten whitespace-delimited words.

Count words across title and selftext and require a nonempty name identifier.
Read stage2_recover/YYYY-MM/matched_posts_final.jsonl and write
stage3_length/YYYY-MM/posts_length_filtered.jsonl and metadata.
No is_self restriction is applied; link posts with sufficient text can remain.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import common

WORD_RE = re.compile(r"\S+")
WORD_THRESHOLD = 10


def word_count(text) -> int:
    if not isinstance(text, str) or not text:
        return 0
    return len(WORD_RE.findall(text))


def run_month(month: str, threshold: int = WORD_THRESHOLD) -> dict:
    if threshold < 1:
        raise ValueError("Word threshold must be positive")
    in_path = common.stage_dir(2, month) / "matched_posts_final.jsonl"
    out_path = common.stage_dir(3, month) / "posts_length_filtered.jsonl"
    meta_path = common.stage_dir(3, month) / "length_filter_metadata.json"
    if not in_path.is_file():
        raise FileNotFoundError(f"Stage 2 posts file not found: {in_path}")

    tmp = out_path.with_name(f".{out_path.name}.tmp.{os.getpid()}")
    common.remove_if_exists(tmp)

    total = kept = dropped_short = dropped_no_name = 0
    started = time.monotonic()
    try:
        with in_path.open("rb", buffering=common.BUFFER_SIZE) as fin,\
             tmp.open("wb", buffering=common.BUFFER_SIZE) as fout:
            for line in fin:
                if not line.strip():
                    continue
                total += 1
                row = common.json_loads_bytes(line)
                title = row.get("title")
                title = title if isinstance(title, str) else ""
                body = row.get("selftext")
                body = body if isinstance(body, str) else ""

                if word_count(title) + word_count(body) < threshold:
                    dropped_short += 1
                    continue
                if not row.get("name"):
                    dropped_no_name += 1
                    continue

                fout.write(common.json_dumps_bytes(row))
                fout.write(b"\n")
                kept += 1
        os.replace(tmp, out_path)
    except BaseException:
        common.remove_if_exists(tmp)
        raise

    meta = {
        "status": "completed",
        "stage": 3,
        "month": month,
        "completed_at": common.utc_now(),
        "word_threshold": threshold,
        "word_regex": r"\S+",
        "text_fields": ["title", "selftext"],
        "input": common.file_signature(in_path),
        "output_bytes": out_path.stat().st_size,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "input_posts": total,
        "kept_posts": kept,
        "dropped_short": dropped_short,
        "dropped_no_name": dropped_no_name,
    }
    common.atomic_write_json(meta_path, meta)
    print(
        f"  Stage 3 [{month}]: input {total} retained {kept} "
        f"(short {dropped_short}, missing name {dropped_no_name})"
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 3: Post length filter")
    parser.add_argument("--month", help="One YYYY-MM month; default: all downloaded months")
    parser.add_argument(
        "--threshold", type=int, default=WORD_THRESHOLD,
        help=f"Minimum title+selftext word count (default: {WORD_THRESHOLD})",
    )
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    months = common.resolve_months([args.month] if args.month else None)
    print(f"Stage 3 months to process ({len(months)}): {', '.join(months)}")
    for m in months:
        run_month(m, args.threshold)


if __name__ == "__main__":
    main()
