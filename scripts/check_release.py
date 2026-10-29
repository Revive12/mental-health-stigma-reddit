"""Check the public source tree for accidental private files and non-English text."""
from pathlib import Path
import ast
import re

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", ".pytest_cache", ".mplconfig", ".venv", "figures"}
errors = []
checked = 0
for path in ROOT.rglob("*"):
    relative = path.relative_to(ROOT)
    if not path.is_file() or any(part in SKIP for part in relative.parts):
        continue
    if path.name == ".DS_Store" or path.suffix in {".zst", ".sqlite", ".sqlite3"}:
        errors.append(f"Unexpected private/cache file: {relative}")
        continue
    if path.suffix not in {".py", ".md", ".txt", ".json", ".jsonl", ".csv", ".yml", ".yaml"} and path.name not in {"LICENSE", ".env.example", ".gitignore"}:
        continue
    checked += 1
    text = path.read_text(encoding="utf-8")
    if re.search(r"[\u3400-\u4dbf\u4e00-\u9fff]", text):
        errors.append(f"Non-English CJK text: {relative}")
    if re.search(r"/(?:Users|home)/[A-Za-z0-9]", text):
        errors.append(f"Machine-specific personal path: {relative}")
    if re.search(r"(?:sk-proj-|sk-)[A-Za-z0-9_-]{24,}", text):
        errors.append(f"Possible embedded API credential: {relative}")
    if path.suffix == ".py":
        try:
            ast.parse(text, filename=str(relative))
        except SyntaxError as exc:
            errors.append(f"Invalid Python: {relative}: {exc}")
if errors:
    raise SystemExit("\n".join(errors))
print(f"Source checks passed for {checked} text files. This is a heuristic scan, not a privacy guarantee.")
