#!/usr/bin/env python3
"""Annotate an externally selected sample using the post-grouped reference index.

Batches have a soft record target and never split a post. --max-batches is a
smoke-test/run limit, not a sampling design. Materialization uses its own output
and progress paths and never advances real annotation progress. Only fully valid
H/I batches advance annotation progress; failures are saved for inspection.
"""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time

import common
from prompts import construct_prompt_simple

HERE = Path(__file__).resolve().parent
DATA = common.OUTPUT_ROOT
STAGE4C = DATA / "stage4c_filter"
STAGE7 = DATA / "stage7_trees"
OUT_DIR = DATA / "stage_stigma_annotate"
INDEX = OUT_DIR / "shuffle_index.tsv"
BATCH_DIR = OUT_DIR / "batches"
PROGRESS = OUT_DIR / "progress.json"
BATCH_SIZE = 1000


def build_parent_map(root_comments: list) -> dict:
    """Return node and parent identifiers using iterative tree traversal."""
    parent, stack = {}, [(node, None) for node in root_comments]
    while stack:
        node, pname = stack.pop()
        name = node.get("name")
        if not name or name in parent:
            raise ValueError(f"Missing or duplicate tree comment identifier: {name!r}")
        parent[name] = ({k: v for k, v in node.items() if k != "replies"}, pname)
        stack.extend((child, name) for child in (node.get("replies") or []))
    return parent


def chain_to_target(parent: dict, target: str) -> list:
    if target not in parent:
        return []
    chain, seen, current = [], set(), target
    while current is not None:
        if current in seen or current not in parent:
            raise ValueError(f"Cycle or missing ancestor in comment chain: {current}")
        seen.add(current)
        node, current = parent[current]
        chain.append(node)
    return list(reversed(chain))


class TreeStore:
    def __init__(self):
        self._tree, self._post = {}, {}

    def _fh(self, month, which):
        cache = self._tree if which == "tree" else self._post
        if month not in cache:
            base = STAGE7 if which == "tree" else STAGE4C
            filename = "comment_trees.jsonl" if which == "tree" else "posts_prefiltered.jsonl"
            cache[month] = (base / month / filename).open("rb")
        return cache[month]

    def read_post(self, month, offset):
        handle = self._fh(month, "post")
        handle.seek(offset)
        return json.loads(handle.readline())

    def read_tree(self, month, offset):
        handle = self._fh(month, "tree")
        handle.seek(offset)
        return json.loads(handle.readline())

    def close(self):
        for handle in [*self._tree.values(), *self._post.values()]:
            handle.close()


def build_records(refs: list, store: TreeStore) -> list:
    """Build inputs, rejecting stale offsets or mismatched source records."""
    cache, records = {}, []
    for row in refs:
        if len(row) != 7:
            raise ValueError("Every index row must contain seven tab-separated fields")
        _, month, pname, subreddit, cname, tree_offset, post_offset = row
        key = (month, pname)
        if key not in cache:
            post = store.read_post(month, int(post_offset))
            tree = store.read_tree(month, int(tree_offset))
            if post.get("name") != pname or tree.get("name") != pname:
                raise ValueError(f"Stale index offsets for post {pname}; rebuild the index")
            cache[key] = (post, build_parent_map(tree.get("comments", [])))
        post, parent = cache[key]
        chain = chain_to_target(parent, cname)
        if not chain:
            raise ValueError(f"Indexed comment {cname} is absent from source tree {pname}")
        records.append({"subreddit": subreddit, "month": month, "post_name": pname,
                        "comment_name": cname, "post_data": post,
                        "context_chain": chain[:-1], "target_comment": chain[-1]})
    return records


class Annotator:
    def __init__(self, concurrency=64, max_retries=8, timeout=120, base_url=None,
                 model=None, api_key=None, no_think=False, max_tokens=512, temperature=0.0):
        from openai import AsyncOpenAI
        import httpx
        self.model = model or os.environ.get("ANNOTATE_MODEL")
        if not self.model:
            raise ValueError("Set --model or ANNOTATE_MODEL to the actual deployed coarse model")
        self.base_url = base_url or os.environ.get("ANNOTATE_BASE_URL", "http://127.0.0.1:8123/v1")
        self.temperature, self.no_think, self.max_tokens = temperature, no_think, max_tokens
        self.client = AsyncOpenAI(base_url=self.base_url,
            api_key=api_key or os.environ.get("ANNOTATE_API_KEY", "EMPTY"), timeout=timeout,
            max_retries=0,
            http_client=httpx.AsyncClient(limits=httpx.Limits(max_connections=concurrency,
                                                           max_keepalive_connections=concurrency)))
        self.sem, self.max_retries = asyncio.Semaphore(concurrency), max_retries

    @staticmethod
    def _parse(content: str) -> dict:
        if not isinstance(content, str):
            return {"label": "X", "raw": content}
        cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)[:-3].strip()
        try:
            result = json.loads(cleaned)
            label = result.get("label") if isinstance(result, dict) else None
            label = label if isinstance(label, str) and label in {"H", "I"} else "X"
        except (ValueError, TypeError):
            label = "X"
        return {"label": label, "raw": content}

    async def _one(self, prompt, index):
        if self.no_think:
            prompt += "\n\n/no_think"
        async with self.sem:
            for attempt in range(self.max_retries):
                try:
                    response = await self.client.chat.completions.create(
                        model=self.model, messages=[{"role": "user", "content": prompt}],
                        temperature=self.temperature, max_tokens=self.max_tokens)
                    result = self._parse(response.choices[0].message.content)
                    if result["label"] in {"H", "I"}:
                        return index, result
                    # Invalid responses are not successful annotations.
                    if attempt + 1 == self.max_retries:
                        return index, result
                except Exception as exc:
                    status = getattr(exc, "status_code", None)
                    if status is not None and 400 <= status < 500 and status != 429:
                        raise RuntimeError(f"LLM API rejected the request (HTTP {status}); check configuration") from None
                    if attempt + 1 == self.max_retries:
                        return index, {"label": "ERROR", "raw": ""}
                await asyncio.sleep(min(2 ** attempt, 16))
        return index, {"label": "ERROR", "raw": ""}

    async def batch(self, prompts):
        result = await asyncio.gather(*(self._one(prompt, index) for index, prompt in enumerate(prompts)))
        return [value for _, value in sorted(result)]


def load_progress():
    if PROGRESS.is_file():
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    return {"byte_offset": 0, "batches_done": 0, "records_done": 0}


def save_progress(progress):
    temp = PROGRESS.with_suffix(".json.tmp")
    temp.write_text(json.dumps(progress, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, PROGRESS)


def load_exclude(path):
    source = Path(path) if path else OUT_DIR / "exclude_comments.txt"
    return {x.strip() for x in source.read_text(encoding="utf-8").splitlines() if x.strip()} if source.is_file() else set()


def read_batch(handle, batch_size=BATCH_SIZE):
    """Read whole posts until the soft size target has been reached."""
    rows, previous = [], None
    while True:
        offset = handle.tell()
        line = handle.readline()
        if not line:
            break
        fields = line.rstrip(b"\n").split(b"\t")
        if len(fields) != 7:
            raise ValueError(f"Malformed index row at byte {offset}")
        post = (fields[1], fields[2])
        if rows and len(rows) >= batch_size and post != previous:
            handle.seek(offset)
            break
        rows.append([part.decode("utf-8") for part in fields])
        previous = post
    return rows


def _slim_post(post):
    return {key: post.get(key) for key in ("name", "title", "selftext", "author_fullname", "subreddit", "created_utc")}


async def run(args):
    if not INDEX.is_file():
        raise FileNotFoundError("Reference index not found; run build_shuffle_index.py first")
    BATCH_DIR.mkdir(parents=True, exist_ok=True)
    exclude = load_exclude(args.exclude)
    stat = INDEX.stat()
    config = {"schema_version": 1, "index_size": stat.st_size, "index_mtime_ns": stat.st_mtime_ns,
              "materialize_only": args.materialize_only, "model": args.model or os.environ.get("ANNOTATE_MODEL"),
              "temperature": args.temperature, "no_think": args.no_think, "max_tokens": args.max_tokens,
              "batch_size": args.batch_size,
              "prompt_source_sha256": hashlib.sha256((HERE / "prompts.py").read_bytes()).hexdigest(),
              "exclude_sha256": hashlib.sha256("\n".join(sorted(exclude)).encode()).hexdigest()}
    progress = load_progress()
    if PROGRESS.exists() and progress.get("configuration") != config:
        raise ValueError("Resume settings or source index changed. Use a separate data root for a new run.")
    progress["configuration"] = config
    store = TreeStore()
    annotator = None
    try:
        if not args.materialize_only:
            annotator = Annotator(concurrency=args.concurrency, base_url=args.base_url,
                model=args.model, api_key=args.api_key, no_think=args.no_think,
                max_tokens=args.max_tokens, temperature=args.temperature)
        with INDEX.open("rb") as source:
            source.seek(progress["byte_offset"])
            start = progress["batches_done"]
            while args.max_batches is None or progress["batches_done"] - start < args.max_batches:
                refs = read_batch(source, args.batch_size)
                if not refs:
                    break
                records = build_records([row for row in refs if row[4] not in exclude], store)
                labels = None if args.materialize_only else await annotator.batch([
                    construct_prompt_simple(row["post_data"], row["context_chain"], row["target_comment"])
                    for row in records])
                batch_id = progress["batches_done"]
                out = BATCH_DIR / f"batch_{batch_id:06d}.jsonl"
                temp = out.with_suffix(".jsonl.tmp")
                with temp.open("w", encoding="utf-8") as target:
                    for index, row in enumerate(records):
                        value = {"input": {"post_data": _slim_post(row["post_data"]),
                                           "context_chain": row["context_chain"],
                                           "target_comment": row["target_comment"]},
                                 "subreddit": row["subreddit"], "month": row["month"],
                                 "comment_name": row["comment_name"], "annotation_configuration": config}
                        if labels is not None:
                            value["output"] = labels[index]
                        target.write(json.dumps(value, ensure_ascii=False) + "\n")
                if labels is not None and any(row["label"] not in {"H", "I"} for row in labels):
                    os.replace(temp, out.with_suffix(".failed.jsonl"))
                    raise RuntimeError("Batch contains unresolved annotations; progress was not advanced. Inspect the failed batch and rerun.")
                os.replace(temp, out)
                progress.update(byte_offset=source.tell(), batches_done=batch_id + 1,
                                records_done=progress["records_done"] + len(records))
                save_progress(progress)
                print(f"Batch {batch_id:06d}: {len(records):,} records; total {progress['records_done']:,}", flush=True)
        print(f"Completed {progress['batches_done']} batches / {progress['records_done']:,} records")
    finally:
        store.close()
        if annotator is not None:
            await annotator.client.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--materialize-only", action="store_true", help="Write inputs to materialized_batches without API calls")
    ap.add_argument("--max-batches", type=int, default=None, help="Invocation/smoke-test limit, not an upstream sampling method")
    ap.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Soft target; a post is never split")
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--base-url", default=None, help="ANNOTATE_BASE_URL or local http://127.0.0.1:8123/v1")
    ap.add_argument("--model", default=None, help="Deployed coarse model ID; required unless materializing or ANNOTATE_MODEL is set")
    ap.add_argument("--api-key", default=None, help="Prefer ANNOTATE_API_KEY")
    ap.add_argument("--no-think", action="store_true", help="Append /no_think; use only for a compatible deployed model")
    ap.add_argument("--max-tokens", type=int, default=512)
    ap.add_argument("--exclude", default=None, help="Optional one-comment-ID-per-line exclusion file")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args()
    if args.batch_size < 1 or args.concurrency < 1 or args.max_tokens < 1 or (args.max_batches is not None and args.max_batches < 1):
        ap.error("Batch size, concurrency, max tokens, and max batches must be positive")
    common.set_data_root(args.data_root)
    global DATA, STAGE4C, STAGE7, OUT_DIR, INDEX, BATCH_DIR, PROGRESS
    DATA = common.OUTPUT_ROOT
    STAGE4C, STAGE7 = DATA / "stage4c_filter", DATA / "stage7_trees"
    OUT_DIR = DATA / "stage_stigma_annotate"
    INDEX = OUT_DIR / "shuffle_index.tsv"
    BATCH_DIR = OUT_DIR / ("materialized_batches" if args.materialize_only else "batches")
    PROGRESS = OUT_DIR / ("materialize_progress.json" if args.materialize_only else "progress.json")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with PROGRESS.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        asyncio.run(run(args))


if __name__ == "__main__":
    main()
