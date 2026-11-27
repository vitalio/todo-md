#!/usr/bin/env python3
"""Tests for workspace discovery, dependency DAG sequencing, list topological order, and unlock reporting."""

import contextlib
import io
import os
import unittest
import unittest.mock
from tests.helpers import ROOT, SCRIPT, TodoMdTestCase


class TestDeps(TodoMdTestCase):
    def test_workspace_discovery_addressing_and_depends(self):
        ws = self.tmp / "ws"
        ws.mkdir()
        proj_a = ws / "proj_a"
        proj_b = ws / "parent_proj"
        proj_c = ws / "parent_proj" / "sub_proj"
        hidden = ws / ".hidden_proj"
        vendor = ws / "node_modules" / "pkg"
        for d in (proj_a, proj_b, proj_c, hidden, vendor):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), str(d), "init"], check=True)

        # Nested subproject without TODO.md does NOT climb to parent git root
        sub_no_todo = proj_b / "sub_empty"
        sub_no_todo.mkdir()
        self._run(["git", "init"], cwd=str(proj_b), check=True)
        r_sub_chk = self._run([str(SCRIPT), "check"], cwd=str(sub_no_todo))
        self.assertNotEqual(r_sub_chk.returncode, 0, msg=r_sub_chk.stderr)

        # Add tasks in projects
        self._run([str(SCRIPT), "add", "Base rule", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Base parent task"], cwd=str(proj_b), check=True)

        # Standalone project without .todo_projects lists only itself (1 project(s))
        # and rejects -w, -p <project>, and <project>:<ID>
        r_standalone_projs = self._run([str(SCRIPT), "projects"], cwd=str(proj_b), check=True)
        self.assertIn("(1 project(s))", r_standalone_projs.stdout)
        self.assertIn("parent_proj", r_standalone_projs.stdout)
        self.assertNotIn("proj_a", r_standalone_projs.stdout)
        self.assertNotIn("sub_proj", r_standalone_projs.stdout)
        for bad_standalone in (
            ["-w"],
            ["-w", "overview"],
            ["-w", "list"],
            ["-w", "check"],
            ["-p", "proj_a", "list"],
            ["proj_a:F1"],
        ):
            with self.subTest(bad_standalone=bad_standalone):
                r_bad_st = self._run([str(SCRIPT), *bad_standalone], cwd=str(proj_b))
                self.assertNotEqual(r_bad_st.returncode, 0, msg=r_bad_st.stdout)
                self.assertIn(".todo_projects", r_bad_st.stderr)

        # Cross-project dependency in a non-orchestrator repository is rejected on add, edit, and check
        r_non_orch_add = self._run(
            [str(SCRIPT), "add", "Sub feature", "--depends", "proj_a:F1"],
            cwd=str(proj_c),
        )
        self.assertNotEqual(r_non_orch_add.returncode, 0, msg=r_non_orch_add.stderr)
        self.assertIn("non-orchestrator repository", r_non_orch_add.stderr)
        self.assertIn(".todo_projects", r_non_orch_add.stderr)

        r_non_orch_chk = self._run([str(SCRIPT), "check"], cwd=str(proj_c))
        self.assertNotEqual(r_non_orch_chk.returncode, 0, msg=r_non_orch_chk.stderr)
        self.assertIn("non-orchestrator repository", r_non_orch_chk.stderr)

        r_non_orch_edit = self._run(
            [str(SCRIPT), "edit", "F1", "--depends", "proj_a:F1"],
            cwd=str(proj_c),
        )
        self.assertNotEqual(r_non_orch_edit.returncode, 0, msg=r_non_orch_edit.stderr)
        self.assertIn("non-orchestrator repository", r_non_orch_edit.stderr)

        # Clear cross-project dep on non-orchestrator proj_c -> check passes;
        # then configure .todo_projects.local on proj_c (and .todo_projects on ws) to allow cross-project dependencies
        self._run([str(SCRIPT), "edit", "F1", "--depends", ""], cwd=str(proj_c), check=True)
        self._run([str(SCRIPT), "check"], cwd=str(proj_c), check=True)
        (proj_c / ".todo_projects.local").write_text(
            "../proj_a\n..\n.\n",
            encoding="utf-8",
        )
        (ws / ".todo_projects").write_text(
            "proj_a\nparent_proj\nparent_proj/sub_proj\n",
            encoding="utf-8",
        )

        # Missing dependency fails validation immediately on edit in orchestrator
        r_bad_dep = self._run(
            [str(SCRIPT), "edit", "F1", "--depends", "proj_a:F1,F99"],
            cwd=str(proj_c),
        )
        self.assertNotEqual(r_bad_dep.returncode, 0, msg=r_bad_dep.stderr)
        self.assertIn("missing task 'F99'", r_bad_dep.stderr)

        # Edit F1 in orchestrator proj_c to depend only on proj_a:F1 (cross-project)
        self._run(
            [str(SCRIPT), "edit", "parent_proj/sub_proj:F1", "--depends", "proj_a:F1"],
            cwd=str(ws),
            check=True,
        )
        self._run([str(SCRIPT), "check"], cwd=str(proj_c), check=True)

        # Show surfaces blocked dependency status, then DONE after proj_a:F1 is completed
        r_show_blocked = self._run([str(SCRIPT), "parent_proj/sub_proj:F1"], cwd=str(ws), check=True)
        self.assertIn("Dependencies (blocked): proj_a:F1", r_show_blocked.stdout)
        self._run([str(SCRIPT), "done", "proj_a:F1", "-m", "done"], cwd=str(ws), check=True)
        r_show_ready = self._run([str(SCRIPT), "parent_proj/sub_proj:F1"], cwd=str(ws), check=True)
        self.assertIn("Dependencies (ready): proj_a:F1 ✅ [DONE]", r_show_ready.stdout)

        # Configured .todo_projects listing includes only configured projects and skips unconfigured .hidden_proj and node_modules
        r_projs = self._run([str(SCRIPT), "projects"], cwd=str(ws), check=True)
        self.assertIn("(3 project(s))", r_projs.stdout)
        self.assertIn("proj_a", r_projs.stdout)
        self.assertIn(str(proj_a.resolve()), r_projs.stdout)
        self.assertIn("parent_proj", r_projs.stdout)
        self.assertIn("parent_proj/sub_proj", r_projs.stdout)
        self.assertIn(str(proj_c.resolve()), r_projs.stdout)
        self.assertNotIn(".hidden_proj", r_projs.stdout)
        self.assertNotIn("node_modules", r_projs.stdout)

        # Workspace overview (-w from inside configured orchestrator, and auto-workspace from ws root with .todo_projects)
        r_ws_flag = self._run([str(SCRIPT), "-w", "overview"], cwd=str(proj_c), check=True)
        self.assertIn("sub_proj:F1", r_ws_flag.stdout)
        r_ws_auto = self._run([str(SCRIPT), "overview"], cwd=str(ws), check=True)
        self.assertIn("## parent_proj/sub_proj", r_ws_auto.stdout)

        # Workspace list and check
        r_ws_list = self._run([str(SCRIPT), "-w", "list", "active"], cwd=str(proj_c), check=True)
        self.assertIn("sub_proj:F1", r_ws_list.stdout)
        self._run([str(SCRIPT), "-w", "check"], cwd=str(proj_c), check=True)

    def test_dependency_sequencing_queue_next_id_and_cycles(self):
        ws = self.tmp / "ws"
        orch = ws / "orch"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        for d in (orch, proj_a, proj_b):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Intra-project sequential stages + parallel commas + multiple Depends on lines
        self._run([str(SCRIPT), "add", "Stage 1A"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Stage 1B"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Stage 2C"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Branch 2X"], cwd=str(proj_a), check=True)
        self._run(
            [
                str(SCRIPT),
                "add",
                "Target T",
                "--depends",
                "F1, F2 -> F3",
                "--depends",
                "F4",
            ],
            cwd=str(proj_a),
            check=True,
        )
        todo_a = (proj_a / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Depends on: F1, F2 -> F3", todo_a)
        self.assertIn("- Depends on: F4", todo_a)

        r_show_f5 = self._run([str(SCRIPT), "F5"], cwd=str(proj_a), check=True)
        self.assertIn(
            "Dependencies (blocked): F1 ⚪ [NEW], F2 ⚪ [NEW] -> F3 ⚪ [NEW]; F4 ⚪ [NEW]",
            r_show_f5.stdout,
        )

        # Queue shows stable topological order with [ready] / [blocked by: ...] and Next actionable
        r_q1 = self._run([str(SCRIPT), "queue", "F5"], cwd=str(proj_a), check=True)
        q1_refs = self._row_refs(r_q1.stdout)
        q1_flat = self._flat_text(r_q1.stdout)
        self.assertLess(q1_refs.index("F1"), q1_refs.index("F3"))
        self.assertLess(q1_refs.index("F2"), q1_refs.index("F3"))
        self.assertLess(q1_refs.index("F3"), q1_refs.index("F5"))
        self.assertIn("🟢 ready · 🔓 unblocks: 2", q1_flat)
        self.assertIn("🔒 blocked by: F1, F2 · 🔓 unblocks: 1", q1_flat)
        self.assertIn("Next actionable: F1", r_q1.stdout)

        r_nid1 = self._run([str(SCRIPT), "next-id", "F5"], cwd=str(proj_a), check=True)
        self.assertEqual(r_nid1.stdout.strip(), "F1")

        # Complete F1 and F2 -> DONE tasks hidden by default, shown with --all; F3 becomes ready
        self._run([str(SCRIPT), "done", "F1", "-m", "done1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F2", "-m", "done2"], cwd=str(proj_a), check=True)
        r_q2 = self._run([str(SCRIPT), "queue", "F5"], cwd=str(proj_a), check=True)
        self.assertNotIn("F1", r_q2.stdout)
        self.assertNotIn("F2", r_q2.stdout)
        self.assertIn("Next actionable: F3", r_q2.stdout)

        r_q2_all = self._run([str(SCRIPT), "queue", "F5", "--all"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_q2_all.stdout)
        self.assertIn("✅ DONE", r_q2_all.stdout)
        self.assertIn("Next actionable: F3", r_q2_all.stdout)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F5"], cwd=str(proj_a), check=True).stdout.strip(), "F3")

        # Complete F3 and F4 -> Dependencies (ready), next-id F5 returns F5 itself
        self._run([str(SCRIPT), "done", "F3", "-m", "done3"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F4", "-m", "done4"], cwd=str(proj_a), check=True)
        r_show_ready = self._run([str(SCRIPT), "F5"], cwd=str(proj_a), check=True)
        self.assertIn(
            "Dependencies (ready): F1 ✅ [DONE], F2 ✅ [DONE] -> F3 ✅ [DONE]; F4 ✅ [DONE]",
            r_show_ready.stdout,
        )
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F5"], cwd=str(proj_a), check=True).stdout.strip(), "F5")

        # Cross-project orchestrator preserving one-way boundaries + transitive intra-project deps
        (orch / ".todo_projects").write_text("proj_a\nproj_b\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "Repo A base"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Repo B prereq"], cwd=str(proj_b), check=True)
        self._run([str(SCRIPT), "add", "Repo B child", "--depends", "F1"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Release orch", "--depends", "proj_a:F6 -> proj_b:F2"],
            cwd=str(orch),
            check=True,
        )
        proj_b_before = (proj_b / "TODO.md").read_text(encoding="utf-8")

        r_orch_q = self._run([str(SCRIPT), "queue", "F1"], cwd=str(orch), check=True)
        orch_refs = self._row_refs(r_orch_q.stdout)
        self.assertLess(orch_refs.index("proj_a:F6"), orch_refs.index("proj_b:F2"))
        self.assertLess(orch_refs.index("proj_b:F1"), orch_refs.index("proj_b:F2"))
        self.assertIn("🔒 blocked by: proj_a:F6, proj_b:F1 · 🔓 unblocks: 1", self._flat_text(r_orch_q.stdout))
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_a:F6")
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "orch:F1"], cwd=str(orch), check=True).stdout.strip(),
            "proj_a:F6",
        )
        self.assertEqual((proj_b / "TODO.md").read_text(encoding="utf-8"), proj_b_before)

        # Complete proj_a:F6 -> proj_b:F1 is next; complete proj_b:F1 -> proj_b:F2 is next
        self._run([str(SCRIPT), "done", "proj_a:F6", "-m", "d6"], cwd=str(orch), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_b:F1")
        self._run([str(SCRIPT), "done", "proj_b:F1", "-m", "db1"], cwd=str(orch), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_b:F2")

        # CANCELED blocker causes next-id to fail non-zero and queue to mark [blocked]
        self._run([str(SCRIPT), "cancel", "proj_b:F2", "-m", "dropped"], cwd=str(orch), check=True)
        r_q_can = self._run([str(SCRIPT), "queue", "F1"], cwd=str(orch))
        self.assertEqual(r_q_can.returncode, 1, msg=r_q_can.stderr)
        self.assertIn("unresolved blocker", r_q_can.stderr)
        self.assertIn("❌ CANCELED", r_q_can.stdout)
        self.assertIn("🔒 blocked by: proj_b:F2", self._flat_text(r_q_can.stdout))
        self.assertIn("Next actionable: none", r_q_can.stdout)
        r_nid_can = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch))
        self.assertNotEqual(r_nid_can.returncode, 0, msg=r_nid_can.stderr)
        self.assertIn("CANCELED", r_nid_can.stderr)

        # Already-closed target fails non-zero in next-id
        r_nid_done = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(proj_a))
        self.assertNotEqual(r_nid_done.returncode, 0, msg=r_nid_done.stderr)
        self.assertIn("already closed", r_nid_done.stderr)

        # ';' and newline branch separators in --depends emit separate '- Depends on:' lines,
        # and ';' in an existing '- Depends on:' line is parsed as independent branches
        semi_dir = ws / "semi_proj"
        semi_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(semi_dir), check=True)
        for idx in range(1, 5):
            self._run([str(SCRIPT), "add", f"Node {idx}"], cwd=str(semi_dir), check=True)
        self._run(
            [str(SCRIPT), "add", "Diamond target", "--depends", "F1 -> F2; F1 -> F3\nF4"],
            cwd=str(semi_dir),
            check=True,
        )
        semi_todo = (semi_dir / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("- Depends on: F1 -> F2\n- Depends on: F1 -> F3\n- Depends on: F4", semi_todo)
        r_semi_show = self._run([str(SCRIPT), "F5"], cwd=str(semi_dir), check=True)
        self.assertIn(
            "Dependencies (blocked): F1 ⚪ [NEW] -> F2 ⚪ [NEW]; F1 ⚪ [NEW] -> F3 ⚪ [NEW]; F4 ⚪ [NEW]",
            r_semi_show.stdout,
        )
        # In-file ';' on a single Depends on: line also validates and rewrites on rename
        (semi_dir / "TODO.md").write_text(
            semi_todo.replace(
                "- Depends on: F1 -> F2\n- Depends on: F1 -> F3",
                "- Depends on: F1 -> F2; F1 -> F3",
            ),
            encoding="utf-8",
        )
        self._run([str(SCRIPT), "check"], cwd=str(semi_dir), check=True)
        self._run([str(SCRIPT), "rename", "F1", "F9"], cwd=str(semi_dir), check=True)
        self.assertIn("- Depends on: F9 -> F2; F9 -> F3", (semi_dir / "TODO.md").read_text(encoding="utf-8"))

        # Multi-stage duplicate task reference within the same '->' clause is rejected with precedence hint
        r_dup_stage = self._run(
            [str(SCRIPT), "add", "Ambiguous comma", "--depends", "F9 -> F2, F9 -> F3"],
            cwd=str(semi_dir),
        )
        self.assertNotEqual(r_dup_stage.returncode, 0, msg=r_dup_stage.stdout)
        self.assertIn(
            "duplicate task F9 across '->' stages in 'F9 -> F2, F9 -> F3' "
            "(',' groups parallel items within a stage and binds tighter than '->'; "
            "use ';' or repeat --depends to separate independent chains)",
            r_dup_stage.stderr,
        )

        # Syntax errors rejected by --depends
        for bad_dep in ("F1 ->", "-> F1", "F1, -> F2", "badref", "F1 -> F2; ", "; F1", "F1 -> F1"):
            with self.subTest(bad_dep=bad_dep):
                r_bad = self._run([str(SCRIPT), "add", "Bad dep", "--depends", bad_dep], cwd=str(proj_a))
                self.assertNotEqual(r_bad.returncode, 0, msg=r_bad.stderr)

        # Transitive cycle detection in todo_md check, queue, and next-id
        cyc_dir = ws / "cyc"
        cyc_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_dir), check=True)
        self._run([str(SCRIPT), "add", "Node A"], cwd=str(cyc_dir), check=True)
        self._run([str(SCRIPT), "add", "Node B", "--depends", "F1"], cwd=str(cyc_dir), check=True)
        r_cyc_edit = self._run([str(SCRIPT), "edit", "F1", "--depends", "F2"], cwd=str(cyc_dir))
        self.assertNotEqual(r_cyc_edit.returncode, 0, msg=r_cyc_edit.stderr)
        self.assertIn("dependency cycle", r_cyc_edit.stderr)
        r_chk_cyc = self._run([str(SCRIPT), "check"], cwd=str(cyc_dir))
        self.assertNotEqual(r_chk_cyc.returncode, 0, msg=r_chk_cyc.stderr)
        self.assertIn("dependency cycle", r_chk_cyc.stderr)
        r_q_cyc = self._run([str(SCRIPT), "queue", "F1"], cwd=str(cyc_dir))
        self.assertNotEqual(r_q_cyc.returncode, 0, msg=r_q_cyc.stderr)
        self.assertIn("dependency cycle", r_q_cyc.stderr)
        r_nid_cyc = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(cyc_dir))
        self.assertNotEqual(r_nid_cyc.returncode, 0, msg=r_nid_cyc.stderr)
        self.assertIn("dependency cycle", r_nid_cyc.stderr)

        # Stage-induced cycle (A depends on B, target says A -> B) caught by check
        cyc_stage = ws / "cyc_stage"
        cyc_stage.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_stage), check=True)
        self._run([str(SCRIPT), "add", "S2"], cwd=str(cyc_stage), check=True)
        self._run([str(SCRIPT), "add", "S1", "--depends", "F1"], cwd=str(cyc_stage), check=True)
        r_st_cyc = self._run([str(SCRIPT), "add", "S3", "--depends", "F2 -> F1"], cwd=str(cyc_stage))
        self.assertNotEqual(r_st_cyc.returncode, 0, msg=r_st_cyc.stderr)
        self.assertIn("dependency cycle", r_st_cyc.stderr)

        # Syntax error in TODO.md caught by check
        syn_dir = ws / "syn"
        syn_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(syn_dir), check=True)
        (syn_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Broken\n\n- Depends on: F2 -> \n", encoding="utf-8")
        r_syn = self._run([str(SCRIPT), "check"], cwd=str(syn_dir))
        self.assertNotEqual(r_syn.returncode, 0, msg=r_syn.stderr)
        self.assertIn("syntax error", r_syn.stderr)

    def test_list_topo_order_blocked_next_badges_and_ready_filter(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Build chain F1 -> F2 -> F3 and independent F4 in proj_a, with promoted blocked order
        self._run([str(SCRIPT), "add", "Base task", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Middle task", "--depends", "F1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Top task", "--depends", "F2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Ready task", "--next"], cwd=str(proj_a), check=True)
        # Promote F3 then F2 via next: F2 depends on F1 and F3 depends on F2, so TODO.md must keep
        # ready tasks (F4, F1) before blocked tasks (F2, F3), and F2 before F3
        self._run([str(SCRIPT), "next", "F3"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "next", "F2"], cwd=str(proj_a), check=True)

        todo_txt = (proj_a / "TODO.md").read_text(encoding="utf-8")
        self.assertIn("# 🎯 [NEXT] F3:", todo_txt)
        self.assertLess(todo_txt.index("F4:"), todo_txt.index("F2:"))
        self.assertLess(todo_txt.index("F1:"), todo_txt.index("F2:"))
        self.assertLess(todo_txt.index("F2:"), todo_txt.index("F3:"))

        # Local list: blocked NEXT items render with ⏳ [NEXT], chain F3 shows full path, single-step F2 stays single-hop
        r_list = self._run([str(SCRIPT), "list"], cwd=str(proj_a), check=True)
        rows = {
            line.split()[0]: line
            for line in r_list.stdout.splitlines()
            if line.startswith("  ")
        }
        self.assertIn("🎯 NEXT", rows["F4"])
        self.assertIn("🎯 NEXT", rows["F1"])
        self.assertIn("⏳ NEXT", rows["F2"])
        self.assertIn("[blocked: F1 (NEXT)]", rows["F2"])
        self.assertNotIn("->", rows["F2"])
        self.assertIn("⏳ NEXT", rows["F3"])
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", rows["F3"])
        self.assertLess(r_list.stdout.index("F4"), r_list.stdout.index("F2"))
        self.assertLess(r_list.stdout.index("F1"), r_list.stdout.index("F2"))
        self.assertLess(r_list.stdout.index("F2"), r_list.stdout.index("F3"))

        # Multi-stage Depends on: F1 -> F2 on a single task also surfaces the full ordered chain
        self._run([str(SCRIPT), "add", "Stage task", "--next", "--depends", "F1 -> F2"], cwd=str(proj_a), check=True)
        r_list_stage = self._run([str(SCRIPT), "list", "NEXT"], cwd=str(proj_a), check=True)
        stage_line = next(l for l in r_list_stage.stdout.splitlines() if l.strip().startswith("F5"))
        self.assertIn("⏳ NEXT", stage_line)
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", stage_line)

        # --ready filters local list to active tasks without unresolved deps
        r_ready = self._run([str(SCRIPT), "list", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_ready.stdout)
        self.assertIn("F4", r_ready.stdout)
        self.assertNotIn("F2", r_ready.stdout)
        self.assertNotIn("F3", r_ready.stdout)
        self.assertNotIn("F5", r_ready.stdout)

        # Cross-project dependency in proj_b + workspace list -w and -w --ready
        (proj_b / ".todo_projects").write_text("proj_a\nproj_b\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "Cross ready", "--next"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Cross blocked", "--next", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )
        r_ws = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_b), check=True)
        ws_rows = self._table_rows(r_ws.stdout)
        self.assertIn("⏳ NEXT", ws_rows["proj_a:F3"])
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", ws_rows["proj_a:F3"])
        self.assertIn("⏳ NEXT", ws_rows["proj_b:F2"])
        self.assertIn("[blocked: proj_a:F1 (NEXT) -> proj_a:F2 (NEXT) -> proj_a:F3 (NEXT)]", ws_rows["proj_b:F2"])
        self.assertIn("🎯 NEXT", ws_rows["proj_b:F1"])

        r_ws_ready = self._run([str(SCRIPT), "-w", "list", "NEXT", "--ready"], cwd=str(proj_b), check=True)
        self.assertIn("proj_a:F1", r_ws_ready.stdout)
        self.assertIn("proj_a:F4", r_ws_ready.stdout)
        self.assertIn("proj_b:F1", r_ws_ready.stdout)
        self.assertNotIn("proj_a:F2", r_ws_ready.stdout)
        self.assertNotIn("proj_b:F2", r_ws_ready.stdout)

        # Completing F1 unblocks F2 -> F2 becomes ready with [deps: DONE] and moves before F3/F5
        self._run([str(SCRIPT), "done", "F1", "-m", "d1"], cwd=str(proj_a), check=True)
        r_after_done = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_b), check=True)
        ws_after = self._table_rows(r_after_done.stdout)
        self.assertIn("🎯 NEXT", ws_after["proj_a:F2"])
        self.assertIn("[deps: DONE]", ws_after["proj_a:F2"])
        self.assertIn("⏳ NEXT", ws_after["proj_a:F3"])
        self.assertIn("[blocked: F2 (NEXT)]", ws_after["proj_a:F3"])
        self.assertNotIn("<- start:", ws_after["proj_a:F3"])

        r_none_ready = self._run([str(SCRIPT), "list", "archive", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("No matching tasks (archive, ready)", r_none_ready.stdout)

        # CANCELED blocker does not append <- start: and cycle falls back safely to file order
        cyc = ws / "cyc_list"
        cyc.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc), check=True)
        (cyc / "TODO.md").write_text(
            "# 🎯 [NEXT] F1: Cycle A\n\n- Depends on: F2\n\n"
            "# 🎯 [NEXT] F2: Cycle B\n\n- Depends on: F1\n\n"
            "# 🎯 [NEXT] F3: Ready C\n\nBody C\n",
            encoding="utf-8",
        )
        r_cyc_list = self._run([str(SCRIPT), "list"], cwd=str(cyc), check=True)
        self.assertLess(r_cyc_list.stdout.index("F3"), r_cyc_list.stdout.index("F1"))
        self.assertLess(r_cyc_list.stdout.index("F1"), r_cyc_list.stdout.index("F2"))
        self.assertIn("⏳ NEXT", r_cyc_list.stdout)

        # Blocked WIP badge (⏳ [WIP]) and full mixed-status unblock chain in local and workspace list
        wip_ws = ws / "wip_chain_ws"
        wip_proj = wip_ws / "alpha"
        wip_proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Root WIP", "--status", "WIP"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Mid NEXT", "--next", "--depends", "F1"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Child WIP", "--status", "WIP", "--depends", "F2"], cwd=str(wip_proj), check=True)
        self._run([str(SCRIPT), "add", "Leaf NEXT", "--next", "--depends", "F3"], cwd=str(wip_proj), check=True)

        r_wip_local = self._run([str(SCRIPT), "list"], cwd=str(wip_proj), check=True)
        wip_rows = self._table_rows(r_wip_local.stdout)
        self.assertIn("🔵 WIP", wip_rows["F1"])
        self.assertIn("⏳ WIP", wip_rows["F3"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT)]", wip_rows["F3"])
        self.assertIn("⏳ NEXT", wip_rows["F2"])
        self.assertIn("[blocked: F1 (WIP)]", wip_rows["F2"])
        self.assertIn("⏳ NEXT", wip_rows["F4"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT) -> F3 (WIP)]", wip_rows["F4"])

        (wip_ws / ".todo_projects").write_text("alpha\n", encoding="utf-8")
        r_wip_ws = self._run([str(SCRIPT), "list", "-w"], cwd=str(wip_ws), check=True)
        wip_ws_rows = self._table_rows(r_wip_ws.stdout)
        self.assertIn("🔵 WIP", wip_ws_rows["alpha:F1"])
        self.assertIn("⏳ WIP", wip_ws_rows["alpha:F3"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT)]", wip_ws_rows["alpha:F3"])
        self.assertIn("⏳ NEXT", wip_ws_rows["alpha:F4"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT) -> F3 (WIP)]", wip_ws_rows["alpha:F4"])

    def test_done_prints_newly_unblocked_local_and_orchestrator_tasks(self):
        ws = self.tmp / "ws_done"
        repo_a = ws / "repo_a"
        repo_b = ws / "repo_b"
        orch_dir = ws / "orch"
        for d in (repo_a, repo_b, orch_dir):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)
        (orch_dir / ".todo_projects").write_text("repo_a\nrepo_b\n", encoding="utf-8")

        # Local chain in repo_a: F1 and F2 both required for F4; F3 depends only on F1
        self._run([str(SCRIPT), "add", "Prereq 1"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Prereq 2"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Single waiter", "--depends", "F1"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Dual waiter", "--depends", "F1, F2"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Already ready"], cwd=str(repo_a), check=True)

        # Workspace orchestrator task in orch depending on repo_a:F1, repo_b:F1
        self._run([str(SCRIPT), "add", "Repo B step"], cwd=str(repo_b), check=True)
        self._run([str(SCRIPT), "add", "Repo B step 2"], cwd=str(repo_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Orch release", "--depends", "repo_a:F1, repo_b:F1, repo_b:F2"],
            cwd=str(orch_dir),
            check=True,
        )

        # Completing F1 in standalone repo_a unblocks local F3, does NOT unblock F4 or scan parent for orch
        r_done1 = self._run([str(SCRIPT), "done", "F1", "-m", "d1"], cwd=str(repo_a), check=True)
        self.assertIn("Unblocked: F3", r_done1.stdout)
        self.assertNotIn("F4", r_done1.stdout)
        self.assertNotIn("F5", r_done1.stdout)
        self.assertNotIn("orch:F1", r_done1.stdout)

        # Completing F2 unblocks local F4
        r_done2 = self._run([str(SCRIPT), "done", "F2", "-m", "d2"], cwd=str(repo_a), check=True)
        self.assertIn("Unblocked: F4", r_done2.stdout)

        # Completing F3 has no downstream dependents -> no Unblocked: line
        r_done3 = self._run([str(SCRIPT), "done", "F3", "-m", "d3"], cwd=str(repo_a), check=True)
        self.assertNotIn("Unblocked:", r_done3.stdout)

        # Completing repo_b:F1 inside standalone repo_b does not scan parent directories for orch
        r_done_b_local = self._run([str(SCRIPT), "done", "F1", "-m", "db1"], cwd=str(repo_b), check=True)
        self.assertNotIn("orch:F1", r_done_b_local.stdout)

        # Completing repo_b:F2 from orchestrator completes all deps for orch:F1 and reports it
        r_done_b = self._run([str(SCRIPT), "done", "repo_b:F2", "-m", "db2"], cwd=str(orch_dir), check=True)
        self.assertIn("Unblocked: orch:F1", r_done_b.stdout)

    def test_nested_orchestrators_external_alias_and_cycle_safety(self):
        import os
        from unittest import mock

        mod = self.todo_md_mod
        for removed_fn in (
            "discover_projects",
            "_scan_projects",
            "discover_orchestrators_for_project",
            "_scan_orchestrators_for_project",
            "_inbound_blocker_items",
            "_rewrite_orchestrator_deps",
        ):
            self.assertFalse(hasattr(mod, removed_fn), f"{removed_fn} must be removed")

        ws = (self.tmp / "ws_tiers").resolve()
        home = (self.tmp / "home_tiers").resolve()
        canary = home / "chrome" / "canary"
        meta_orch = ws / "meta_orch"
        todo_flow = ws / "todo_flow"
        todo_md_p = ws / "todo_md"
        run_block = ws / "run_block"
        for d in (meta_orch, todo_flow, todo_md_p, run_block, canary):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)
        (todo_flow / ".todo_projects").write_text("todo_md\nrun_block\n", encoding="utf-8")
        (meta_orch / ".todo_projects").write_text("todo_flow\n~/chrome/canary\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            for key in ("TODO_MD_PROJECTS", "TODO_MD_WORKSPACE", "TODO_MD_CWD"):
                os.environ.pop(key, None)
            cfg = mod.read_configured_todo_projects(meta_orch, ws, include_env=False)
            self.assertEqual(
                {p.name for p in cfg},
                {"meta_orch", "todo_flow", "todo_md", "run_block", "canary"},
            )
            flow_cfg = mod.read_configured_todo_projects(todo_flow, ws, include_env=False)
            self.assertEqual(
                {p.name for p in flow_cfg},
                {"todo_flow", "todo_md", "run_block"},
            )
            self.assertEqual(mod.resolve_project_dir(meta_orch, "chrome/canary"), canary.resolve())
            self.assertEqual(mod.resolve_project_dir(meta_orch, "canary"), canary.resolve())
            with self.assertRaises(SystemExit):
                mod.resolve_project_dir(todo_flow, "chrome/canary")
            with self.assertRaises(SystemExit):
                mod.resolve_project_dir(todo_md_p, "chrome/canary")
            self.assertEqual(mod.project_label(canary.resolve(), ws), "chrome/canary")
            self.assertEqual(mod.project_label(todo_md_p, ws), "todo_md")

    def test_orchestrator_inbound_edges_in_queue_next_id_list_and_show(self):
        ws = self.tmp / "ws_inbound"
        todo_flow = ws / "todo_flow"
        todo_md_p = ws / "todo_md"
        for d in (todo_flow, todo_md_p):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)
        (todo_flow / ".todo_projects").write_text("todo_flow\ntodo_md\n", encoding="utf-8")
        self._run([str(SCRIPT), "add", "F", "Flow prerequisite", "--next"], cwd=str(todo_flow), check=True)
        self._run([str(SCRIPT), "add", "F", "Md downstream", "--next"], cwd=str(todo_md_p), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Flow sequencing", "--next", "--depends", "F1 -> todo_md:F1"],
            cwd=str(todo_flow),
            check=True,
        )

        # Child todo_md_p is 100% self-contained (no reverse child-to-orchestrator coupling)
        r_next_child = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(todo_md_p), check=True)
        self.assertEqual(r_next_child.stdout.strip(), "F1")

        r_show_child = self._run([str(SCRIPT), "F1"], cwd=str(todo_md_p), check=True)
        self.assertNotIn("Dependencies (blocked):", r_show_child.stdout)
        self.assertNotIn("todo_flow:F1", r_show_child.stdout)

        r_list_child = self._run([str(SCRIPT), "list", "active"], cwd=str(todo_md_p), check=True)
        self.assertNotIn("blocked:", self._flat_text(r_list_child.stdout))

        # From orchestrator todo_flow, cross-project stage edges and blockers are surfaced
        r_orch_next = self._run([str(SCRIPT), "next-id", "F2"], cwd=str(todo_flow), check=True)
        self.assertEqual(r_orch_next.stdout.strip(), "F1")

        r_orch_chain = self._run([str(SCRIPT), "chain", "-f", "todo_md:F1"], cwd=str(todo_flow), check=True)
        self.assertIn("🔒 blocked by: F1", self._flat_text(r_orch_chain.stdout))

        r_ov = self._run([str(SCRIPT), "overview", "-w"], cwd=str(todo_flow), check=True)
        self.assertIn("## todo_flow ", r_ov.stdout)
        self.assertIn("## todo_md ", r_ov.stdout)

        mod = self.todo_md_mod
        md_tasks = [t for t in mod.collect_all_tasks(todo_md_p) if t["file"] == "TODO.md"]
        flow_tasks = [t for t in mod.collect_all_tasks(todo_flow) if t["file"] == "TODO.md"]
        with unittest.mock.patch.object(
            mod, "collect_all_tasks", wraps=mod.collect_all_tasks
        ) as mock_collect:
            with mod.discovery_session():
                def _query_pass() -> None:
                    for t in md_tasks:
                        mod._task_dag(todo_md_p, t)
                        mod._is_task_blocked(todo_md_p, t)
                        mod._task_dependency_info(todo_md_p, t)
                    for ft in flow_tasks:
                        mod._task_dag(todo_flow, ft)
                    mod.resolve_dependency_statuses(todo_flow, ["F1", "todo_md:F1"])
                    self.assertEqual(mod.resolve_top_task_id(todo_md_p), "F1")
                    self.assertEqual(mod.resolve_top_task_id(todo_flow), "F1")
                    buf = io.StringIO()
                    with contextlib.redirect_stdout(buf):
                        rc = mod._show_tasks(
                            todo_flow,
                            ["F1", "F2", "todo_md:F1"],
                            None,
                            mod.BundleOptions(enabled=False),
                        )
                    self.assertEqual(rc, 0)

                _query_pass()
                first_collects = mock_collect.call_count
                self.assertEqual(first_collects, 2)
                _query_pass()
                _query_pass()
                self.assertEqual(mock_collect.call_count, first_collects)

            mock_collect.reset_mock()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = mod._show_tasks(
                    todo_flow,
                    ["F1", "F2", "todo_md:F1"],
                    None,
                    mod.BundleOptions(enabled=False),
                )
            self.assertEqual(rc, 0)
            self.assertEqual(mock_collect.call_count, 2)

        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(todo_flow), check=True)
        r_orch_after = self._run([str(SCRIPT), "next-id", "F2"], cwd=str(todo_flow), check=True)
        self.assertEqual(r_orch_after.stdout.strip(), "todo_md:F1")

    def test_alias_path_mapping_in_todo_projects_and_local_and_scoped_projects_view(self):
        ws = (self.tmp / "ws_alias_map").resolve()
        ext_root = (self.tmp / "ext_checkouts").resolve()
        orch = ws / "todo-flow"
        local_checkout = ws / "todo_md_checkout"
        sibling_unlisted = ws / "unlisted_sibling"
        ext_checkout = ext_root / "rb-custom-dir"
        for d in (orch, local_checkout, sibling_unlisted, ext_checkout):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Map canonical project IDs to local relative directory and external path
        (orch / ".todo_projects").write_text(
            "# Canonical alias mappings\ntodo-md=../todo_md_checkout\n",
            encoding="utf-8",
        )
        (orch / ".todo_projects.local").write_text(
            f"run-block={ext_checkout}\n",
            encoding="utf-8",
        )

        # Add tasks via canonical aliases (-p <alias>, add <alias>, and show/edit <alias>:<ID>)
        self._run(
            [str(SCRIPT), "add", "todo-md", "F", "Task in aliased local checkout", "--next"],
            cwd=str(orch),
            check=True,
        )
        self._run(
            [str(SCRIPT), "-p", "run-block", "add", "B", "Bug in aliased external checkout", "--next"],
            cwd=str(orch),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Unlisted sibling task", "--next"],
            cwd=str(sibling_unlisted),
            check=True,
        )

        # Orchestrator depends on canonical aliases todo-md:F1 -> run-block:B1
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Orchestrator milestone via canonical aliases",
                "--next",
                "--depends",
                "todo-md:F1 -> run-block:B1",
            ],
            cwd=str(orch),
            check=True,
        )
        self._run([str(SCRIPT), "check"], cwd=str(orch), check=True)

        # `todo projects` inside orchestrator lists only managed projects + orchestrator with resolved paths
        r_projs = self._run([str(SCRIPT), "projects"], cwd=str(orch), check=True)
        self.assertIn("(3 project(s))", r_projs.stdout)
        self.assertIn("todo-flow", r_projs.stdout)
        self.assertIn(str(orch.resolve()), r_projs.stdout)
        self.assertIn("todo-md", r_projs.stdout)
        self.assertIn(str(local_checkout.resolve()), r_projs.stdout)
        self.assertIn("run-block", r_projs.stdout)
        self.assertIn(str(ext_checkout.resolve()), r_projs.stdout)
        self.assertNotIn("unlisted_sibling", r_projs.stdout)

        # Quest-Log and dependency resolution use canonical alias labels and resolve across checkouts
        r_chain = self._run([str(SCRIPT), "chain"], cwd=str(orch), check=True)
        self.assertIn("todo-md:F1", r_chain.stdout)
        self.assertIn("run-block:B1", r_chain.stdout)
        self.assertNotIn("unlisted_sibling", r_chain.stdout)

        r_next = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True)
        self.assertEqual(r_next.stdout.strip(), "todo-md:F1")

        # Child checkouts remain self-contained and never scan parent directories for orchestrator
        r_child_next = self._run(
            [str(SCRIPT), "next-id", "B1"],
            cwd=str(ext_checkout),
            env={**os.environ, "TODO_MD_WORKSPACE": str(ws)},
            check=True,
        )
        self.assertEqual(r_child_next.stdout.strip(), "B1")
        r_child_projs = self._run([str(SCRIPT), "projects"], cwd=str(ext_checkout), check=True)
        self.assertIn("(1 project(s))", r_child_projs.stdout)
        self.assertIn("rb-custom-dir", r_child_projs.stdout)
        self.assertNotIn("todo-flow", r_child_projs.stdout)

        # Rename in aliased child does not mutate external orchestrator TODO.md; orchestrator updates its own dep
        self._run([str(SCRIPT), "rename", "todo-md:F1", "F9"], cwd=str(orch), check=True)
        self.assertIn("Depends on: todo-md:F1 -> run-block:B1", (orch / "TODO.md").read_text(encoding="utf-8"))
        self._run(
            [str(SCRIPT), "edit", "F1", "--depends", "todo-md:F9 -> run-block:B1"],
            cwd=str(orch),
            check=True,
        )
        r_show_orch = self._run([str(SCRIPT), "show", "F1"], cwd=str(orch), check=True)
        self.assertIn("Depends on: todo-md:F9 -> run-block:B1", r_show_orch.stdout)
        self.assertNotIn("IDs in use:", r_show_orch.stdout)

        # Completing all stages unblocks the orchestrator task
        r_done_1 = self._run([str(SCRIPT), "done", "todo-md:F9"], cwd=str(orch), check=True)
        self.assertNotIn("todo-flow:F1", r_done_1.stdout)
        r_done_2 = self._run([str(SCRIPT), "done", "run-block:B1"], cwd=str(orch), check=True)
        self.assertIn("Unblocked: todo-flow:F1", r_done_2.stdout)

    def test_discovery_and_alias_caching_scan_budgets_and_hard_timeouts(self):
        import signal
        import time
        from unittest import mock

        mod = self.todo_md_mod
        ws = (self.tmp / "ws_perf_budget").resolve()
        ext_root = (self.tmp / "ext_perf_budget").resolve()
        orch = ws / "todo-flow"
        proj_a = ws / "proj_a_checkout"
        proj_b = ws / "proj_b_checkout"
        proj_c = ext_root / "proj_c_external"
        for d in (orch, proj_a, proj_b, proj_c):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        (orch / ".todo_projects").write_text(
            "proj-a=../proj_a_checkout\nproj-b=../proj_b_checkout\n",
            encoding="utf-8",
        )
        (orch / ".todo_projects.local").write_text(
            f"proj-c={proj_c}\n",
            encoding="utf-8",
        )

        def _populate_tasks(p_dir, count: int) -> None:
            blocks = []
            for idx in range(1, count + 1):
                dep_line = f"\n- Depends on: F{idx - 1}" if idx > 1 else ""
                blocks.append(f"# 🎯 [NEXT] F{idx}: Task {idx} in {p_dir.name}{dep_line}\n\n- Detail {idx}.")
            (p_dir / "TODO.md").write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

        _populate_tasks(proj_a, 12)
        _populate_tasks(proj_b, 12)
        _populate_tasks(proj_c, 12)

        orch_blocks = []
        for idx in range(1, 13):
            prev_chain = f"F{idx - 1} -> " if idx > 1 else ""
            dep_spec = f"{prev_chain}proj-a:F{idx} -> proj-b:F{idx} -> proj-c:F{idx}"
            orch_blocks.append(
                f"# 🎯 [NEXT] F{idx}: Orchestrator wave {idx}\n- Depends on: {dep_spec}\n\n- Wave {idx}."
            )
        (orch / "TODO.md").write_text("\n\n".join(orch_blocks) + "\n", encoding="utf-8")

        @contextlib.contextmanager
        def _hard_timeout(seconds: float, label: str):
            has_itimer = hasattr(signal, "setitimer") and hasattr(signal, "ITIMER_REAL")
            old_handler = None
            if has_itimer:
                def _on_alarm(signum, frame):
                    raise TimeoutError(f"{label} exceeded hard timeout of {seconds:.1f}s")
                old_handler = signal.signal(signal.SIGALRM, _on_alarm)
                signal.setitimer(signal.ITIMER_REAL, seconds)
            t0 = time.monotonic()
            try:
                yield
            finally:
                elapsed = time.monotonic() - t0
                if has_itimer:
                    signal.setitimer(signal.ITIMER_REAL, 0.0)
                    signal.signal(signal.SIGALRM, old_handler)
                self.assertLess(
                    elapsed,
                    seconds,
                    msg=f"{label} took {elapsed:.3f}s (limit {seconds:.1f}s)",
                )

        with mock.patch.dict(
            os.environ,
            {"TODO_MD_WORKSPACE": str(ws), "TODO_MD_CWD": str(orch)},
            clear=False,
        ):
            # 1. Verify alias_maps caching and O(1) alias/display lookups
            with (
                mock.patch.object(
                    mod,
                    "read_configured_todo_project_entries",
                    wraps=mod.read_configured_todo_project_entries,
                ) as m_read_cfg,
                mock.patch.object(mod, "collect_all_tasks", wraps=mod.collect_all_tasks) as m_collect,
            ):
                with mod.discovery_session() as cache:
                    alias_map = mod.configured_project_alias_map(orch, ws)
                    self.assertIn((orch.resolve(), ws.resolve()), cache.alias_maps)
                    self.assertEqual(alias_map["proj-a"], proj_a.resolve())
                    self.assertEqual(alias_map["proj-c"], proj_c.resolve())

                    # Prime lookup_external_alias and project_display_name once
                    self.assertEqual(mod.lookup_external_alias(orch, ws, "proj-a"), proj_a.resolve())
                    self.assertEqual(mod.lookup_external_alias(orch, ws, "proj-c"), proj_c.resolve())
                    self.assertEqual(mod.project_display_name(proj_a, ws, orch), "proj-a")
                    self.assertEqual(mod.project_display_name(proj_c, ws, orch), "proj-c")

                    cfg_calls_after_prime = m_read_cfg.call_count

                    for _ in range(50):
                        self.assertEqual(
                            mod.configured_project_alias_map(orch, ws)["proj-b"],
                            proj_b.resolve(),
                        )
                        self.assertEqual(mod.lookup_external_alias(orch, ws, "proj-a"), proj_a.resolve())
                        self.assertEqual(mod.lookup_external_alias(orch, ws, "proj-b"), proj_b.resolve())
                        self.assertEqual(mod.lookup_external_alias(orch, ws, "proj-c"), proj_c.resolve())
                        self.assertIsNone(mod.lookup_external_alias(orch, ws, "nonexistent-proj"))
                        self.assertEqual(mod.project_display_name(proj_a, ws, orch), "proj-a")
                        self.assertEqual(mod.project_display_name(proj_b, ws, orch), "proj-b")
                        self.assertEqual(mod.project_display_name(proj_c, ws, orch), "proj-c")

                    self.assertEqual(m_read_cfg.call_count, cfg_calls_after_prime)

                    # Verify build_execution_chain_dag shares cache.task_maps
                    mod.build_execution_chain_dag(orch)
                    self.assertGreaterEqual(len(cache.task_maps), 4)
                    collect_after_first_dag = m_collect.call_count
                    mod.build_execution_chain_dag(orch)
                    self.assertEqual(m_collect.call_count, collect_after_first_dag)

            # 2. Verify hard timeouts and zero parent/child task leaks across commands
            cases = [
                ("cmd_check(orch)", lambda: mod.cmd_check(orch), 4),
                ("cmd_check(proj_a)", lambda: mod.cmd_check(proj_a), 1),
                ("cmd_workspace_check(orch)", lambda: mod.cmd_workspace_check(orch), 4),
                ("cmd_chain(orch)", lambda: mod.cmd_chain(orch), 4),
                ("cmd_chain(proj_a)", lambda: mod.cmd_chain(proj_a), 1),
                ("cmd_list(orch)", lambda: mod.cmd_list(orch), 4),
                ("cmd_list(proj_a)", lambda: mod.cmd_list(proj_a), 1),
                ("cmd_projects(orch)", lambda: mod.cmd_projects(orch), 0),
                ("cmd_projects(proj_a)", lambda: mod.cmd_projects(proj_a), 0),
                (
                    "find_newly_unblocked_tasks(proj_a, F1)",
                    lambda: mod.find_newly_unblocked_tasks(proj_a, "F1"),
                    4,
                ),
            ]
            for label, fn, max_collects in cases:
                with self.subTest(case=label):
                    with mock.patch.object(mod, "collect_all_tasks", wraps=mod.collect_all_tasks) as m_col:
                        out_buf = io.StringIO()
                        err_buf = io.StringIO()
                        with (
                            contextlib.redirect_stdout(out_buf),
                            contextlib.redirect_stderr(err_buf),
                            _hard_timeout(2.0, label),
                        ):
                            res = fn()
                        if isinstance(res, int):
                            self.assertEqual(res, 0, msg=err_buf.getvalue())
                        self.assertLessEqual(
                            m_col.call_count,
                            max_collects,
                            msg=f"{label}: collect_all_tasks called {m_col.call_count} times",
                        )


if __name__ == "__main__":
    unittest.main()
