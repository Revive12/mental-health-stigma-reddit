"""Stage 4c: optional stricter placeholder and bot prefilter before stage 5.

Remove posts with exact [removed]/[deleted] selftext and their comments.
Remove comments with exact placeholder bodies or bot-like author names,
along with all descendant comments. This changes historical bot-descendant
handling and is not an exact replay of filtering performed during annotation.
The rules do not establish that all remaining content is human-authored.

Inputs: stage4_top16/YYYY-MM/{posts_top16,comments_top16}.jsonl.
Outputs: stage4c_filter/YYYY-MM/{posts_prefiltered,comments_prefiltered}.jsonl
and prefilter_metadata.json. Inputs remain unchanged.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
sys.path.insert(0, str(_HERE / "lib"))

import common  # noqa: E402

PLACEHOLDERS = {"[removed]", "[deleted]"}
# Heuristic bot author names, including AutoModerator.
_AUTHOR_BOT = re.compile(r"automoderator|(^|[_\-.])bot($|[_\-.])|_bot$|^bot$", re.I)


def is_placeholder(text) -> bool:
    return isinstance(text, str) and text.strip() in PLACEHOLDERS


def is_bot_author(author) -> bool:
    return isinstance(author, str) and bool(_AUTHOR_BOT.search(author))


def process_month(month: str) -> dict:
    posts_in = common.stage_dir(4, month) / "posts_top16.jsonl"
    comments_in = common.stage_dir(4, month) / "comments_top16.jsonl"
    for required in (posts_in, comments_in):
        if not required.is_file():
            raise FileNotFoundError(f"Required input not found: {required}")
    out_dir = common.stage_dir("4c", month)
    posts_out = out_dir / "posts_prefiltered.jsonl"
    comments_out = out_dir / "comments_prefiltered.jsonl"

    stats = {
        "stage": "4c", "month": month, "status": "completed",
        "posts_input": 0, "posts_kept": 0,
        "posts_dropped_placeholder": 0,
        "comments_input": 0, "comments_kept": 0,
        "comments_dropped_post_placeholder": 0,
        "comments_dropped_placeholder": 0,
        "comments_dropped_bot": 0,
        "comments_dropped_descendant": 0,
    }

    # Pass 1: filter posts.
    placeholder_post_ids: set[str] = set()
    with posts_in.open("rb", buffering=common.BUFFER_SIZE) as fin,\
            posts_out.open("wb") as fout:
        for row in common.iter_jsonl_bytes(posts_in):
            stats["posts_input"] += 1
            if is_placeholder(row.get("selftext")):
                stats["posts_dropped_placeholder"] += 1
                pid = row.get("name")
                if pid:
                    placeholder_post_ids.add(pid)
                continue
            fout.write(common.json_dumps_bytes(row) + b"\n")
            stats["posts_kept"] += 1

    # Pass 2a: identify comments to exclude.
    # Propagate post-placeholder, body-placeholder and bot exclusions to descendants.
    children: dict[str, list[str]] = {}
    dropped: dict[str, str] = {}   # Comment name -> exclusion reason (post_ph, placeholder or bot).
    n_in = 0
    for row in common.iter_jsonl_bytes(comments_in):
        n_in += 1
        name = row.get("name") or (f"t1_{row['id']}" if row.get("id") else "")
        if not name:
            raise ValueError("Comment is missing both name and id")
        parent = row.get("parent_id") or ""
        if parent:
            children.setdefault(parent, []).append(name)
        if row.get("link_id") in placeholder_post_ids:
            dropped[name] = "post_ph"
        elif is_placeholder(row.get("body")):
            dropped[name] = "placeholder"
        elif is_bot_author(row.get("author")):
            dropped[name] = "bot"
    stats["comments_input"] = n_in

    # Compute the descendant closure.
    stack = list(dropped)
    while stack:
        cur = stack.pop()
        for child in children.get(cur, ()):
            if child not in dropped:
                dropped[child] = "descendant"
                stack.append(child)

    # Pass 2b: write retained comments.
    with comments_in.open("rb", buffering=common.BUFFER_SIZE) as fin,\
            comments_out.open("wb") as fout:
        for row in common.iter_jsonl_bytes(comments_in):
            name = row.get("name") or (f"t1_{row['id']}" if row.get("id") else "")
            reason = dropped.get(name)
            if reason is None:
                fout.write(common.json_dumps_bytes(row) + b"\n")
                stats["comments_kept"] += 1
            elif reason == "post_ph":
                stats["comments_dropped_post_placeholder"] += 1
            elif reason == "placeholder":
                stats["comments_dropped_placeholder"] += 1
            elif reason == "bot":
                stats["comments_dropped_bot"] += 1
            else:
                stats["comments_dropped_descendant"] += 1

    stats["completed_at"] = common.utc_now()
    stats["posts_input_signature"] = common.file_signature(posts_in)
    stats["comments_input_signature"] = common.file_signature(comments_in)
    common.atomic_write_json(out_dir / "prefilter_metadata.json", stats)
    return stats


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Stage 4c: Placeholder/bot prefilter (before stage 5)")
    parser.add_argument("--month", help="One YYYY-MM month; default: all stage 4 months")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    if args.month:
        months = [args.month]
    else:
        base = common.OUTPUT_ROOT / "stage4_top16"
        months = sorted(p.name for p in base.iterdir()
                        if p.is_dir() and common.MONTH_RE.fullmatch(p.name))
    for month in months:
        stats = process_month(month)
        print(f"[{month}] posts {stats['posts_input']:,}→{stats['posts_kept']:,} "
              f"(placeholders {stats['posts_dropped_placeholder']:,}) | "
              f"comments {stats['comments_input']:,}→{stats['comments_kept']:,} "
              f"(post placeholders {stats['comments_dropped_post_placeholder']:,}, "
              f"placeholders {stats['comments_dropped_placeholder']:,}, "
              f"bot {stats['comments_dropped_bot']:,}, "
              f"descendants {stats['comments_dropped_descendant']:,})", flush=True)


if __name__ == "__main__":
    main()
