#!/usr/bin/env python3
"""Tests for todo_md CLI flags, lazy imports, project selector, and install.sh."""

import contextlib
import io
import os
import re
import sys
import unittest
from unittest import mock
from tests.helpers import INSTALL_SH, ROOT, SCRIPT, TodoMdTestCase


class TestCli(TodoMdTestCase):
    def test_help_version_and_agents(self):
        rh = self._run_subprocess([str(SCRIPT), "-h"], check=True)
        self.assertIn("Usage:", rh.stdout)
        flat = self._flat_text(rh.stdout)
        self.assertNotIn("resume", rh.stdout)
        self.assertNotIn("TODO_PLAN.md", rh.stdout)
        self.assertIn("next <ID>", rh.stdout)
        self.assertIn("reopen <ID>", rh.stdout)
        self.assertIn("--reopen", rh.stdout)
        self.assertIn("-C DIR|PROJ, --project NAME", rh.stdout)
        self.assertIn("add", rh.stdout)
        self.assertIn("--role ROLE", rh.stdout)
        self.assertIn("Options: --role ROLE, -r/--ready, --limit N, --full", flat)
        self.assertIn("edit", rh.stdout)
        self.assertIn("append", rh.stdout)

        rv = self._run_subprocess([str(SCRIPT), "--version"], check=True)
        ver = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(rv.stdout.strip(), f"todo_md {ver}")

        self.assertNotIn("--agents", rh.stdout)
        rule_txt = (ROOT / "agents/todo_md.md").read_text(encoding="utf-8")
        self.assertIn("Repository scope only", rule_txt)
        self.assertIn("🎯 [NEXT]", rule_txt)
        self.assertIn("TODO_ARCHIVE.md", rule_txt)
        self.assertIn("reopen <ID>", rule_txt)
        self.assertIn("--reopen", rule_txt)
        self.assertIn("--max-total-bytes N", rule_txt)
        self.assertIn("- Target files:", rule_txt)
        self.assertNotIn("Mode: ", rule_txt)
        self.assertIn("-C <dir|project>` or `--project <name>`", rule_txt)
        self.assertIn("list [active|archive|all|<STATUS>] [<ID>...] [--role <role>] [-r|--ready] [--limit N] [--full]", rule_txt)
        self.assertIn("⏳ [WIP]` / `⏳ [NEXT]", rule_txt)
        self.assertIn("[blocked: A (<STATUS>) -> B (<STATUS>)]", rule_txt)
        self.assertIn("--max-total-lines N", flat)
        self.assertIn("-r, --ready", rh.stdout)
        self.assertIn("`--ready` / `-r`", rule_txt)
        self.assertIn("Chain integration (both directions)", rule_txt)
        self.assertNotIn("queue <ID>", rh.stdout)
        self.assertNotIn("Alias for chain", rh.stdout)
        self.assertIn("chain [<ID>...] [opts]", rh.stdout)
        for help_frag in (
            "overview [--full] [-w]",
            "search <QUERY> [opts]",
            "-t, --tree",
            "--numbered[=left|right]",
            "-l N, --limit N, -n N",
            "--status STATUS",
            "-f, --filter <ID>...",
            "-H, --highlight [<ID>...]",
            "-s, --search QUERY",
            "show <ID>...",
        ):
            with self.subTest(help_frag=help_frag):
                self.assertIn(help_frag, rh.stdout)
        self.assertIn("next-id [<ID>] [--role ROLE]", rh.stdout)
        self.assertIn("queue <ID> [--all]", rule_txt)
        self.assertIn(
            "chain [<ID>...] [--all] [--by-role] [--role <role>] [--ready] [-l N|--limit N] [--include-hold] [--tree] [--numbered[=left|right]]",
            rule_txt,
        )
        self.assertIn("alias for `todo_md chain <ID> [--all]`", rule_txt)
        self.assertIn("4-char connectors", rule_txt)
        self.assertIn("next-id [<ID>] [--role <role>]", rule_txt)
        self.assertIn("A -> B -> C", rule_txt)
        self.assertIn("do not introduce a separate `- Order:` field", rule_txt)
        self.assertIn("role=work", rule_txt)
        self.assertIn("role=review", rule_txt)
        self.assertIn("strips an existing `- Role: plan` line", rule_txt)
        self.assertIn("agents_bundle | run_block", rule_txt)
        self.assertNotIn("role=execute", rule_txt)
        self.assertIn("Task ID prefixes and roles", rh.stdout)
        self.assertIn("D Design (role: design in any status)", flat)
        self.assertNotIn("--role ROLE, --depends SPEC", rh.stdout)
        self.assertIn("Task ID prefixes: `F` is a feature", rule_txt)
        self.assertIn("rejects `- Role:` lines in active `TODO.md` tasks", rule_txt)
        self.assertIn("inside the final commit step", rule_txt)
        self.assertNotIn("--role <role>] [--depends <spec>]", rule_txt)
        self.assertNotIn("role=audit", rule_txt)

    def _assert_help_aligned(self, text: str) -> None:
        lines = text.splitlines()
        width = self.todo_md_mod.help_display_width
        too_long = [ln for ln in lines if width(ln) > 100]
        self.assertEqual(too_long, [])
        titles = (
            "Commands:",
            "Global options:",
            "Quest-Log options",
            "Task ID prefixes and roles",
            "Files:",
            "Environment variables:",
        )
        for title in titles:
            with self.subTest(section=title):
                heads = [i for i, ln in enumerate(lines) if ln.startswith(title)]
                self.assertEqual(len(heads), 1)
                body = []
                for ln in lines[heads[0] + 1:]:
                    if not ln.startswith("  "):
                        break
                    body.append(ln)
                self.assertTrue(body)
                cols = set()
                for ln in body:
                    if ln.startswith("   "):
                        continue
                    m = re.match(r"^  (\S+(?: \S+)*)( {2,})\S", ln)
                    self.assertIsNotNone(m, msg=ln)
                    cols.add(m.end(2))
                self.assertEqual(len(cols), 1, msg="\n".join(body))
                col = cols.pop()
                for ln in body:
                    if ln.startswith("   "):
                        self.assertEqual(len(ln) - len(ln.lstrip(" ")), col, msg=ln)

    def test_help_structured_sections_and_alignment(self):
        rh = self._run_subprocess([str(SCRIPT), "--help"], check=True)
        self.assertEqual(rh.stderr, "")
        lines = rh.stdout.splitlines()
        for section in ("Usage:", "Commands:", "Global options:", "Files:", "Environment variables:"):
            with self.subTest(section=section):
                self.assertIn(section, lines)
        self.assertTrue(any(ln.startswith("Quest-Log options") for ln in lines))
        self._assert_help_aligned(rh.stdout)
        with mock.patch.object(self.todo_md_mod, "prog_name", return_value="todo_md_custom"):
            self._assert_help_aligned(self.todo_md_mod.usage_text())

    def test_lazy_urllib_import_and_offline_update(self):
        probe = (
            "import contextlib, importlib.machinery, importlib.util, io, sys\n"
            "loader = importlib.machinery.SourceFileLoader('todo_md_probe', sys.argv[1])\n"
            "spec = importlib.util.spec_from_loader('todo_md_probe', loader)\n"
            "mod = importlib.util.module_from_spec(spec)\n"
            "loader.exec_module(mod)\n"
            "buf = io.StringIO()\n"
            "with contextlib.redirect_stdout(buf):\n"
            "    assert mod.main(['--version']) == 0\n"
            "    assert mod.main(['init']) == 0\n"
            "    assert mod.main(['add', 'Lazy import task']) == 0\n"
            "    assert mod.main(['check']) == 0\n"
            "    assert mod.main(['list']) == 0\n"
            "for banned in ('urllib.request', 'http.client', 'ssl'):\n"
            "    assert banned not in sys.modules, f'unexpectedly imported {banned}'\n"
        )
        r_probe = self._run_subprocess([sys.executable, "-c", probe, str(SCRIPT)])
        self.assertEqual(r_probe.returncode, 0, msg=r_probe.stderr)

        remote_file = self.tmp / "remote_todo_md"
        remote_payload = (
            "#!/usr/bin/env python3\n"
            "# todo_md-repo: vitalio/todo_md\n"
            "VERSION = '99.0.0'\n"
        )
        remote_file.write_text(remote_payload, encoding="utf-8")
        env = {**os.environ, "TODO_MD_UPDATE_URL": remote_file.as_uri()}

        r_chk = self._run_subprocess([str(SCRIPT), "check-update"], env=env)
        self.assertEqual(r_chk.returncode, 0, msg=r_chk.stderr)
        self.assertIn("update available:", r_chk.stdout)
        self.assertIn("99.0.0", r_chk.stdout)

        dest_bin = self.tmp / "todo_md_local"
        dest_bin.write_text("# old\n", encoding="utf-8")
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            rc = self.todo_md_mod.cmd_update(url=remote_file.as_uri(), target_path=dest_bin)
        self.assertEqual(rc, 0, msg=err_buf.getvalue())
        self.assertIn("-> 99.0.0", out_buf.getvalue())
        self.assertEqual(dest_bin.read_text(encoding="utf-8"), remote_payload)

    def test_global_project_selector_and_precedence(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "parent_proj" / "sub_proj"
        proj_c = ws / "proj_c"
        dup_1 = ws / "g1" / "shared"
        dup_2 = ws / "g2" / "shared"
        outside = self.tmp / "outside"
        for d in (proj_a, proj_b, proj_c, dup_1, dup_2, outside):
            d.mkdir(parents=True)
        for d in (proj_a, proj_b, proj_c, dup_1, dup_2):
            self._run([str(SCRIPT), "-C", str(d), "init"], cwd=str(outside), check=True)

        (proj_a / "mod.py").write_text("x = 1\n", encoding="utf-8")
        env_ws = {**os.environ, "TODO_MD_WORKSPACE": str(ws)}

        # -C <dir> and --project <name> across mutating and read-only subcommands from outside
        self._run(
            [str(SCRIPT), "-C", str(proj_a), "add", "-p", "B", "Bug from -C", "-b", "- Target files: `mod.py`."],
            cwd=str(outside),
            check=True,
        )
        self._run(
            [str(SCRIPT), "--project", "parent_proj/sub_proj", "add", "Sub task", "--depends", "proj_a:B1"],
            cwd=str(outside),
            env=env_ws,
            check=True,
        )
        # Unique leaf project name resolves across workspace
        self._run(
            [str(SCRIPT), "--project=sub_proj", "edit", "F1", "-t", "Sub task updated"],
            cwd=str(outside),
            env=env_ws,
            check=True,
        )
        self._run([str(SCRIPT), "-C", "sub_proj", "append", "F1", "-b", "More notes."], cwd=str(outside), env=env_ws, check=True)
        self._run([str(SCRIPT), "-C", "sub_proj", "status", "F1", "HOLD"], cwd=str(outside), env=env_ws, check=True)
        self._run([str(SCRIPT), "-C", "sub_proj", "next", "F1"], cwd=str(outside), env=env_ws, check=True)

        # Read-only commands with -C / --project from outside
        r_ids = self._run([str(SCRIPT), "-C", "proj_a", "ids"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("B:1", r_ids.stdout)
        r_list = self._run([str(SCRIPT), "-C", "proj_a", "list"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("B1", r_list.stdout)
        r_show = self._run([str(SCRIPT), "-C", "proj_a", "show", "B1"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("Bug from -C", r_show.stdout)
        r_files = self._run([str(SCRIPT), "-C", "proj_a", "files", "B1"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_files.stdout.splitlines(), ["mod.py"])
        r_last_id = self._run([str(SCRIPT), "-C", "proj_a", "last-id", "NEW"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_last_id.stdout.strip(), "B1")
        r_last = self._run([str(SCRIPT), "-C", "proj_a", "last", "NEW"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("Bug from -C", r_last.stdout)
        self._run([str(SCRIPT), "-C", "proj_a", "check"], cwd=str(outside), env=env_ws, check=True)
        r_nid_sub = self._run([str(SCRIPT), "-C", "sub_proj", "next-id", "F1"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_nid_sub.stdout.strip(), "proj_a:B1")
        r_nid_blocked = self._run([str(SCRIPT), "-C", "sub_proj", "next-id"], cwd=str(outside), env=env_ws)
        self.assertEqual(r_nid_blocked.returncode, 1, msg=r_nid_blocked.stderr)

        # Complete and archive via -C, then verify sub_proj next-id unblocks, inspect archive and reopen
        self._run([str(SCRIPT), "-C", "proj_a", "done", "B1", "-m", "fixed"], cwd=str(outside), env=env_ws, check=True)
        r_nid_top = self._run([str(SCRIPT), "-C", "sub_proj", "next-id"], cwd=str(outside), env=env_ws, check=True)
        self.assertEqual(r_nid_top.stdout.strip(), "F1")
        r_arch = self._run([str(SCRIPT), "-C", "proj_a", "archive"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("B1: Bug from -C", r_arch.stdout)
        self._run([str(SCRIPT), "-C", "sub_proj", "cancel", "F1", "-m", "dropped"], cwd=str(outside), env=env_ws, check=True)
        r_sub_arch = self._run([str(SCRIPT), "-C", "sub_proj", "archive"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("F1: Sub task updated", r_sub_arch.stdout)

        # Overview, queue, and reopen with -C from outside
        r_sum = self._run([str(SCRIPT), "-C", "proj_a", "overview"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("Archived in TODO_ARCHIVE.md: 1 task(s)", r_sum.stdout)
        self._run([str(SCRIPT), "-C", "proj_a", "reopen", "B1"], cwd=str(outside), env=env_ws, check=True)
        self._run([str(SCRIPT), "-C", "sub_proj", "reopen", "F1"], cwd=str(outside), env=env_ws, check=True)
        r_q = self._run([str(SCRIPT), "-C", "sub_proj", "queue", "F1", "--all"], cwd=str(outside), env=env_ws, check=True)
        self.assertIn("proj_a:B1", r_q.stdout)

        # Workspace discovery from sibling project without TODO_MD_WORKSPACE env var
        r_sib = self._run([str(SCRIPT), "-C", "proj_a", "ids"], cwd=str(proj_c), check=True)
        self.assertIn("B:1", r_sib.stdout)

        # Precedence: -C/--project > TODO_MD_CWD > <project>:<ID> > cwd
        env_cwd_a = {**os.environ, "TODO_MD_WORKSPACE": str(ws), "TODO_MD_CWD": str(proj_a)}
        r_prec_env = self._run([str(SCRIPT), "ids"], cwd=str(proj_b), env=env_cwd_a, check=True)
        self.assertIn("B:1", r_prec_env.stdout)
        self.assertNotIn("F:1", r_prec_env.stdout)

        r_prec_cli = self._run([str(SCRIPT), "-C", "sub_proj", "ids"], cwd=str(outside), env=env_cwd_a, check=True)
        self.assertIn("F:1", r_prec_cli.stdout)
        self.assertNotIn("B:1", r_prec_cli.stdout)

        r_prec_ref = self._run([str(SCRIPT), "show", "proj_a:B1"], cwd=str(proj_c), check=True)
        self.assertIn("Bug from -C", r_prec_ref.stdout)

        # Explicit error on missing/empty/ambiguous targets and invalid <project>: on non-task commands
        for bad_args in (
            ["-C"],
            ["--project"],
            ["--project="],
            ["-C", ""],
            ["-C", "/nonexistent_todo_md_dir"],
            ["-C", "does_not_exist", "list"],
            ["--project", "shared", "list"],
            ["list", "proj_a:"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(outside), env=env_ws)
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_install_sh(self):
        bin_dir = self.tmp / "bin"
        bin_dir.mkdir()
        env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
        r = self._run_subprocess(["sh", str(INSTALL_SH), "--dir", str(bin_dir), "--yes"], env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((bin_dir / "todo_md").is_file())


    def test_default_quest_log_overview_multi_show_focus_highlight_and_status_filters(self):
        proj = self.tmp / "ql"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        for title, extra in (
            ("Alpha", []),
            ("Beta", ["--depends", "F1"]),
            ("Gamma", ["--status", "HOLD"]),
            ("Delta", []),
        ):
            self._run([str(SCRIPT), "add", title, *extra], cwd=str(proj), check=True)

        # Default view is the Quest-Log; overview / --full render the Markdown overview
        out = self._run([str(SCRIPT)], cwd=str(proj), check=True).stdout
        self.assertIn("Chain 1 -> F2: Beta", out)
        self.assertIn("Standalone tasks:", out)
        out_ov = self._run([str(SCRIPT), "overview"], cwd=str(proj), check=True).stdout
        self.assertNotIn("Chain 1 ->", out_ov)
        self.assertIn("F1", out_ov)
        out_full = self._run([str(SCRIPT), "--full"], cwd=str(proj), check=True).stdout
        self.assertNotIn("Chain 1 ->", out_full)
        self.assertIn("F1: Alpha", out_full)

        # Multi-ID show: space- and comma-separated, blank-line separated, same output
        out_multi = self._run([str(SCRIPT), "F1", "F2"], cwd=str(proj), check=True).stdout
        out_multi_show = self._run([str(SCRIPT), "show", "F1,F2"], cwd=str(proj), check=True).stdout
        self.assertEqual(out_multi, out_multi_show)
        self.assertLess(out_multi.index("Task: F1"), out_multi.index("Task: F2"))
        self.assertIn("\n\nTask: F2", out_multi)
        r_miss = self._run([str(SCRIPT), "show", "F1", "F99"], cwd=str(proj))
        self.assertNotEqual(r_miss.returncode, 0)
        self.assertIn("Task: F1", r_miss.stdout)

        # -f / --filter scopes the view and prints Next actionable for a single ID
        out_focus = self._run([str(SCRIPT), "--filter", "F4"], cwd=str(proj), check=True).stdout
        out_focus_short = self._run([str(SCRIPT), "-f", "F4"], cwd=str(proj), check=True).stdout
        self.assertEqual(out_focus, out_focus_short)
        self.assertIn("Delta", out_focus)
        self.assertNotIn("Chain 1 -> F2", out_focus)
        self.assertIn("Next actionable: F4", out_focus)
        out_chain_id = self._run([str(SCRIPT), "chain", "F2"], cwd=str(proj), check=True).stdout
        self.assertIn("Chain 1 -> F2: Beta", out_chain_id)
        self.assertNotIn("Delta", out_chain_id)
        self.assertIn("Next actionable: F1", out_chain_id)

        # -H / --highlight is a boolean focus-disabling toggle (and accepts -H <ID>... shorthand)
        out_hl = self._run([str(SCRIPT), "--highlight", "F4"], cwd=str(proj), check=True).stdout
        out_hl_toggle = self._run([str(SCRIPT), "-f", "F4", "-H"], cwd=str(proj), check=True).stdout
        out_hl_pre = self._run([str(SCRIPT), "-H", "-f", "F4"], cwd=str(proj), check=True).stdout
        self.assertEqual(out_hl, out_hl_toggle)
        self.assertEqual(out_hl, out_hl_pre)
        self.assertIn("Chain 1 -> F2: Beta", out_hl)
        self.assertIn("Delta", out_hl)
        self.assertNotIn("Next actionable:", out_hl)

        # Status filters (keyword and --status) and top-level -l N
        out_hold = self._run([str(SCRIPT), "HOLD"], cwd=str(proj), check=True).stdout
        self.assertIn("Gamma", out_hold)
        self.assertNotIn("Alpha", out_hold)
        out_wip = self._run([str(SCRIPT), "--status", "WIP"], cwd=str(proj), check=True).stdout
        self.assertIn("Chain: (none)", out_wip)
        r_done = self._run([str(SCRIPT), "DONE"], cwd=str(proj))
        self.assertEqual(r_done.returncode, 0, msg=r_done.stderr)
        out_lim = self._run([str(SCRIPT), "-l", "1"], cwd=str(proj), check=True).stdout
        self.assertNotIn("Delta", out_lim)
        for bad in (["--status", "bogus"], ["chain", "--filter"], ["chain", "-f"], ["--numbered=middle"]):
            with self.subTest(bad=bad):
                self.assertNotEqual(self._run([str(SCRIPT), *bad], cwd=str(proj)).returncode, 0)


    def test_search_scopes_quest_log_prints_full_sections_and_includes_archive(self):
        proj = self.tmp / "srch"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        self._run(
            [str(SCRIPT), "add", "Parser rewrite", "--next", "-b", "Mentions tokenizer details."],
            cwd=str(proj),
            check=True,
        )
        self._run([str(SCRIPT), "add", "Docs polish", "--next", "--depends", "F1"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Unrelated cleanup", "--next"], cwd=str(proj), check=True)

        # Body match scopes the Quest-Log to the chain containing the task; case-insensitive
        out = self._run([str(SCRIPT), "--search", "tokenizer"], cwd=str(proj), check=True).stdout
        self.assertIn("Parser rewrite", out)
        self.assertNotIn("Unrelated cleanup", out)
        out_cmd = self._run([str(SCRIPT), "search", "TOKENIZER"], cwd=str(proj), check=True).stdout
        self.assertEqual(out, out_cmd)
        out_short = self._run([str(SCRIPT), "-s", "tokenizer"], cwd=str(proj), check=True).stdout
        self.assertEqual(out, out_short)

        # Title match and regex support
        out_title = self._run([str(SCRIPT), "-s", "^unrelated cleanup$"], cwd=str(proj), check=True).stdout
        self.assertIn("Unrelated cleanup", out_title)
        self.assertNotIn("Parser rewrite", out_title)
        out_invalid_re = self._run([str(SCRIPT), "-s", "tokenizer ("], cwd=str(proj))
        self.assertNotEqual(out_invalid_re.returncode, 0)

        # --full prints full task sections of matches
        out_full = self._run([str(SCRIPT), "--full", "--search", "tokenizer"], cwd=str(proj), check=True).stdout
        self.assertIn("Task: F1", out_full)
        self.assertIn("Mentions tokenizer details.", out_full)
        self.assertNotIn("Chain 1", out_full)

        # -s with -H renders full Quest-Log with matches highlighted instead of focusing
        out_s_hl = self._run([str(SCRIPT), "-s", "tokenizer", "-H"], cwd=str(proj), check=True).stdout
        self.assertIn("Parser rewrite", out_s_hl)
        self.assertIn("Unrelated cleanup", out_s_hl)

        # No match -> non-zero exit; archive searched with --all or archive status
        self.assertNotEqual(self._run([str(SCRIPT), "-s", "no-such-text"], cwd=str(proj)).returncode, 0)
        self._run([str(SCRIPT), "done", "F3"], cwd=str(proj), check=True)
        self.assertNotEqual(self._run([str(SCRIPT), "-s", "unrelated"], cwd=str(proj)).returncode, 0)
        out_arch_ql = self._run([str(SCRIPT), "--all", "-s", "unrelated"], cwd=str(proj), check=True).stdout
        self.assertIn("F3", out_arch_ql)
        self.assertIn("Unrelated cleanup", out_arch_ql)
        self.assertNotIn("Parser rewrite", out_arch_ql)
        out_arch_filt = self._run([str(SCRIPT), "--all", "-f", "F3"], cwd=str(proj), check=True).stdout
        self.assertIn("F3", out_arch_filt)
        self.assertIn("Unrelated cleanup", out_arch_filt)
        self.assertNotIn("Parser rewrite", out_arch_filt)
        out_arch = self._run([str(SCRIPT), "--full", "--all", "-s", "unrelated"], cwd=str(proj), check=True).stdout
        self.assertIn("Task: F3", out_arch)


if __name__ == "__main__":
    unittest.main()
