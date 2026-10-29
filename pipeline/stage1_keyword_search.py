#!/usr/bin/env python3
"""Stage 1: retrieve posts and comments using 30 mental-health keywords.

Search title/selftext for posts and body for comments using a combined regex.
Read monthly RS/RC Zstandard dumps and write matched_posts.jsonl,
matched_comments.jsonl and their associated post ID lists under
pipeline_data/stage1_keywords/YYYY-MM/. Source records are not modified.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

import common
from keyword_utils import (
    COMMENT_SEARCH_FIELDS,
    MENTAL_HEALTH_KEYWORDS,
    POST_SEARCH_FIELDS,
    any_keyword_in_row,
    compile_combined_pattern,
    normalize_post_id,
)
from reddit_streams import iter_file_paths, iter_json_objects, write_json_line


def process_one(
    input_path: Path,
    output_path: Path,
    search_fields,
    combined_pattern,
    kind: str,
) -> tuple[int, set[str]]:
    """Write deduplicated keyword matches and return count and associated post IDs."""
    print(f"[{kind}] Scanning: {input_path}")
    matched_count = 0
    seen: set[str] = set()
    linked_post_ids: set[str] = set()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as out:
        for file_path in iter_file_paths(str(input_path), recursive=False):
            file_matched = 0
            for row in iter_json_objects(file_path):
                if not any_keyword_in_row(row, search_fields, combined_pattern):
                    continue
                row_id = row.get("id")
                key = str(row_id) if row_id else repr(sorted(row.items()))
                if key in seen:
                    continue
                seen.add(key)
                write_json_line(out, row)
                matched_count += 1
                file_matched += 1
                if kind == "comments":
                    linked_post_ids.add(normalize_post_id(row.get("link_id")))
                else:
                    linked_post_ids.add(normalize_post_id(row.get("id")))
            print(f"  {file_path}: matches {file_matched}")
    return matched_count, linked_post_ids


def write_ids(path: Path, ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in sorted({i for i in ids if i}):
            f.write(item + "\n")


def run_month(month: str, mode: str = "both") -> dict:
    sub_path = common.submission_zst(month)
    com_path = common.comment_zst(month)
    out_dir = common.stage_dir(1, month)

    combined_pattern = compile_combined_pattern(MENTAL_HEALTH_KEYWORDS)
    print(f"=== Stage 1 [{month}] keyword count={len(MENTAL_HEALTH_KEYWORDS)} (combined regex) ===")
    print(f"  post fields {POST_SEARCH_FIELDS} | comment fields {COMMENT_SEARCH_FIELDS}")

    started = datetime.now()
    post_n = com_n = 0

    if mode in {"both", "posts"}:
        if not sub_path.is_file():
            raise FileNotFoundError(f"Raw submissions file not found: {sub_path}")
        out_posts = out_dir / "matched_posts.jsonl"
        post_n, post_ids = process_one(
            sub_path, out_posts, POST_SEARCH_FIELDS, combined_pattern, "posts"
        )
        write_ids(out_dir / "matched_post_ids.txt", post_ids)
        print(f"  postsmatches {post_n} -> {out_posts}")

    if mode in {"both", "comments"}:
        if not com_path.is_file():
            raise FileNotFoundError(f"Raw comments file not found: {com_path}")
        out_comments = out_dir / "matched_comments.jsonl"
        com_n, com_post_ids = process_one(
            com_path, out_comments, COMMENT_SEARCH_FIELDS, combined_pattern, "comments"
        )
        write_ids(out_dir / "matched_comment_post_ids.txt", com_post_ids)
        print(f"  commentsmatches {com_n} -> {out_comments}")

    duration = datetime.now() - started
    print(f"  Stage 1 [{month}] completed: total matches {post_n + com_n}, elapsed {duration}")
    return {"month": month, "posts": post_n, "comments": com_n}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 1: Keyword retrieval")
    parser.add_argument("--month", help="One YYYY-MM month; default: all downloaded months")
    parser.add_argument(
        "--mode", choices=("both", "posts", "comments"), default="both"
    )
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    months = common.resolve_months([args.month] if args.month else None)
    print(f"Stage 1 months to process ({len(months)}): {', '.join(months)}")
    results = [run_month(m, args.mode) for m in months]

    print("=" * 60)
    for r in results:
        print(f"{r['month']}: posts={r['posts']}, comments={r['comments']}")


if __name__ == "__main__":
    main()
