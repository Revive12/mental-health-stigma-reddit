"""Synthetic regression checks for preprocessing; no APIs or model downloads."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
sys.path.insert(0, str(ROOT / "pipeline" / "lib"))
import common
import keyword_utils
import stage1_keyword_search as stage1
import stage2_recover_context as stage2
import stage3_length_filter as stage3
import stage4_top16_subreddits as stage4
import stage4c_placeholder_bot_filter as stage4c
import stage5_bot_detect as stage5
import stage6_match_and_clean as stage6
import stage7_construct_trees as stage7


def write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")


def comment(name, parent="t3_synthetic", post="t3_synthetic", body="Synthetic example", author="example_user"):
    return {"name": name, "id": name.removeprefix("t1_"), "parent_id": parent,
            "link_id": post, "body": body, "author": author}


class PreprocessingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.previous_root = common.DATA_ROOT
        common.set_data_root(self.root)

    def tearDown(self):
        common.set_data_root(self.previous_root)
        self.temp.cleanup()

    def test_data_root_default_uses_environment(self):
        with patch.dict(os.environ, {"MH_DATA_ROOT": str(self.root)}):
            common.set_data_root(None)
            self.assertEqual(common.DATA_ROOT, self.root)
            self.assertEqual(common.OUTPUT_ROOT, self.root / "pipeline_data")

    def test_invalid_calendar_month_and_path_are_rejected(self):
        for value in ("2024-00", "2024-13", "../outside", "2024-1"):
            with self.assertRaises(ValueError):
                common.stage_dir(3, value)
        self.assertEqual(common.month_to_year_dir("2024-12"), "reddit-24")

    def test_keyword_boundaries_and_whitespace(self):
        regex = keyword_utils.compile_combined_pattern()
        self.assertEqual(len(keyword_utils.MENTAL_HEALTH_KEYWORDS), 30)
        self.assertTrue(regex.search("MENTAL   HEALTH"))
        self.assertFalse(regex.search("distress"))
        self.assertTrue(regex.search("stress"))

    def test_stage4_requires_all_months(self):
        with self.assertRaises(FileNotFoundError):
            stage4.run(["2024-01"], 16)

    def test_missing_recovery_input_is_not_treated_as_empty(self):
        d = common.stage_dir(1, "2024-01")
        write_jsonl(d / "matched_posts.jsonl", [])
        with self.assertRaises(FileNotFoundError):
            stage2.run_month("2024-01")

    def test_prefilter_removes_descendants_in_any_input_order(self):
        month = "2024-01"
        d = common.stage_dir(4, month)
        write_jsonl(d / "posts_top16.jsonl", [{"name": "t3_synthetic", "selftext": "Example"}])
        write_jsonl(d / "comments_top16.jsonl", [
            comment("t1_child", "t1_bot"),
            comment("t1_ok"),
            comment("t1_bot", author="AutoModerator"),
            comment("t1_hidden", body="[deleted]"),
            comment("t1_later", "t1_hidden"),
        ])
        stats = stage4c.process_month(month)
        kept = list(common.iter_jsonl_bytes(common.stage_dir("4c", month) / "comments_prefiltered.jsonl"))
        self.assertEqual([r["name"] for r in kept], ["t1_ok"])
        self.assertEqual(stats["comments_dropped_descendant"], 2)

    def test_cross_post_roots_and_orphan_descendants_are_not_connected(self):
        path = self.root / "comments.jsonl"
        write_jsonl(path, [comment("t1_ok"), comment("t1_reply", "t1_ok"),
                           comment("t1_wrongroot", "t3_other"),
                           comment("t1_orphan", "t1_missing"), comment("t1_desc", "t1_orphan")])
        trees, orphans, stats = stage7.build_comment_trees(path, ["t3_synthetic"])
        self.assertEqual(stage7.collect_reachable_ids(trees["t3_synthetic"]), {"t1_ok", "t1_reply"})
        self.assertEqual(stage7.collect_reachable_ids(orphans["t3_synthetic"]),
                         {"t1_wrongroot", "t1_orphan", "t1_desc"})
        self.assertEqual(stats["preserved_comments"], 5)

    def test_cycles_are_rejected(self):
        path = self.root / "comments.jsonl"
        write_jsonl(path, [comment("t1_a", "t1_b"), comment("t1_b", "t1_a")])
        with self.assertRaisesRegex(ValueError, "Cycle"):
            stage7.build_comment_trees(path, ["t3_synthetic"])

    def test_duplicate_comment_ids_are_rejected(self):
        path = self.root / "comments.jsonl"
        write_jsonl(path, [comment("t1_duplicate"), comment("t1_duplicate")])
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            stage7.build_comment_trees(path, ["t3_synthetic"])

    def test_ai_resume_requires_same_threshold_and_token_limit(self):
        inp, out, meta = (self.root / x for x in ("input.jsonl", "output.jsonl", "metadata.json"))
        inp.write_text("{}\n")
        out.write_text("{}\n")
        info = {"status": "completed", "input_bytes": inp.stat().st_size,
                "input_mtime_ns": inp.stat().st_mtime_ns, "output_bytes": out.stat().st_size,
                "model_id": stage5.MODEL_ID, "ai_threshold": 0.5, "max_length": 512}
        meta.write_text(json.dumps(info))
        self.assertTrue(stage5.is_complete(inp, out, meta))
        info["ai_threshold"] = 0.8
        meta.write_text(json.dumps(info))
        self.assertFalse(stage5.is_complete(inp, out, meta))

    def test_synthetic_month_pipeline_preserves_top_level_subreddit(self):
        import zstandard
        month = "2024-01"
        posts = [{"id": "synthetic", "name": "t3_synthetic", "subreddit": "ActualForum",
                  "title": "Synthetic anxiety discussion example containing enough words for this test case",
                  "selftext": "Example", "crosspost_parent_list": [{"subreddit": "WrongForum"}]},
                 {"id": "short", "name": "t3_short", "subreddit": "WrongForum",
                  "title": "anxiety", "selftext": ""}]
        comments = [comment("t1_root", body="Synthetic anxiety example"),
                    comment("t1_reply", "t1_root"), comment("t1_ai"),
                    comment("t1_ai_child", "t1_ai")]
        for path, rows in ((common.submission_zst(month), posts), (common.comment_zst(month), comments)):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zstandard.ZstdCompressor().compress(
                "".join(json.dumps(x) + "\n" for x in rows).encode()))
        with redirect_stdout(io.StringIO()):
            stage1.run_month(month)
            stage2.run_month(month)
            stage3.run_month(month)
            stage4.run([month], 1)
            stage4c.process_month(month)
            prefiltered = list(common.iter_jsonl_bytes(common.stage_dir("4c", month) / "comments_prefiltered.jsonl"))
            for row in prefiltered:
                row["slop_detection"] = {"is_ai_generated": row["name"] == "t1_ai"}
            write_jsonl(common.stage_dir(5, month) / "comments_bot_labeled.jsonl", prefiltered)
            stage6.run_month(month)
            meta = stage7.run_month(month)
        selected = json.loads((common.stage_dir(4) / "top16_subreddits.json").read_text())
        self.assertEqual(selected["top_subreddits"], ["actualforum"])
        self.assertEqual(meta["normal_tree_comments"], 2)
        self.assertEqual(meta["orphan_branch_comments"], 1)
        self.assertEqual(meta["posts_with_trees_written"], 1)


if __name__ == "__main__":
    unittest.main()
