#!/usr/bin/env python3
"""Stage 5: classify potential AI-generated comments with slop-detector.

Read stage4c_filter/YYYY-MM/comments_prefiltered.jsonl and add slop_detection.
Every comment is scored, including short comments; input is truncated to
512 model tokens. Write stage5_bot/YYYY-MM/comments_bot_labeled.jsonl and
metadata. Requires CUDA. The default model is trentmkelly/slop-detector-mini-2.
This model score is a proxy, not proof of human or AI authorship.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import common



MODEL_ID = "trentmkelly/slop-detector-mini-2"   # Hugging Face model ID or local path; overridden by --model.
AI_LABEL_ID = 1
AI_THRESHOLD = 0.5


def load_model(gpu_id: int, model_id: str | None = None):
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    model_id = model_id or MODEL_ID
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; stage 5 requires a CUDA GPU")
    if gpu_id < 0 or gpu_id >= torch.cuda.device_count():
        raise ValueError(
            f"GPU {gpu_id} unavailable; visible CUDA devices: {torch.cuda.device_count()} "
        )
    print(f"[GPU {gpu_id}] Loading tokenizer/model {model_id}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForSequenceClassification.from_pretrained(model_id)
    device = torch.device(f"cuda:{gpu_id}")
    model.to(device)
    model.eval()
    torch.set_float32_matmul_precision("high")
    labels = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
    if labels.get(AI_LABEL_ID) not in {"llm", "ai", "ai_generated"}:
        raise ValueError(f"Unexpected model label configuration: {labels}")
    print(f"[GPU {gpu_id}] Model ready on {device}", flush=True)
    return tokenizer, model, device


def infer_and_write(texts, rows, tokenizer, model, device, output_file) -> int:
    import torch

    inputs = tokenizer(
        texts, return_tensors="pt", truncation=True, max_length=512, padding=True
    )
    inputs = {k: v.to(device, non_blocking=True) for k, v in inputs.items()}
    with torch.inference_mode():
        logits = model(**inputs).logits
        scores = torch.softmax(logits, dim=-1)[:, AI_LABEL_ID].cpu().tolist()

    ai_count = 0
    for row, score_value in zip(rows, scores):
        score = float(score_value)
        is_ai = score > AI_THRESHOLD
        ai_count += int(is_ai)
        row["slop_detection"] = {
            "is_ai_generated": is_ai,
            "confidence": round(score, 4),
            "label": "predicted_ai" if is_ai else "predicted_human",
        }
        output_file.write(common.json_dumps_bytes(row))
        output_file.write(b"\n")
    return ai_count


def is_complete(input_path: Path, output_path: Path, metadata_path: Path,
                model_id: str | None = None) -> bool:
    if not output_path.is_file() or not metadata_path.is_file():
        return False
    try:
        meta = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    istat = input_path.stat()
    return (
        meta.get("status") == "completed"
        and meta.get("input_bytes") == istat.st_size
        and meta.get("input_mtime_ns") == istat.st_mtime_ns
        and meta.get("output_bytes") == output_path.stat().st_size
        and meta.get("model_id") == (model_id or MODEL_ID)
        and meta.get("ai_threshold") == AI_THRESHOLD
        and meta.get("max_length") == 512
    )


def process_month(month: str, gpu_id: int, batch_size: int, force: bool,
                  model_id: str | None = None) -> None:
    if batch_size < 1:
        raise ValueError("Batch size must be positive")
    input_path = common.stage_dir("4c", month) / "comments_prefiltered.jsonl"
    output_path = common.stage_dir(5, month) / "comments_bot_labeled.jsonl"
    metadata_path = common.stage_dir(5, month) / "bot_detection_metadata.json"

    if not input_path.is_file():
        raise FileNotFoundError(f"Stage 4c comments file not found: {input_path}")

    if not force and is_complete(input_path, output_path, metadata_path, model_id):
        print(f"[{month}] Stage 5 already completed; skipping", flush=True)
        return

    common.remove_if_exists(output_path)
    common.remove_if_exists(metadata_path)

    tokenizer, model, device = load_model(gpu_id, model_id)
    tmp = output_path.with_name(f".{output_path.name}.tmp.{os.getpid()}")
    common.remove_if_exists(tmp)

    input_stat = input_path.stat()
    total = ai_count = human_count = 0
    texts: list[str] = []
    rows: list[dict] = []
    started = time.monotonic()
    print(f"[GPU {gpu_id}] [{month}] batch={batch_size} input={input_path} (all comments scored)", flush=True)

    try:
        with input_path.open("rb", buffering=common.BUFFER_SIZE) as fin,\
             tmp.open("wb", buffering=common.BUFFER_SIZE) as fout:
            for line in fin:
                if not line.strip():
                    continue
                row = common.json_loads_bytes(line)
                total += 1
                body = row.get("body")
                body = body.strip() if isinstance(body, str) else ""

                # Score all comments, without exempting short texts.
                texts.append(body)
                rows.append(row)

                if len(texts) >= batch_size:
                    batch_ai = infer_and_write(
                        texts, rows, tokenizer, model, device, fout
                    )
                    ai_count += batch_ai
                    human_count += len(rows) - batch_ai
                    texts.clear()
                    rows.clear()

                if total % 100_000 == 0:
                    elapsed = time.monotonic() - started
                    rate = total / elapsed if elapsed else 0.0
                    print(
                        f"[GPU {gpu_id}] [{month}] processed {total:,} | "
                        f"{rate:,.0f} rows/s | AI {ai_count:,}",
                        flush=True,
                    )

            if texts:
                batch_ai = infer_and_write(
                    texts, rows, tokenizer, model, device, fout
                )
                ai_count += batch_ai
                human_count += len(rows) - batch_ai

        os.replace(tmp, output_path)
    except BaseException:
        common.remove_if_exists(tmp)
        raise

    elapsed = time.monotonic() - started
    metadata = {
        "status": "completed",
        "stage": 5,
        "month": month,
        "completed_at": common.utc_now(),
        "model_id": model_id or MODEL_ID,
        "ai_label_id": AI_LABEL_ID,
        "ai_threshold": AI_THRESHOLD,
        "max_length": 512,
        "short_text_limit": 0,
        "short_text_skipped": False,
        "batch_size": batch_size,
        "gpu_id_in_process": gpu_id,
        "input": common.file_signature(input_path),
        "input_bytes": input_stat.st_size,
        "input_mtime_ns": input_stat.st_mtime_ns,
        "output_bytes": output_path.stat().st_size,
        "total_comments": total,
        "ai_comments": ai_count,
        "human_comments": human_count,
        "elapsed_seconds": round(elapsed, 3),
    }
    common.atomic_write_json(metadata_path, metadata)
    ai_pct = ai_count / total * 100 if total else 0.0
    print(
        f"[GPU {gpu_id}] [{month}] completed: {total:,} comments, AI {ai_count:,} ({ai_pct:.2f}%), "
        f"elapsed {elapsed / 60:.1f} minutes",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage 5: AI-generated comment detection")
    parser.add_argument("--month", required=True, help="YYYY-MM (one month)")
    parser.add_argument("--gpu", type=int, required=True, help="CUDA device index visible to this process")
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--model", default=None,
                        help="Model ID or local path (default: trentmkelly/slop-detector-mini-2)")
    parser.add_argument("--data-root", default=None,
                        help="Data root (default: MH_DATA_ROOT or ./data)")
    args = parser.parse_args()
    common.set_data_root(args.data_root)

    process_month(args.month, args.gpu, args.batch_size, args.force, args.model)


if __name__ == "__main__":
    main()
