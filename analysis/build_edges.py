#!/usr/bin/env python3
"""Build validated parent-comment -> reply edges from labeled JSONL.

Records must be grouped by post; their order within a post is arbitrary.
Missing parents, duplicate comments, cycles, and invalid labels are errors.
Original-post responses remain in the post manifest but do not create edges.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path

LABELS = tuple('ABCDEFGH')
MH_SUBS = {'depression', 'anxiety', 'suicidewatch', 'bpd', 'mentalhealth'}
FIELDS = ['post_id', 'subreddit', 'community_type', 'parent_comment', 'comment_id',
          'p_label', 'c_label', 'parent_author', 'child_author']


def community_type(sub: str) -> str:
    if not isinstance(sub, str) or not sub.strip():
        raise ValueError('A non-empty subreddit is required; missing values cannot be assigned to General.')
    return 'MH' if sub.lower() in MH_SUBS else 'General'


def iter_posts(path):
    """Stream post blocks and reject a post that reappears in another block."""
    seen, block, current = set(), [], None
    with open(path, encoding='utf-8') as handle:
        for line_no, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            post = row.get('post_name')
            if not isinstance(post, str) or not post.startswith('t3_'):
                raise ValueError(f'Line {line_no}: invalid post_name')
            if row.get('label') not in LABELS:
                raise ValueError(f'Line {line_no}: label must be exactly A-H')
            if not isinstance(row.get('comment_name'), str) or not row['comment_name'].startswith('t1_'):
                raise ValueError(f'Line {line_no}: invalid comment_name')
            community_type(row.get('subreddit'))
            if post != current:
                if current is not None:
                    yield current, block
                    seen.add(current)
                if post in seen:
                    raise ValueError(f'Non-contiguous post block: {post}')
                current, block = post, []
            block.append(row)
    if block:
        yield current, block


def edges_for_post(post, rows):
    indexed = {r['comment_name']: r for r in rows}
    if len(indexed) != len(rows):
        raise ValueError(f'Duplicate comment identifier in {post}')
    subs = {r['subreddit'].lower() for r in rows}
    if len(subs) != 1:
        raise ValueError(f'Inconsistent subreddit within {post}')
    sub = next(iter(subs))
    # Validate connectivity independently of serialization order.
    connected = set()
    for name in indexed:
        path, visited, cursor = [], set(), name
        while cursor != post and cursor not in connected:
            if cursor in visited:
                raise ValueError(f'Cycle in {post}: {cursor}')
            if cursor not in indexed:
                raise ValueError(f'Missing or cross-post parent in {post}: {cursor}')
            visited.add(cursor); path.append(cursor)
            cursor = indexed[cursor].get('parent_id')
        connected.update(path)
    for row in rows:
        parent = row['parent_id']
        if parent == post:
            continue
        previous = indexed[parent]
        yield dict(zip(FIELDS, [post, sub, community_type(sub), parent,
            row['comment_name'], previous['label'], row['label'],
            previous.get('author_fullname') or '', row.get('author_fullname') or '']))


def build_edges(source, output, posts_output=None):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + '.tmp')
    posts = []
    count = 0
    try:
        with temp.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            for post, rows in iter_posts(source):
                edges = list(edges_for_post(post, rows))
                writer.writerows(edges); count += len(edges)
                sub = rows[0]['subreddit'].lower()
                posts.append({'post_id': post, 'subreddit': sub,
                    'community_type': community_type(sub), 'month': rows[0].get('month') or '', 'n_comments': len(rows),
                    'n_edges': len(edges)})
        temp.replace(output)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    if posts_output:
        target = Path(posts_output); target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('w', newline='', encoding='utf-8') as handle:
            writer = csv.DictWriter(handle, fieldnames=['post_id', 'subreddit', 'community_type', 'month', 'n_comments', 'n_edges'])
            writer.writeheader(); writer.writerows(posts)
    return {'posts': len(posts), 'edges': count}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labeled', required=True)
    parser.add_argument('--out', default='edges.csv')
    parser.add_argument('--posts-out', help='Post manifest including discussions without comment-to-comment edges')
    args = parser.parse_args()
    print(json.dumps(build_edges(args.labeled, args.out, args.posts_out), indent=2))

if __name__ == '__main__':
    main()
