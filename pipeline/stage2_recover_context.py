#!/usr/bin/env python3
"""Stage 2: recover context for the union of post and comment keyword hits.

Read stage1 matched records and the corresponding month's original RS/RC dumps.
Write matched_posts_final.jsonl, post_comments.jsonl and target post IDs under
stage2_recover/YYYY-MM/. This implementation reads only the same calendar
month: it does not recover later replies or submissions from earlier months.
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
from keyword_utils import normalize_post_id
from reddit_streams import iter_json_objects, write_json_line


def read_jsonl(path: Path):
    if not path.is_file():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                import json
                yield json.loads(line)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def collect_target_ids(stage1_dir: Path) -> tuple[set[str], set[str]]:
    """Read target post IDs and keyword-matched comment IDs from stage 1."""
    post_hit_ids: set[str] = set()
    for row in read_jsonl(stage1_dir / "matched_posts.jsonl"):
        pid = normalize_post_id(row.get("id"))
        if pid:
            post_hit_ids.add(pid)

    comment_hit_post_ids: set[str] = set()
    keyword_comment_ids: set[str] = set()
    for row in read_jsonl(stage1_dir / "matched_comments.jsonl"):
        pid = normalize_post_id(row.get("link_id"))
        if pid:
            comment_hit_post_ids.add(pid)
        cid = str(row.get("id", "")).strip()
        if cid:
            keyword_comment_ids.add(cid)

    target = post_hit_ids | comment_hit_post_ids
    return target, keyword_comment_ids


def write_ids(path: Path, ids: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in sorted({i for i in ids if i}):
            f.write(item + "\n")


def run_month(month: str) -> dict:
    stage1_dir = common.stage_dir(1, month)
    sub_path = common.submission_zst(month)
    com_path = common.comment_zst(month)
    out_dir = common.stage_dir(2, month)

    if not (stage1_dir / "matched_posts.jsonl").is_file():
        raise FileNotFoundError(f"Stage 1 posts output not found: {stage1_dir/'matched_posts.jsonl'}")

    for required in (stage1_dir / "matched_comments.jsonl", sub_path, com_path):
        if not required.is_file():
            raise FileNotFoundError(f"Required input not found: {required}")

    target_post_ids, keyword_comment_ids = collect_target_ids(stage1_dir)
    print(f"=== Stage 2 [{month}] ===")
    print(f"  Unique target posts: {len(target_post_ids)}")
    print(f"  Keyword-matched comments: {len(keyword_comment_ids)}")
    write_ids(out_dir / "matched_post_ids_final.txt", target_post_ids)

    if not target_post_ids and not keyword_comment_ids:
        print("  No targets; writing empty output.")
        for name in ("matched_posts_final.jsonl", "post_comments.jsonl"):
            (out_dir / name).write_text("")
        return {"month": month, "posts": 0, "comments": 0}

    started = datetime.now()

    # Recover target posts from the current submission dump.
    out_posts = out_dir / "matched_posts_final.jsonl"
    post_count = 0
    seen_post: set[str] = set()
    with open(out_posts, "w", encoding="utf-8") as out:
        for row in iter_json_objects(str(sub_path)):
            pid = normalize_post_id(row.get("id"))
            if pid not in target_post_ids:
                continue
            key = str(row.get("id", "")) or repr(sorted(row.items()))
            if key in seen_post:
                continue
            seen_post.add(key)
            write_json_line(out, row)
            post_count += 1
    print(f"  postsrecovered: {post_count} -> {out_posts}")

    # Recover matching comments from the current comment dump.
    out_comments = out_dir / "post_comments.jsonl"
    comment_count = 0
    seen_comment: set[str] = set()
    with open(out_comments, "w", encoding="utf-8") as out:
        for row in iter_json_objects(str(com_path)):
            pid = normalize_post_id(row.get("link_id"))
            cid = str(row.get("id", "")).strip()
            if pid not in target_post_ids and cid not in keyword_comment_ids:
                continue
            key = cid or repr(sorted(row.items()))
            if key in seen_comment:
                continue
            seen_comment.add(key)
            write_json_line(out, row)
            comment_count += 1
    print(f"  commentsrecovered: {comment_count} -> {out_comments}")

    duration = datetime.now() - started
    print(f"  Stage 2 [{month}] completed: elapsed {duration}")
    return {"month": month, "posts": post_count, "comments": comment_count}


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 2: Context recovery")
    parser.add_argument("--month", help="One YYYY-MM month; default: all downloaded months")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    months = common.resolve_months([args.month] if args.month else None)
    print(f"Stage 2 months to process ({len(months)}): {', '.join(months)}")
    results = [run_month(m) for m in months]

    print("=" * 60)
    for r in results:
        print(f"{r['month']}: posts={r['posts']}, comments={r['comments']}")


if __name__ == "__main__":
    main()
