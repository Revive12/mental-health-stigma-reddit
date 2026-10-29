"""Shared path, month, JSONL and atomic metadata helpers.

Raw input files are read-only. Data root precedence is --data-root, then
MH_DATA_ROOT, then ./data. Monthly dumps reside in
full_data/reddit-YY/{submissions,comments}/RS_YYYY-MM.zst and RC_YYYY-MM.zst.
Derived artifacts reside in pipeline_data/stageN_name/YYYY-MM/.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def resolve_data_root(cli_value: str | None = None) -> Path:
    """Resolve --data-root, then MH_DATA_ROOT, then ./data."""
    root = cli_value or os.environ.get("MH_DATA_ROOT") or "./data"
    return Path(root).resolve()


DATA_ROOT = resolve_data_root()
FULL_DATA = DATA_ROOT / "full_data"
OUTPUT_ROOT = DATA_ROOT / "pipeline_data"


def set_data_root(root: str | Path | None) -> None:
    """Redirect derived paths after CLI argument parsing."""
    global DATA_ROOT, FULL_DATA, OUTPUT_ROOT
    DATA_ROOT = resolve_data_root(str(root) if root is not None else None)
    FULL_DATA = DATA_ROOT / "full_data"
    OUTPUT_ROOT = DATA_ROOT / "pipeline_data"

MONTH_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
BUFFER_SIZE = 16 * 1024 ** 2


# ============================================================
# Calendar months and raw Zstandard paths
# ============================================================

def month_to_year_dir(month: str) -> str:
    """'2024-03' -> 'reddit-24'."""
    if not MONTH_RE.fullmatch(month):
        raise ValueError(f"Invalid calendar month: {month}")
    return f"reddit-{month[2:4]}"


def submission_zst(month: str) -> Path:
    return FULL_DATA / month_to_year_dir(month) / "submissions" / f"RS_{month}.zst"


def comment_zst(month: str) -> Path:
    return FULL_DATA / month_to_year_dir(month) / "comments" / f"RC_{month}.zst"


def discover_months() -> list[str]:
    """Return sorted calendar months discovered in submission dump filenames."""
    months: set[str] = set()
    for year_dir in FULL_DATA.glob("reddit-*"):
        if not year_dir.is_dir():
            continue
        sub_dir = year_dir / "submissions"
        if not sub_dir.is_dir():
            continue
        for path in sub_dir.glob("RS_*.zst"):
            month = path.stem[3:]  # Remove the RS_ prefix
            if MONTH_RE.fullmatch(month):
                months.add(month)
    return sorted(months)


def resolve_months(requested: list[str] | None) -> list[str]:
    """Validate and deduplicate requested months, or discover downloaded months."""
    if not requested:
        return discover_months()
    invalid = [m for m in requested if not MONTH_RE.fullmatch(m)]
    if invalid:
        raise ValueError(f"Invalid calendar month: {invalid}")
    return sorted(set(requested))


# ============================================================
# Derived artifact directories
# ============================================================

# Stage identifiers and their pipeline_data directory names
STAGE_DIRS = {
    1: "stage1_keywords",
    2: "stage2_recover",
    3: "stage3_length",
    4: "stage4_top16",
    "4c": "stage4c_filter",
    5: "stage5_bot",
    6: "stage6_clean",
}


def stage_dir(stage, month: str | None = None) -> Path:
    """Return and create pipeline_data/<stage_dir>/[YYYY-MM/]."""
    if stage not in STAGE_DIRS:
        raise ValueError(f"Unknown stage: {stage}")
    base = OUTPUT_ROOT / STAGE_DIRS[stage]
    if month is not None:
        month_to_year_dir(month)
        base = base / month
    base.mkdir(parents=True, exist_ok=True)
    return base


# ============================================================
# Atomic writes and metadata
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def remove_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def atomic_write_json(path: Path, data: dict) -> None:
    """Commit metadata through a temporary file and atomic replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def file_signature(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


# ============================================================
# Binary JSONL helpers (orjson with standard-library fallback)
# ============================================================

try:
    import orjson as _orjson

    def json_loads_bytes(line: bytes):
        return _orjson.loads(line)

    def json_dumps_bytes(row) -> bytes:
        """Serialize to bytes; the caller must append a newline."""
        return _orjson.dumps(row)

except ImportError:  # pragma: no cover
    import json as _stdlib_json

    def json_loads_bytes(line: bytes):
        return _stdlib_json.loads(line)

    def json_dumps_bytes(row) -> bytes:
        return _stdlib_json.dumps(row, ensure_ascii=False).encode("utf-8")


def iter_jsonl_bytes(path: Path):
    """Stream decoded JSONL objects, skipping blank lines."""
    with path.open("rb", buffering=BUFFER_SIZE) as f:
        for line in f:
            if not line.strip():
                continue
            yield json_loads_bytes(line)
