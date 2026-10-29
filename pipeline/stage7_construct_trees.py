#!/usr/bin/env python3
"""Stage 7: reconstruct reply trees within each monthly input partition.

Read stage4c posts_prefiltered.jsonl and stage6 comments_cleaned.jsonl.
Write stage7_trees/YYYY-MM/comment_trees.jsonl for connected trees,
orphan_comments.jsonl for disconnected branches, and trees_metadata.json.
Orphan branches are retained separately and excluded from annotation.
No cross-month recovery is performed by this stage.
"""
from __future__ import annotations

import argparse
import json as json_std
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import common
try:
    import orjson
except ImportError:
    orjson = None

sys.setrecursionlimit(10000)


def load_post_ids(file_path: Path) -> list[str]:
    """Return deduplicated t3_ post identifiers in input order."""
    post_ids: list[str] = []
    seen: set[str] = set()
    for row in common.iter_jsonl_bytes(file_path):
        post_id = row.get("name") or row.get("id")
        if not post_id:
            continue
        if not post_id.startswith("t3_"):
            post_id = f"t3_{post_id}"
        if post_id not in seen:
            seen.add(post_id)
            post_ids.append(post_id)
    return post_ids


def collect_reachable_ids(roots) -> set[str]:
    """Collect every comment identifier reachable from the supplied roots."""
    reachable: set[str] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        cid = node["name"]
        if cid in reachable:
            continue
        reachable.add(cid)
        stack.extend(node["replies"])
    return reachable


def build_comment_trees(file_path: Path, target_post_ids: list[str]):
    """Return connected trees, orphan trees and counts for target posts."""
    target_link_ids = set(target_post_ids)
    post_trees: dict[str, list] = {pid: [] for pid in target_post_ids}
    orphan_trees: dict[str, list] = {pid: [] for pid in target_post_ids}
    comment_map: dict[str, dict] = {}
    stats = {
        "input_comments": 0,
        "matched_comments": 0,
        "comments_without_id": 0,
        "root_comments": 0,
        "nested_comments": 0,
        "direct_orphan_comments": 0,
    }

    for row in common.iter_jsonl_bytes(file_path):
        stats["input_comments"] += 1
        link_id = row.get("link_id")
        if link_id not in target_link_ids:
            continue
        stats["matched_comments"] += 1

        comment_id = row.get("name")
        if not comment_id and row.get("id"):
            comment_id = f"t1_{row['id']}"
        if not comment_id:
            stats["comments_without_id"] += 1
            continue

        if comment_id in comment_map:
            raise ValueError(f"Duplicate comment identifier: {comment_id}")
        comment_map[comment_id] = {
            "name": comment_id,
            "author": row.get("author"),
            "author_fullname": row.get("author_fullname"),
            "body": row.get("body"),
            "score": row.get("score"),
            "created_utc": row.get("created_utc"),
            "parent_id": row.get("parent_id"),
            "link_id": link_id,
            "replies": [],
        }

    # Fail on cycles instead of silently losing nodes or serializing recursion.
    checked: set[str] = set()
    for start in comment_map:
        trail: set[str] = set()
        current = start
        while current in comment_map and current not in checked:
            if current in trail:
                raise ValueError(f"Cycle in reply relationships at {current}")
            trail.add(current)
            current = comment_map[current]["parent_id"]
        checked.update(trail)

    # Attach nodes to their post or parent, or mark them as orphans.
    for node in comment_map.values():
        parent_id = node["parent_id"]
        link_id = node["link_id"]

        if isinstance(parent_id, str) and parent_id == link_id:
            # Top-level comments attached directly to their own post.
            post_trees[link_id].append(node)
            stats["root_comments"] += 1
        elif (
            isinstance(parent_id, str)
            and parent_id in comment_map
            and comment_map[parent_id]["link_id"] == link_id
        ):
            # A parent comment exists in the same discussion.
            comment_map[parent_id]["replies"].append(node)
            stats["nested_comments"] += 1
        else:
            # A missing or cross-post parent creates an orphan branch.
            node["is_orphan"] = True
            node["missing_parent_id"] = parent_id
            orphan_trees[link_id].append(node)
            stats["direct_orphan_comments"] += 1

    normal_ids = collect_reachable_ids(
        r for roots in post_trees.values() for r in roots
    )
    orphan_ids = collect_reachable_ids(
        r for roots in orphan_trees.values() for r in roots
    )
    stats["unique_comments"] = len(comment_map)
    stats["normal_tree_comments"] = len(normal_ids)
    stats["orphan_branch_comments"] = len(orphan_ids - normal_ids)
    stats["preserved_comments"] = len(normal_ids | orphan_ids)
    stats["posts_with_comments"] = sum(bool(r) for r in post_trees.values())
    stats["posts_with_orphans"] = sum(bool(r) for r in orphan_trees.values())
    return post_trees, orphan_trees, stats


def save_trees(file_path: Path, trees: dict, key: str) -> int:
    """Write one JSONL record per nonempty tree and return the record count."""
    tmp = file_path.with_name(f".{file_path.name}.tmp.{os.getpid()}")
    common.remove_if_exists(tmp)
    written = 0
    try:
        with tmp.open("wb") as f:
            for post_id, comments in trees.items():
                if not comments:
                    continue
                item = {"name": post_id, key: comments}
                try:
                    if orjson is None:
                        payload = json_std.dumps(item, ensure_ascii=False).encode("utf-8")
                    else:
                        payload = orjson.dumps(item)
                except TypeError:
                    # Fall back to standard-library JSON for deeply nested trees.
                    # The recursion limit is set to 10000 above.
                    payload = (json_std.dumps(item, ensure_ascii=False) + "\n").encode("utf-8")
                f.write(payload)
                if not payload.endswith(b"\n"):
                    f.write(b"\n")
                written += 1
        os.replace(tmp, file_path)
    except BaseException:
        common.remove_if_exists(tmp)
        raise
    return written


def run_month(month: str) -> dict:
    posts_path = common.stage_dir("4c", month) / "posts_prefiltered.jsonl"
    comments_path = common.stage_dir(6, month) / "comments_cleaned.jsonl"
    common.month_to_year_dir(month)
    out_dir = common.OUTPUT_ROOT / "stage7_trees" / month
    out_dir.mkdir(parents=True, exist_ok=True)
    trees_path = out_dir / "comment_trees.jsonl"
    orphan_path = out_dir / "orphan_comments.jsonl"
    meta_path = out_dir / "trees_metadata.json"

    if not posts_path.is_file():
        raise FileNotFoundError(f"{month}: missing {posts_path}")
    if not comments_path.is_file():
        raise FileNotFoundError(f"{month}: missing {comments_path}")

    started = time.monotonic()
    post_ids = load_post_ids(posts_path)
    post_trees, orphan_trees, stats = build_comment_trees(comments_path, post_ids)
    stats["posts"] = len(post_ids)

    posts_written = save_trees(trees_path, post_trees, "comments")
    orphan_posts_written = save_trees(orphan_path, orphan_trees, "orphan_comments")

    elapsed = time.monotonic() - started
    meta = {
        "status": "completed",
        "stage": 7,
        "month": month,
        "completed_at": common.utc_now(),
        "posts_input": common.file_signature(posts_path),
        "comments_input": common.file_signature(comments_path),
        "comment_trees_output_bytes": trees_path.stat().st_size,
        "orphan_output_bytes": orphan_path.stat().st_size,
        "posts_with_trees_written": posts_written,
        "posts_with_orphans_written": orphan_posts_written,
        **stats,
        "elapsed_seconds": round(elapsed, 3),
    }
    common.atomic_write_json(meta_path, meta)
    print(
        f"[{month}] posts {stats['posts']}, matched comments {stats['matched_comments']:,}, "
        f"connected comments {stats['normal_tree_comments']:,}, "
        f"orphan-branch comments {stats['orphan_branch_comments']:,} "
        f"(direct orphans {stats['direct_orphan_comments']:,}) [{elapsed:.1f}s]",
        flush=True,
    )
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 7: Build connected reply trees and separate orphan branches")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)
    run_month(args.month)


if __name__ == "__main__":
    main()
