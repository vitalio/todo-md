#!/usr/bin/env python3
"""Tests for the context-bundle-protocol v1 producer."""

import json
import os
import re
import unittest
from tests.helpers import ROOT, SCRIPT, TodoMdTestCase

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

    def test_task_bundle_stream_is_read_only(self):
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
        self.assertNotIn("# Description:", rule_body)
        self.assertNotIn("[if ", rule_body)
        self.assertIn("role=work", rule_body)
        self.assertIn("todo_md done <ID>", rule_body)
        self.assertIn("todo_md status <ID> WIP", rule_body)
        self.assertIn('todo_md add "<title>" -b "<problem_and_impact>"', rule_body)
        self.assertNotIn("Target files contract", rule_body)
        self.assertLessEqual(len(rule_body.splitlines()), 18)
        inc_meta, inc_body = parts[1]
        self.assertEqual(inc_meta, {"kind": "include", "name": "app.py", "chain": ["todo_md"]})
        self.assertTrue(inc_body.startswith("===== $ cat app.py ====="), msg=inc_body)
        task_meta, task_body = parts[2]
        self.assertEqual(
            task_meta, {"kind": "task", "id": "F1", "name": "TODO.md:F1", "chain": ["todo_md"]}
        )
        self.assertTrue(task_body.startswith("===== Prompt ====="))
        self.assertIn("# 🎯 [NEXT] F1:", task_body)
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

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

    def test_bundle_no_files(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "--bundle", "--no-files", "F1"], check=True)
        _, parts = self._parse(r.stdout)
        self.assertEqual([m["kind"] for m, _ in parts], ["rule", "task"])
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_plain_calls_never_mutate_status(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "F1"], check=True)
        self.assertNotIn("Bundle-Protocol", r.stdout)
        self.assertIn("Task: F1", r.stdout)
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_bundle_role_follows_resolved_task_role_without_mutation(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "Plan only"], check=True)
        self._run([str(SCRIPT), "add", "D", "Design only"], check=True)
        r_plan = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        plan_headers, plan_parts = self._parse(r_plan.stdout)
        self.assertEqual(plan_headers["Role"], "plan")
        self.assertIn("# ⚪ [NEW] F1:", self._todo())
        self.assertNotIn("# Description:", plan_parts[0][1])
        self.assertNotIn("[if ", plan_parts[0][1])
        self.assertIn("Target files contract", plan_parts[0][1])
        self.assertLess(len(plan_parts[0][1]), 3800)
        r_design = self._run([str(SCRIPT), "--bundle", "D1"], check=True)
        design_headers, design_parts = self._parse(r_design.stdout)
        self.assertEqual(design_headers["Role"], "design")
        self.assertIn("# ⚪ [NEW] D1:", self._todo())
        self.assertNotIn("# Description:", design_parts[0][1])
        self.assertIn("Target files contract", design_parts[0][1])

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
                self.assertNotIn("# Description:", parts[0][1])
                self.assertIn("Target files contract", parts[0][1])
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
                    [str(SCRIPT), *args], env={**base_env, **extra}, check=True
                )
                self.assertEqual("Bundle-Protocol: 1" in r.stdout, expected, msg=r.stdout)

    def test_help_documents_bundle_flags(self):
        r = self._run_subprocess([str(SCRIPT), "--help"], check=True)
        for frag in ("--bundle", "--plain", "--no-files", "role=ROLE", "TODO_MD_BUNDLE", "TODO_MD_PLAIN"):
            with self.subTest(frag=frag):
                self.assertIn(frag, r.stdout)

    def test_help_drops_no_wip_flag(self):
        r = self._run_subprocess([str(SCRIPT), "--help"], check=True)
        self.assertNotIn("--no-wip", r.stdout)

    def test_role_override_selects_rule_and_header(self):
        self._setup_task()
        cases = (
            (["F1", "role=plan"], "plan", True),
            (["role=plan", "F1"], "plan", True),
            (["show", "F1", "--role", "plan"], "plan", True),
            (["F1", "--role=plan"], "plan", True),
            (["F1", "role=work"], "work", False),
        )
        for args, role, full in cases:
            with self.subTest(args=args):
                r = self._run([str(SCRIPT), "--bundle", *args], check=True)
                headers, parts = self._parse(r.stdout)
                self.assertEqual(headers["Role"], role)
                self.assertEqual("Target files contract" in parts[0][1], full)
                self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_role_override_on_context_streams(self):
        self._setup_task()
        cases = (
            (["role=work"], False),
            (["overview", "role=work"], False),
            (["-w", "role=plan"], True),
        )
        for args, full in cases:
            with self.subTest(args=args):
                r = self._run([str(SCRIPT), "--bundle", *args], check=True)
                headers, parts = self._parse(r.stdout)
                self.assertNotIn("Task", headers)
                self.assertEqual(headers["Role"], "work" if not full else "plan")
                self.assertEqual("Target files contract" in parts[0][1], full)
        r = self._run([str(SCRIPT), "--bundle", "last", "NEXT", "role=plan"], check=True)
        headers, parts = self._parse(r.stdout)
        self.assertEqual((headers["Task"], headers["Role"]), ("F1", "plan"))
        self.assertIn("Target files contract", parts[0][1])

    def test_role_flag_stays_row_filter_for_list(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "list", "--role", "plan"], check=True)
        self.assertNotIn("F1", r.stdout)
        r = self._run([str(SCRIPT), "list", "--role", "work"], check=True)
        self.assertIn("F1", r.stdout)

    def test_embedded_rule_selection_and_pure_markdown_files(self):
        mod = self.todo_md_mod
        work = mod.get_embedded_todo_rule("work")
        full = mod.get_embedded_todo_rule("plan")
        self.assertEqual(full, mod.get_embedded_todo_rule(None))
        self.assertEqual(full, mod.get_embedded_todo_rule("design"))
        self.assertIn("todo_md status <ID> WIP", work)
        self.assertNotIn("Target files contract", work)
        self.assertIn("Target files contract", full)
        self.assertFalse(hasattr(mod, "RULE_IF_BLOCK_RE"))
        for name in ("todo_md.md", "todo_md_work.md"):
            with self.subTest(name=name):
                text = (ROOT / "agents" / name).read_text(encoding="utf-8")
                self.assertNotIn("[if ", text)
                self.assertNotIn("[endif]", text)


if __name__ == "__main__":
    unittest.main()
