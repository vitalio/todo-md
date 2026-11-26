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
        self._run(
            [str(SCRIPT), "add", "Bundle task", "--next", "-b", "Task description."],
            check=True,
        )

    def _todo(self):
        return (self.tmp / "TODO.md").read_text(encoding="utf-8")

    def test_task_bundle_stream_is_read_only_and_declarative(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        headers, parts = self._parse(r.stdout)
        self.assertTrue(r.stdout.startswith("Bundle-Protocol: 1\n"), msg=r.stdout)
        self.assertEqual(headers["Bundle-Name"], "vitalio/todo-md")
        self.assertIn("===== Rules =====", r.stdout)
        self.assertTrue(headers["Bundle-Command"].endswith("--bundle F1"))
        self.assertRegex(headers["Bundle-Boundary"], r"^[0-9a-f]{32}$")
        self.assertNotIn("Bundle-Expose", headers)
        self.assertNotIn("Role", headers)
        self.assertEqual(headers["Task"], "F1")
        self.assertEqual(headers["Prefix"], "F")
        self.assertEqual(headers["Status"], "NEXT")
        self.assertEqual(headers["Title"], "Bundle task")
        self.assertNotIn("Files", headers)
        self.assertEqual(headers["Workdir"], str(self.tmp.resolve()))
        self.assertEqual([m["kind"] for m, _ in parts], ["rule", "prompt"])
        rule_meta, rule_body = parts[0]
        self.assertEqual(rule_meta, {"kind": "rule", "id": "vitalio/todo-md:todo", "chain": ["vitalio/todo-md"]})
        self.assertNotIn("# Description:", rule_body)
        self.assertNotIn("[if ", rule_body)
        self.assertIn("`L` is a", rule_body)
        task_meta, task_body = parts[1]
        self.assertEqual(
            task_meta, {"kind": "prompt", "id": "F1", "name": "TODO.md:F1", "chain": ["vitalio/todo-md"]}
        )
        self.assertTrue(task_body.startswith("===== Prompt ====="))
        self.assertIn("# 🎯 [NEXT] F1:", task_body)
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_plain_calls_never_mutate_status(self):
        self._setup_task()
        r = self._run([str(SCRIPT), "F1"], check=True)
        self.assertNotIn("Bundle-Protocol", r.stdout)
        self.assertIn("Task: F1", r.stdout)
        self.assertIn("Prefix: F", r.stdout)
        self.assertIn("Status: NEXT", r.stdout)
        self.assertNotIn("Role:", r.stdout)
        self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_bundle_task_headers_across_prefixes_and_statuses(self):
        self._run([str(SCRIPT), "init"], check=True)
        self._run([str(SCRIPT), "add", "Plan only"], check=True)
        self._run([str(SCRIPT), "add", "D", "Design only"], check=True)
        self._run([str(SCRIPT), "add", "L", "Law rule update"], check=True)
        r_f = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        f_headers, f_parts = self._parse(r_f.stdout)
        self.assertEqual((f_headers["Prefix"], f_headers["Status"]), ("F", "NEW"))
        self.assertNotIn("Role", f_headers)
        self.assertNotIn("Files", f_headers)
        self.assertIn("# ⚪ [NEW] F1:", self._todo())
        self.assertIn("Task ID prefixes", f_parts[0][1])

        r_d = self._run([str(SCRIPT), "--bundle", "D1"], check=True)
        d_headers, _ = self._parse(r_d.stdout)
        self.assertEqual((d_headers["Prefix"], d_headers["Status"]), ("D", "NEW"))
        self.assertNotIn("Role", d_headers)

        r_l = self._run([str(SCRIPT), "--bundle", "L1"], check=True)
        l_headers, _ = self._parse(r_l.stdout)
        self.assertEqual((l_headers["Prefix"], l_headers["Status"]), ("L", "NEW"))
        self.assertNotIn("Role", l_headers)

    def test_archived_task_is_not_mutated(self):
        self._setup_task()
        self._run([str(SCRIPT), "done", "F1"], check=True)
        r = self._run([str(SCRIPT), "--bundle", "F1"], check=True)
        headers, parts = self._parse(r.stdout)
        self.assertEqual(headers["Status"], "DONE")
        self.assertEqual(parts[-1][0]["name"], "TODO_ARCHIVE.md:F1")
        self.assertNotIn("F1:", self._todo())

    def test_context_bundle_for_quest_log_and_overview(self):
        self._setup_task()
        for args in (["--bundle"], ["-B"], ["--bundle", "overview"], ["-B", "overview"]):
            with self.subTest(args=args):
                r = self._run([str(SCRIPT), *args], check=True)
                headers, parts = self._parse(r.stdout)
                self.assertEqual(headers["Bundle-Name"], "vitalio/todo-md")
                self.assertNotIn("Task", headers)
                self.assertNotIn("Role", headers)
                self.assertEqual(headers["Workdir"], str(self.tmp.resolve()))
                self.assertEqual([m["kind"] for m, _ in parts], ["rule", "prompt"])
                self.assertNotIn("# Description:", parts[0][1])
                self.assertIn("Task ID prefixes", parts[0][1])
                self.assertEqual(
                    parts[1][0], {"kind": "prompt", "name": "todo", "chain": ["vitalio/todo-md"]}
                )
                self.assertIn("F1", parts[1][1])

    def test_explicit_bundle_activation_and_plain_pipe_default(self):
        self._setup_task()
        drop = ("TODO_MD_PLAIN", "TODO_MD_BUNDLE", "RUN_BLOCK_STEP_STDOUT_INO", "IN_RUN_BLOCK")
        base_env = {k: v for k, v in os.environ.items() if k not in drop}
        cases = (
            ({}, ["F1"], False),
            ({}, [], False),
            ({}, ["overview"], False),
            ({"IN_RUN_BLOCK": "1"}, ["F1"], False),
            ({"IN_RUN_BLOCK": "1", "RUN_BLOCK_STEP_STDOUT_INO": "1:1"}, ["F1"], False),
            ({}, ["-B", "F1"], True),
            ({}, ["F1", "-B"], True),
            ({}, ["--bundle", "F1"], True),
            ({}, ["show", "-B", "F1"], True),
            ({}, ["--plain", "F1"], False),
            ({"TODO_MD_PLAIN": "1"}, ["F1"], False),
            ({"TODO_MD_PLAIN": "1"}, ["-B", "F1"], True),
            ({"TODO_MD_PLAIN": "1"}, ["--bundle", "F1"], True),
            ({}, ["-B", "--plain", "F1"], True),
            ({"TODO_MD_BUNDLE": "1"}, ["F1"], True),
            ({"TODO_MD_BUNDLE": "1"}, ["--plain", "F1"], False),
            ({"TODO_MD_BUNDLE": "1", "TODO_MD_PLAIN": "1"}, ["F1"], False),
            ({"TODO_MD_BUNDLE": "1", "TODO_MD_PLAIN": "1"}, ["-B", "F1"], True),
        )
        for extra, args, expected in cases:
            with self.subTest(extra=extra, args=args):
                r = self._run_subprocess(
                    [str(SCRIPT), *args], env={**base_env, **extra}, check=True
                )
                self.assertEqual("Bundle-Protocol: 1" in r.stdout, expected, msg=r.stdout)

        removed_symbols = (
            "BUNDLE_CONSUMER_NAMES",
            "STANDARD_FILTER_NAMES",
            "SHELL_WRAPPER_NAMES",
            "_normalize_cmd_token",
            "_argv_executable_name",
            "_pipeline_consumer_from_shell_c",
            "_classify_process_tokens",
            "_read_proc_tokens",
            "_read_proc_ppid_pgid",
            "_ancestor_pids",
            "_linux_fifo_is_standard_filter",
            "_ps_fifo_is_standard_filter",
            "_fifo_is_standard_filter",
        )
        for sym in removed_symbols:
            with self.subTest(removed_symbol=sym):
                self.assertFalse(hasattr(self.todo_md_mod, sym), f"{sym} should be removed")

        for args, expected in (
            ("F1", False),
            ("", False),
            ("-B F1", True),
            ("--bundle F1", True),
        ):
            with self.subTest(pipe_args=args):
                cmd = f"{SCRIPT} {args} | cat".strip()
                r_pipe = self._run_subprocess(
                    ["sh", "-c", cmd],
                    env=base_env,
                    check=True,
                )
                self.assertEqual(
                    "Bundle-Protocol: 1" in r_pipe.stdout,
                    expected,
                    msg=f"cmd={cmd!r}\nstdout={r_pipe.stdout}",
                )

    def test_help_documents_bundle_flags(self):
        r = self._run_subprocess([str(SCRIPT), "--help"], check=True)
        for frag in ("-B, --bundle", "--plain", "role=ROLE", "TODO_MD_BUNDLE", "TODO_MD_PLAIN"):
            with self.subTest(frag=frag):
                self.assertIn(frag, r.stdout)
        self.assertNotIn("--no-files", r.stdout)

    def test_help_drops_no_wip_and_role_flags(self):
        r = self._run_subprocess([str(SCRIPT), "--help"], check=True)
        self.assertNotIn("--no-wip", r.stdout)
        self.assertNotIn("--role", r.stdout)
        self.assertNotIn("--by-role", r.stdout)

    def test_role_override_emits_role_header(self):
        self._setup_task()
        cases = (
            (["F1", "role=plan"], "plan"),
            (["role=plan", "F1"], "plan"),
            (["show", "F1", "role=law"], "law"),
            (["F1", "role=work"], "work"),
        )
        for args, role in cases:
            with self.subTest(args=args):
                r = self._run([str(SCRIPT), "--bundle", *args], check=True)
                headers, parts = self._parse(r.stdout)
                self.assertEqual(headers["Role"], role)
                self.assertIn("Task ID prefixes", parts[0][1])
                self.assertIn("# 🎯 [NEXT] F1:", self._todo())

    def test_role_override_on_context_streams(self):
        self._setup_task()
        for args, expected_role in (
            (["role=work"], "work"),
            (["overview", "role=work"], "work"),
            (["-w", "role=plan"], "plan"),
        ):
            with self.subTest(args=args):
                r = self._run([str(SCRIPT), "--bundle", *args], check=True)
                headers, parts = self._parse(r.stdout)
                self.assertNotIn("Task", headers)
                self.assertEqual(headers["Role"], expected_role)
                self.assertIn("Task ID prefixes", parts[0][1])
        r = self._run([str(SCRIPT), "--bundle", "last", "NEXT", "role=plan"], check=True)
        headers, parts = self._parse(r.stdout)
        self.assertEqual((headers["Task"], headers["Role"]), ("F1", "plan"))
        self.assertIn("Task ID prefixes", parts[0][1])

    def test_embedded_rule_is_single_pure_markdown_file(self):
        mod = self.todo_md_mod
        full = mod.get_embedded_todo_rule()
        self.assertIn("Task ID prefixes", full)
        self.assertFalse(hasattr(mod, "EMBEDDED_RULE_TODO_MD_WORK"))
        self.assertFalse((ROOT / "agents" / "todo_md.md").exists())
        self.assertNotIn("{cmd:todo}", full)
        text = (ROOT / "agents" / "todo.md").read_text(encoding="utf-8")
        self.assertIn("{cmd:todo}", text)
        self.assertNotIn("[if ", text)
        self.assertNotIn("[endif]", text)


if __name__ == "__main__":
    unittest.main()
