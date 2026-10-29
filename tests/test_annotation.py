"""Offline regressions for selection, annotation validation, and final export."""
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PIPELINE = Path(__file__).resolve().parents[1] / "pipeline"
sys.path.insert(0, str(PIPELINE))
import build_shuffle_index as indexer
import export_labeled_dataset as exporter
import finelabel_stigma as fine
import stream_annotate as stream


def record(name="t1_a", parent="t3_p", post="t3_p", label="H"):
    return {"comment_name": name, "output": {"label": label},
            "subreddit": "synthetic", "month": "2024-01",
            "input": {"post_data": {"name": post}, "context_chain": [],
                      "target_comment": {"name": name, "parent_id": parent, "body": "Synthetic test text."}}}


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class AnnotationTests(unittest.TestCase):
    def test_exact_labels_only(self):
        for invalid in ['{"label":"Help"}', '{"label":"I think"}', '{"label":"A or B"}',
                        '{"label":["H"]}', 'label=H', '[]', '{"label":null}']:
            self.assertEqual(stream.Annotator._parse(invalid)["label"], "X")
            self.assertEqual(fine.parse_label(invalid), "X")
        self.assertEqual(stream.Annotator._parse('{"label":"I"}')["label"], "I")
        self.assertEqual(fine.parse_label('```json\n{"label":"A"}\n```'), "A")
        self.assertEqual(fine.parse_label('<think>ignored</think>{"label":"H"}'), "H")

    def test_endpoint_accepts_v1(self):
        fine.configure_llm("https://example.invalid/v1", "synthetic-test-key")
        self.assertEqual(fine.GPT_ENDPOINT, "https://example.invalid/v1/chat/completions")
        fine.configure_llm("https://example.invalid", "synthetic-test-key")
        self.assertEqual(fine.GPT_ENDPOINT, "https://example.invalid/v1/chat/completions")

    def test_retry_failed_fine_results(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fine.jsonl"
            write_jsonl(path, [{"comment_name": "t1_a", "finelabel": {"label": "ERROR"}},
                              {"comment_name": "t1_b", "finelabel": {"label": "A"}}])
            self.assertEqual(fine.completed_ids(path), {"t1_b"})

    def test_resume_refuses_changed_fine_provenance(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "fine.jsonl"
            write_jsonl(path, [{"comment_name": "t1_a", "finelabel": {"label": "A"}, "model": "first"}])
            with self.assertRaises(ValueError):
                fine.completed_ids(path, model="second")

    def test_fine_prompt_formats_null_input(self):
        fine.load_prompt(PIPELINE / "prompts_finelabel_V4.4.txt")
        prompt = fine.construct_prompt_v44({"title": None, "selftext": None},
            [{"name": "t1_a", "body": None}], {"name": "t1_b", "body": None})
        self.assertIn("[No text content]", prompt)

    def test_fine_cli_offline_output_and_resume(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "pipeline_data/stage_stigma_annotate"
            write_jsonl(root / "batches/batch_000000.jsonl", [record(label="I")])
            # Diagnostic failed batches must not enter the actual batch stream.
            write_jsonl(root / "batches/batch_000001.failed.jsonl", [record("t1_bad", label="X")])
            argv = ["finelabel_stigma.py", "--data-root", folder, "--model", "synthetic-model",
                    "--base-url", "https://example.invalid/v1", "--api-key", "synthetic-test-key"]
            with patch.object(sys, "argv", argv), patch.object(fine, "call_gpt", return_value='{"label":"C"}') as call:
                fine.main()
                self.assertEqual(call.call_count, 1)
                fine.main()
                self.assertEqual(call.call_count, 1)
            rows = [json.loads(line) for line in (root / "finelabel_output.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["finelabel"]["label"], "C")
            self.assertEqual(rows[0]["model"], "synthetic-model")

    def test_large_post_not_split(self):
        rows = [f"key\t2024-01\tt3_p\tsynthetic\tt1_{i}\t0\t0\n" for i in range(1600)]
        rows.append("zzz\t2024-01\tt3_q\tsynthetic\tt1_last\t10\t10\n")
        handle = BytesIO("".join(rows).encode())
        self.assertEqual(len(stream.read_batch(handle, 1000)), 1600)
        self.assertEqual(len(stream.read_batch(handle, 1000)), 1)

    def test_invalid_coarse_and_missing_fine_are_not_H(self):
        with self.assertRaises(ValueError):
            exporter.resolve_label(record(label="ERROR"), {}, {})
        with self.assertRaises(ValueError):
            exporter.resolve_label(record(label="I"), {}, {})
        self.assertEqual(exporter.resolve_label(record(label="ERROR"), {"t1_a": "C"}, {"t1_a": "I"}), ("I", "C", "C"))

    def test_export_is_atomic_on_missing_fine(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_jsonl(root / "batches/batch_000000.jsonl", [record(label="I")])
            out = root / "output.jsonl"
            out.write_text("unchanged\n")
            with self.assertRaises(ValueError):
                exporter.export(root, 0, 1, out)
            self.assertEqual(out.read_text(), "unchanged\n")

    def test_export_prunes_orphans_crosspost_and_cycles(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            rows = [record(), record("t1_b", "t1_a"), record("t1_c", "t1_missing"),
                    record("t1_d", "t1_c"), record("t1_e", "t1_f"), record("t1_f", "t1_e"),
                    record("t1_g", "t1_a", "t3_other")]
            write_jsonl(root / "batches/batch_000000.jsonl", rows)
            result = exporter.export(root, 0, 1, root / "out.jsonl")
            self.assertEqual(result["comments"], 2)
            self.assertEqual(result["pruned"], 5)

    def test_chain_cycle_rejected(self):
        with self.assertRaises(ValueError):
            stream.chain_to_target({"a": ({}, "b"), "b": ({}, "a")}, "a")

    def test_stale_reference_rejected(self):
        class StaleStore:
            def read_post(self, *args): return {"name": "t3_wrong"}
            def read_tree(self, *args): return {"name": "t3_p", "comments": []}
        with self.assertRaises(ValueError):
            stream.build_records([["key", "2024-01", "t3_p", "synthetic", "t1_a", "0", "0"]], StaleStore())

    def test_selected_posts_only_and_materialization_has_separate_progress(self):
        with tempfile.TemporaryDirectory(prefix="annotation test ") as folder:
            data = Path(folder)
            root = data / "pipeline_data"
            post = {"name": "t3_p", "subreddit": "synthetic", "title": "Synthetic example", "selftext": "Test only."}
            other = {**post, "name": "t3_q"}
            write_jsonl(root / "stage4c_filter/2024-01/posts_prefiltered.jsonl", [post, other])
            write_jsonl(root / "stage7_trees/2024-01/comment_trees.jsonl", [
                {"name": "t3_p", "comments": [{"name": "t1_a", "parent_id": "t3_p", "body": "Synthetic text.", "replies": []}]},
                {"name": "t3_q", "comments": [{"name": "t1_b", "parent_id": "t3_q", "body": "Excluded synthetic text.", "replies": []}]}])
            selected = data / "selected.txt"
            selected.write_text("t3_p\n")
            subprocess.run([sys.executable, str(PIPELINE / "build_shuffle_index.py"), "--data-root", str(data),
                            "--selected-posts", str(selected), "--workers", "1"], check=True, capture_output=True)
            output = root / "stage_stigma_annotate"
            contents = (output / "shuffle_index.tsv").read_text()
            self.assertIn("t1_a", contents)
            self.assertNotIn("t1_b", contents)
            subprocess.run([sys.executable, str(PIPELINE / "stream_annotate.py"), "--data-root", str(data),
                            "--materialize-only", "--max-batches", "1"], check=True, capture_output=True)
            self.assertTrue((output / "materialize_progress.json").is_file())
            self.assertFalse((output / "progress.json").exists())
            self.assertTrue((output / "materialized_batches/batch_000000.jsonl").is_file())


if __name__ == "__main__":
    unittest.main()
