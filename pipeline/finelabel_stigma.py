#!/usr/bin/env python3
"""Assign A-H fine labels to coarse-I comments with the frozen V4.4 prompt.

A valid result is required for resume. Invalid/API-error records are retried on
subsequent runs. Use separate --out files for concurrent disjoint batch ranges;
merge these explicitly into finelabel_output.jsonl before export.
"""
from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from itertools import islice
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import time
import requests

import common
from export_labeled_dataset import load_corrections

HERE = Path(__file__).resolve().parent
DATA = common.OUTPUT_ROOT / "stage_stigma_annotate"
OUT = DATA / "finelabel_output.jsonl"
GPT_BASE_URL = GPT_API_KEY = GPT_ENDPOINT = HEADERS = None
PROMPT_FILE = HERE / "prompts_finelabel_V4.4.txt"
PROMPT_V44 = PROMPT_VERSION = None
LABELS = set("ABCDEFGH")


def configure_llm(base_url: str | None, api_key: str | None):
    global GPT_BASE_URL, GPT_API_KEY, GPT_ENDPOINT, HEADERS
    GPT_BASE_URL = base_url or os.environ.get("FINELABEL_BASE_URL")
    GPT_API_KEY = api_key or os.environ.get("FINELABEL_API_KEY")
    if not GPT_BASE_URL or not GPT_API_KEY:
        raise ValueError("Set FINELABEL_BASE_URL and FINELABEL_API_KEY, or use the matching CLI options")
    base = GPT_BASE_URL.rstrip("/")
    GPT_ENDPOINT = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    HEADERS = {"Authorization": f"Bearer {GPT_API_KEY}", "Content-Type": "application/json"}


def load_prompt(path: Path):
    """Load the versioned prompt without rewriting its scientific definitions."""
    global PROMPT_FILE, PROMPT_V44, PROMPT_VERSION
    PROMPT_FILE = Path(path)
    raw = PROMPT_FILE.read_text(encoding="utf-8")
    idx = raw.find("# Role & Task")
    if idx < 0:
        raise ValueError("Prompt template must contain '# Role & Task'")
    PROMPT_V44 = raw[idx:].strip()
    PROMPT_VERSION = f"V4.4[{hashlib.md5(PROMPT_V44.encode()).hexdigest()[:8]}]"


def construct_prompt_v44(post_data, context_chain, target_comment):
    post_title = post_data.get("title") or "N/A"
    post_body = post_data.get("selftext") or ""
    if not post_body.strip():
        post_body = "[No text content]"
    formatted_chain = []
    for idx, comm in enumerate(context_chain):
        if comm.get("name") == target_comment.get("name"):
            continue
        uid = comm.get("author_fullname") or "unknown"
        body = (comm.get("body") or "[deleted]").replace("\n", " ")
        formatted_chain.append(f"{idx + 1}.[User {uid}]: {body}")
    chain_text = "\n".join(formatted_chain) if formatted_chain else "[No previous context, this is a top-level comment]"
    return PROMPT_V44.format(post_title=post_title, post_body=post_body,
                             chain_text=chain_text,
                             target_uid=target_comment.get("author_fullname") or "unknown",
                             target_body=target_comment.get("body") or "").strip()


def collect_I_records(max_batch=None, min_batch=0):
    """Read coarse-I rows, including valid repairs of prior coarse errors."""
    fix, seen = load_corrections(DATA), set()
    for path in sorted((DATA / "batches").glob("batch_*.jsonl")):
        match = re.fullmatch(r"batch_(\d+)\.jsonl", path.name)
        if match is None:
            continue
        idx = int(match.group(1))
        if idx < min_batch or (max_batch is not None and idx >= max_batch):
            continue
        with path.open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                name = row["comment_name"]
                lab = row.get("output", {}).get("label")
                if lab not in {"H", "I"}:
                    lab = fix.get(name, lab)
                if lab not in {"H", "I"}:
                    raise ValueError(f"Resolve coarse annotation failure before fine labeling: {name}")
                if lab == "I":
                    if name in seen:
                        raise ValueError(f"Duplicate coarse-I record: {name}")
                    seen.add(name)
                    yield row


def parse_label(content: str) -> str:
    """Accept exact A-H JSON labels; never infer labels from word prefixes."""
    if not isinstance(content, str):
        return "X"
    cleaned = re.sub(r"<think>.*?</think>", "", content, flags=re.S).strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.I)[:-3].strip()
    try:
        value = json.loads(cleaned)
        label = value.get("label") if isinstance(value, dict) else None
        return label if isinstance(label, str) and label in LABELS else "X"
    except (ValueError, TypeError):
        return "X"


def call_gpt(prompt, model, temperature=0.0, effort=None, timeout=180, max_retries=6):
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": temperature}
    if effort:
        payload["reasoning_effort"] = effort
    for attempt in range(max_retries):
        try:
            response = requests.post(GPT_ENDPOINT, headers=HEADERS, json=payload, timeout=timeout)
            if 400 <= response.status_code < 500 and response.status_code != 429:
                raise RuntimeError(f"LLM API rejected the request (HTTP {response.status_code}); check model and request options")
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            if attempt + 1 == max_retries:
                print(f"LLM request failed after {max_retries} attempts ({type(exc).__name__})", flush=True)
                return None
            time.sleep(min(2 ** attempt, 30))
    return None


def completed_ids(path, model=None, prompt_version=None, settings=None):
    """Only successful results with matching provenance are resumable."""
    done = set()
    if Path(path).is_file():
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                row = json.loads(line)
                if row.get("finelabel", {}).get("label") not in LABELS:
                    continue
                if model is not None and row.get("model") != model:
                    raise ValueError("Output contains another model; choose a separate --out file")
                if prompt_version is not None and row.get("prompt") != prompt_version:
                    raise ValueError("Output contains another prompt version; choose a separate --out file")
                if settings is not None and row.get("settings") != settings:
                    raise ValueError("Output contains different or unrecorded inference settings; use a separate --out file")
                done.add(row["comment_name"])
    return done


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.environ.get("FINELABEL_MODEL"), help="Required deployed model ID; alternatively FINELABEL_MODEL")
    ap.add_argument("--concurrency", type=int, default=16)
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--effort", default=None, help="Optional reasoning_effort, only for endpoints that support it")
    ap.add_argument("--limit", type=int, default=None, help="Maximum records in this invocation")
    ap.add_argument("--max-coarse-batch", type=int, default=None, help="Exclusive batch upper bound")
    ap.add_argument("--min-coarse-batch", type=int, default=0, help="Inclusive batch lower bound")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--api-key", default=None, help="Prefer FINELABEL_API_KEY to avoid shell-history exposure")
    ap.add_argument("--prompt-file", default=str(PROMPT_FILE))
    ap.add_argument("--out", default=None, help="Output JSONL; default: stage_stigma_annotate/finelabel_output.jsonl")
    ap.add_argument("--data-root", default=None)
    args = ap.parse_args()
    if not args.model or args.concurrency < 1 or (args.limit is not None and args.limit < 1):
        ap.error("Provide --model and positive concurrency/limit")
    common.set_data_root(args.data_root)
    global DATA, OUT
    DATA = common.OUTPUT_ROOT / "stage_stigma_annotate"
    OUT = Path(args.out) if args.out else DATA / "finelabel_output.jsonl"
    configure_llm(args.base_url, args.api_key)
    load_prompt(args.prompt_file)
    recs = collect_I_records(args.max_coarse_batch, args.min_coarse_batch)
    settings = {"temperature": args.temperature, "reasoning_effort": args.effort}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a+", encoding="utf-8") as fout:
        fcntl.flock(fout, fcntl.LOCK_EX | fcntl.LOCK_NB)
        done = completed_ids(OUT, args.model, PROMPT_VERSION, settings)
        todo = (row for row in recs if row["comment_name"] not in done)
        if args.limit is not None:
            todo = islice(todo, args.limit)
        print(f"Prompt {PROMPT_VERSION}; already completed {len(done):,}; streaming pending records", flush=True)
        def work(rec):
            prompt = construct_prompt_v44(rec["input"]["post_data"], rec["input"]["context_chain"], rec["input"]["target_comment"])
            content = call_gpt(prompt, args.model, args.temperature, args.effort)
            return rec, {"label": parse_label(content) if content else "ERROR", "raw": content or ""}
        with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
            pending = set()
            exhausted, number = False, 0
            while pending or not exhausted:
                while not exhausted and len(pending) < 2 * args.concurrency:
                    try:
                        pending.add(ex.submit(work, next(todo)))
                    except StopIteration:
                        exhausted = True
                if not pending:
                    break
                finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                for future in finished:
                    rec, output = future.result()
                    fout.write(json.dumps({"comment_name": rec["comment_name"],
                        "subreddit": rec.get("subreddit"), "month": rec.get("month"),
                        "post_name": rec["input"]["post_data"].get("name"), "coarse_label": "I",
                        "finelabel": output, "model": args.model, "prompt": PROMPT_VERSION,
                        "settings": settings}, ensure_ascii=False) + "\n")
                    fout.flush()
                    number += 1
                    if number % 50 == 0:
                        print(f"Fine annotation progress: {number:,} records", flush=True)
    print("Fine annotation finished. Failed records remain eligible for retry.")


if __name__ == "__main__":
    main()
