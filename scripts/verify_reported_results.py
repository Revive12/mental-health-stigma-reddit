"""Verify reported aggregate counts and inference tables without private Reddit text."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "manuscript_results"

def read(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))

for record in json.loads((DATA / "source_manifest.json").read_text()):
    assert hashlib.sha256((ROOT / record["file"]).read_bytes()).hexdigest() == record["sha256"], record["file"]
rq1 = {row["scope"]: row for row in read(DATA / "fig1/source_data/RQ1_counts.csv")}
assert int(rq1["ALL"]["posts"]) == 104373
assert int(rq1["ALL"]["comments"]) == 6091206
assert int(rq1["ALL"]["S"]) == 86247
assert int(float(rq1["ALL"]["n_stigma_posts"])) == 20110
counts = read(DATA / "fig2/source_data/RQ2_transition_counts.csv")
pooled = [r for r in counts if r["group"] == "ALL"]
assert len(pooled) == 64
assert sum(int(r["N"]) for r in pooled) == 2746063
assert sum(int(r["N"]) for r in pooled if r["parent"] != "H") == 41345
assert sum(int(r["N"]) for r in pooled if r["parent"] != "H" and r["child"] != "H") == 4760
stats = read(DATA / "fig2/source_data/RQ2_transition_stats.csv")
assert sum(int(r["testable"]) for r in stats) == 161
same = [r for r in stats if r["group"] == "ALL" and r["parent"] == r["child"] != "H"]
assert len(same) == 7 and all(float(r["D"]) > 0 and float(r["q_BH"]) < .001 for r in same)
cross = [r for r in stats if r["group"] == "ALL" and r["parent"] != r["child"] and "H" not in (r["parent"], r["child"]) and r["testable"] == "1"]
assert len(cross) == 41
assert sum(float(r["D"]) > 0 and float(r["q_BH"]) < .05 for r in cross) == 38
contrasts = read(DATA / "supplements/source_data/RQ2_community_differences.csv")
assert sum(int(r["testable"]) for r in contrasts) == 36
assert sum(r["testable"] == "1" and float(r["q_BH"]) < .05 for r in contrasts) == 10
print("Frozen aggregate checks passed: 104373 posts; 6091206 comments; 2746063 reply pairs; 161 and 36 eligible tests.")
print("This validates archived tables, not a rerun of annotation or the historical bootstrap.")
