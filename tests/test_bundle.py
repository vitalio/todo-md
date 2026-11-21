#!/usr/bin/env python3
"""Tests for the context-bundle-protocol v1 producer."""

import json
import os
import re
import unittest
from tests.helpers import SCRIPT, TodoMdTestCase

PART_RE = re.compile(
    r"<!-- bundle:(?P<nonce>[0-9a-f]+):part (?P<meta>\{.*?\}) -->\n(?P<body>.*?)\n"
    r"<!-- bundle:(?P=nonce):end -->",
    re.S,
)


class TestBundle(TodoMdTestCase):
    def _parse(self, out):
        head, _, rest = out.partition("\n\n")
        headers = dict(line.split(": ", 1) for line in head.splitlines())
        parts = [(json.loads(m.group("meta")), m.group("body")) for m in PART_RE.finditer(rest)]
        return headers, parts

    def _setup_task(self):
        self._run([str(SCRIPT), "init"], check=True)
        (self.tmp / "app.py").write_text("print('hi')\n", encoding="utf-8")
        self._run(
            [str(SCRIPT), "add", "Bundle task", "--next", "-b", "- Target files: `app.py`."],
            check=True,
        )

    def _todo(self):
        return (self.tmp / "TODO.md").read_text(encoding="utf-8")

    def test_task_bundle_stream_and_session_start_wip(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        headers, parts = self._parse(r.stdout)
        self.assertTrue(r.stdout.startswith("Bundle-Protocol: 1\n"), msg=r.stdout)
        self.assertIn("===== Rules =====", r.stdout)
        self.assertTrue(headers["Bundle-Command"].endswith("--bundle F1"))
        self.assertRegex(headers["Bundle-Boundary"], r"^[0-9a-f]{32}$")
        self.assertEqual(headers["Bundle-Expose"], "Role, Task, Title")
        self.assertEqual((headers["Task"], headers["Role"]), ("F1", "work"))
        self.assertEqual(headers["Title"], "Bundle task")
        self.assertEqual(headers["Workdir"], str(self.tmp.resolve()))
        self.assertEqual([m["kind"] for m, _ in parts], ["rule", "include", "task"])
        rule_meta, rule_body = parts[0]
        self.assertEqual(rule_meta, {"kind": "rule", "id": "todo_md:todo_md", "chain": ["todo_md"]})
        self.assertIn("Target files contract", rule_body)
        inc_meta, inc_body = parts[1]
        self.assertEqual(inc_meta, {"kind": "include", "name": "app.py", "chain": ["todo_md"]})
        self.assertTrue(inc_body.startswith("===== $ cat app.py ====="), msg=inc_body)
        task_meta, task_body = parts[2]
        self.assertEqual(
            task_meta, {"kind": "task", "id": "F1", "name": "TODO.md:F1", "chain": ["todo_md"]}
        )
        self.assertTrue(task_body.startswith("===== Prompt ====="))
        self.assertIn("# 🔵 [WIP] F1:", task_body)
        self.assertIn("# 🔵 [WIP] F1:", self._todo())

    def test_bundle_slice_include_uses_sed_header(self):
        self._run([str(SCRIPT), "init"], check=True)
        (self.tmp / "big.py").write_text("".join(f"l{i}\n" for i in range(1, 21)), encoding="utf-8")
        self._run(
            [str(SCRIPT), "add", "Slice", "--next", "-b", "- Target files: `big.py:3-5`."],
            check=True,
        )
        r = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        _, parts = self._parse(r.stdout)
        meta, body = parts[1]
        self.assertEqual(meta["name"], "big.py:3-5")
        self.assertEqual(body, "===== $ sed -n '3,5p' big.py =====\nl3\nl4\nl5")

    def test_bundle_no_wip_and_no_files(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "--bundle", "--no-wip", "--no-files", "F1"], check=True)
        _, parts = self._parse(r.stdout)
        self.assertEqual([m["kind"] for m, _ in parts], ["rule", "task"])
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_plain_calls_never_mutate_status(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "F1"], check=True)
        self.assertNotIn("Bundle-Protocol", r.stdout)
        self.assertIn("Task: F1", r.stdout)
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_session_start_wip_follows_resolved_role(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "Plan only"], check=True)
        self._run([str(SCRIPT), "add", "D", "Design only"], check=True)
        r_plan = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        self.assertEqual(self._parse(r_plan.stdout)[0]["Role"], "plan")
        self.assertIn("# ⚪ [NEW] F1:", self._todo())
        r_design = self._run([str(SCRIPT), "--bundle", "D1"], check=True)
        self.assertEqual(self._parse(r_design.stdout)[0]["Role"], "design")
        self.assertIn("# 🔵 [WIP] D1:", self._todo())

    def test_archived_task_is_not_mutated(self):
        self._setup_task()
        self._run([str(SCRIPT), "done", "F1"], check=True)
        r = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        _, parts = self._parse(r.stdout)
        self.assertEqual(parts[-1][0]["name"], "TODO_ARCHIVE.md:F1")
        self.assertNotIn("F1:", self._todo())

    def test_context_bundle_for_quest_log_and_overview(self):
        self._setup_task()
        for args in (["--bundle"], ["--bundle", "overview"]):
            with self.subTest(args=args):
                r = self._run([str(SCRIPT), *args], check=True)
                headers, parts = self._parse(r.stdout)
                self.assertNotIn("Task", headers)
                self.assertEqual(headers["Workdir"], str(self.tmp.resolve()))
                self.assertEqual([m["kind"] for m, _ in parts], ["rule", "context"])
                self.assertEqual(parts[1][0]["name"], "todo_md")
                self.assertIn("F1", parts[1][1])

    def test_fifo_auto_detection(self):
        self._setup_task()
        drop = ("TODO_MD_PLAIN", "TODO_MD_BUNDLE", "RUN_BLOCK_STEP_STDOUT_INO", "IN_RUN_BLOCK")
        base_env = {k: v for k, v in os.environ.items() if k not in drop}
        cases = (
            ({}, ["F1"], True),
            ({"IN_RUN_BLOCK": "1"}, ["F1"], False),
            ({"IN_RUN_BLOCK": "1", "RUN_BLOCK_STEP_STDOUT_INO": "1:1"}, ["F1"], True),
            ({}, ["--plain", "F1"], False),
            ({"TODO_MD_PLAIN": "1"}, ["F1"], False),
            ({"TODO_MD_PLAIN": "1"}, ["--bundle", "F1"], True),
            ({"TODO_MD_BUNDLE": "1"}, ["F1"], True),
        )
        for extra, args, expected in cases:
            with self.subTest(extra=extra, args=args):
                r = self._run_subprocess(
                    [str(SCRIPT), *args, "--no-wip"], env={**base_env, **extra}, check=True
                )
                self.assertEqual("Bundle-Protocol: 1" in r.stdout, expected, msg=r.stdout)

    def test_help_documents_bundle_flags(self):
        r = self._run_subprocess([str(SCRIPT), "--help"], check=True)
        for frag in ("--bundle", "--plain", "--no-files", "--no-wip", "TODO_MD_BUNDLE", "TODO_MD_PLAIN"):
            with self.subTest(frag=frag):
                self.assertIn(frag, r.stdout)


if __name__ == "__main__":
    unittest.main()
