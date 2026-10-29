"""Local JSON/JSONL/Zstandard stream helpers for Arctic Shift dumps."""

from __future__ import annotations

import gzip
import io
import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from typing import Any, Callable, TextIO

try:
	import zstandard
except ImportError:  # pragma: no cover - depends on the local environment
	zstandard = None

try:
	import orjson
except ImportError:  # pragma: no cover - depends on the local environment
	orjson = None


class RowProgressLog:
	def __init__(
		self,
		path: str,
		print_every: int = 100_000,
		file_size: int | None = None,
		position_getter: Callable[[], int] | None = None,
	):
		self.path = path
		self.print_every = print_every
		self.file_size = file_size
		self.position_getter = position_getter
		self.rows = 0
		self.start_time = time.time()

	def on_row(self) -> None:
		self.rows += 1
		if self.rows % self.print_every == 0:
			self.log(end="\r")

	def log(self, end: str = "\n") -> None:
		elapsed = time.time() - self.start_time
		rate = self.rows / elapsed if elapsed > 0 else 0
		if self.file_size and self.position_getter is not None:
			position = min(self.position_getter(), self.file_size)
			progress = position / self.file_size if self.file_size else 0
			remaining = (elapsed / progress - elapsed) if progress > 0 else 0
			progress_text = f"{progress:.2%}, remaining {format_duration(remaining)}"
		else:
			progress_text = "progress n/a"
		print(f"{self.path}: {self.rows:,} rows, {rate:,.0f} rows/s, {progress_text}", end=end)

	def finish(self) -> None:
		self.log()


def iter_file_paths(path: str, recursive: bool = False) -> Iterator[str]:
	if os.path.isfile(path):
		yield path
		return

	if recursive:
		for root, _dirs, files in os.walk(path):
			for filename in sorted(files):
				yield os.path.join(root, filename)
		return

	for filename in sorted(os.listdir(path)):
		file_path = os.path.join(path, filename)
		if os.path.isfile(file_path):
			yield file_path


def _iter_zst_lines_with_python(path: str) -> Iterator[str]:
	if zstandard is None:
		raise RuntimeError("python zstandard is not installed")

	with open(path, "rb") as f:
		decompressor = zstandard.ZstdDecompressor(max_window_size=2**31)
		with decompressor.stream_reader(f) as reader:
			text_stream = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
			for line in text_stream:
				yield line


def _iter_zst_lines_with_cli(path: str) -> Iterator[str]:
	zstd_bin = shutil.which("zstd")
	if zstd_bin is None:
		raise RuntimeError("Reading .zst files requires either python package 'zstandard' or the zstd CLI")

	proc = subprocess.Popen(
		[zstd_bin, "-dc", path],
		stdout=subprocess.PIPE,
		stderr=subprocess.PIPE,
		text=True,
		encoding="utf-8",
		errors="replace",
	)
	if proc.stdout is None:
		raise RuntimeError("Failed to read zstd stdout")

	try:
		for line in proc.stdout:
			yield line
	finally:
		if proc.stdout is not None:
			proc.stdout.close()
		stderr = proc.stderr.read() if proc.stderr is not None else ""
		return_code = proc.wait()
		if return_code != 0:
			raise RuntimeError(f"zstd failed for {path}: {stderr.strip()}")


def iter_text_lines(path: str) -> Iterator[str]:
	if path.endswith(".zst"):
		if zstandard is not None:
			yield from _iter_zst_lines_with_python(path)
		else:
			yield from _iter_zst_lines_with_cli(path)
	elif path.endswith(".gz"):
		with gzip.open(path, "rt", encoding="utf-8", errors="replace") as f:
			yield from f
	else:
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			yield from f


def parse_json_lines(
	path: str,
	lines: Iterator[str],
	progress: RowProgressLog,
) -> Iterator[dict[str, Any]]:
	for line_number, line in enumerate(lines, start=1):
		progress.on_row()
		line = line.strip()
		if not line:
			continue
		try:
			row = orjson.loads(line) if orjson is not None else json.loads(line)
		except ValueError as exc:
			print(f"Skipping invalid JSON in {path}:{line_number}: {exc}")
			continue
		if isinstance(row, dict):
			yield row
	progress.finish()


def iter_json_objects(path: str, progress_every: int = 100_000) -> Iterator[dict[str, Any]]:
	if path.endswith(".json") and not path.endswith(".jsonl") and not path.endswith(".ndjson"):
		with open(path, "r", encoding="utf-8", errors="replace") as f:
			data = json.load(f)
		if isinstance(data, list):
			for row in data:
				if isinstance(row, dict):
					yield row
		elif isinstance(data, dict):
			yield data
		return

	if path.endswith(".zst") and zstandard is not None:
		with open(path, "rb") as f:
			decompressor = zstandard.ZstdDecompressor(max_window_size=2**31)
			with decompressor.stream_reader(f) as reader:
				text_stream = io.TextIOWrapper(reader, encoding="utf-8", errors="replace")
				progress = RowProgressLog(
					path,
					print_every=progress_every,
					file_size=os.path.getsize(path),
					position_getter=f.tell,
				)
				yield from parse_json_lines(path, text_stream, progress)
		return

	progress = RowProgressLog(path, print_every=progress_every)
	yield from parse_json_lines(path, iter_text_lines(path), progress)


def format_duration(seconds: float) -> str:
	if seconds < 0:
		seconds = 0
	hours = int(seconds // 3600)
	minutes = int((seconds % 3600) // 60)
	secs = int(seconds % 60)
	if hours:
		return f"{hours}h{minutes:02}m{secs:02}s"
	if minutes:
		return f"{minutes}m{secs:02}s"
	return f"{secs}s"


def write_json_line(output_f: TextIO, row: dict[str, Any]) -> None:
	if orjson is not None:
		output_f.write(orjson.dumps(row).decode("utf-8") + "\n")
		return
	output_f.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
