#!/usr/bin/env python3
"""Tests for workspace discovery, dependency DAG sequencing, list topological order, and unlock reporting."""

import unittest
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
        self._run([str(SCRIPT), "add", "proj_a", "Base rule", "--next"], cwd=str(ws), check=True)
        self._run([str(SCRIPT), "add", "Base parent task"], cwd=str(proj_b), check=True)

        # Missing dependency fails validation immediately on add
        r_bad_dep = self._run(
            [str(SCRIPT), "add", "Sub feature", "--depends", "proj_a:F1,F99"],
            cwd=str(proj_c),
        )
        self.assertNotEqual(r_bad_dep.returncode, 0, msg=r_bad_dep.stderr)
        self.assertIn("missing task 'F99'", r_bad_dep.stderr)

        # Edit F1 in proj_c to depend only on proj_a:F1 (cross-project)
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

        # Workspace projects listing skips .hidden_proj and node_modules, includes parent_proj and parent_proj/sub_proj
        r_projs = self._run([str(SCRIPT), "projects"], cwd=str(ws), check=True)
        self.assertIn("proj_a", r_projs.stdout)
        self.assertIn("parent_proj", r_projs.stdout)
        self.assertIn("parent_proj/sub_proj", r_projs.stdout)
        self.assertNotIn(".hidden_proj", r_projs.stdout)
        self.assertNotIn("node_modules", r_projs.stdout)

        # Workspace overview (-w from inside a project, and auto-workspace from ws root)
        r_ws_flag = self._run([str(SCRIPT), "-w", "overview"], cwd=str(proj_b), check=True)
        self.assertIn("parent_proj/sub_proj:F1", r_ws_flag.stdout)
        r_ws_auto = self._run([str(SCRIPT), "overview"], cwd=str(ws), check=True)
        self.assertIn("## parent_proj/sub_proj", r_ws_auto.stdout)

        # Workspace list and check
        r_ws_list = self._run([str(SCRIPT), "-w", "list", "active"], cwd=str(proj_b), check=True)
        self.assertIn("parent_proj/sub_proj:F1", r_ws_list.stdout)
        self._run([str(SCRIPT), "-w", "check"], cwd=str(proj_b), check=True)

        # todo_md.bundle runs todo_md -w when workspace=1
        bundle_txt = (ROOT / "src/bundles/todo_md.bundle").read_text(encoding="utf-8")
        self.assertIn("[if workspace=1] $ todo_md -w", bundle_txt)

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
        self.assertIn("[ready | unblocks: 2]", q1_flat)
        self.assertIn("[blocked by: F1, F2 | unblocks: 1]", q1_flat)
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
        self.assertIn("✅ [DONE]", r_q2_all.stdout)
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
        self.assertIn("[blocked by: proj_a:F6, proj_b:F1 | unblocks: 1]", self._flat_text(r_orch_q.stdout))
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_a:F6")
        self.assertEqual(
            self._run([str(SCRIPT), "next-id", "orch:F1"], cwd=str(ws), check=True).stdout.strip(),
            "proj_a:F6",
        )
        self.assertEqual((proj_b / "TODO.md").read_text(encoding="utf-8"), proj_b_before)

        # Complete proj_a:F6 -> proj_b:F1 is next; complete proj_b:F1 -> proj_b:F2 is next
        self._run([str(SCRIPT), "done", "proj_a:F6", "-m", "d6"], cwd=str(ws), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_b:F1")
        self._run([str(SCRIPT), "done", "proj_b:F1", "-m", "db1"], cwd=str(ws), check=True)
        self.assertEqual(self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch), check=True).stdout.strip(), "proj_b:F2")

        # CANCELED blocker causes next-id to fail non-zero and queue to mark [blocked]
        self._run([str(SCRIPT), "cancel", "proj_b:F2", "-m", "dropped"], cwd=str(ws), check=True)
        r_q_can = self._run([str(SCRIPT), "queue", "F1"], cwd=str(orch))
        self.assertEqual(r_q_can.returncode, 1, msg=r_q_can.stderr)
        self.assertIn("unresolved blocker", r_q_can.stderr)
        self.assertIn("[CANCELED]", r_q_can.stdout)
        self.assertIn("[blocked by: proj_b:F2]", self._flat_text(r_q_can.stdout))
        self.assertIn("Next actionable: none", r_q_can.stdout)
        r_nid_can = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(orch))
        self.assertNotEqual(r_nid_can.returncode, 0, msg=r_nid_can.stderr)
        self.assertIn("CANCELED", r_nid_can.stderr)

        # Already-closed target fails non-zero in next-id
        r_nid_done = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(proj_a))
        self.assertNotEqual(r_nid_done.returncode, 0, msg=r_nid_done.stderr)
        self.assertIn("already closed", r_nid_done.stderr)

        # Syntax errors rejected by --depends
        for bad_dep in ("F1 ->", "-> F1", "F1, -> F2", "badref"):
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
        self.assertIn("🎯 [NEXT]", rows["F4"])
        self.assertIn("🎯 [NEXT]", rows["F1"])
        self.assertIn("⏳ [NEXT]", rows["F2"])
        self.assertIn("[blocked: F1 (NEXT)]", rows["F2"])
        self.assertNotIn("->", rows["F2"])
        self.assertIn("⏳ [NEXT]", rows["F3"])
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", rows["F3"])
        self.assertLess(r_list.stdout.index("F4"), r_list.stdout.index("F2"))
        self.assertLess(r_list.stdout.index("F1"), r_list.stdout.index("F2"))
        self.assertLess(r_list.stdout.index("F2"), r_list.stdout.index("F3"))

        # Multi-stage Depends on: F1 -> F2 on a single task also surfaces the full ordered chain
        self._run([str(SCRIPT), "add", "Stage task", "--next", "--depends", "F1 -> F2"], cwd=str(proj_a), check=True)
        r_list_stage = self._run([str(SCRIPT), "list", "NEXT"], cwd=str(proj_a), check=True)
        stage_line = next(l for l in r_list_stage.stdout.splitlines() if l.strip().startswith("F5"))
        self.assertIn("⏳ [NEXT]", stage_line)
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", stage_line)

        # --ready filters local list to active tasks without unresolved deps
        r_ready = self._run([str(SCRIPT), "list", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("F1", r_ready.stdout)
        self.assertIn("F4", r_ready.stdout)
        self.assertNotIn("F2", r_ready.stdout)
        self.assertNotIn("F3", r_ready.stdout)
        self.assertNotIn("F5", r_ready.stdout)

        # Cross-project dependency in proj_b + workspace list -w and -w --ready
        self._run([str(SCRIPT), "add", "Cross ready", "--next"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Cross blocked", "--next", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )
        r_ws = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_a), check=True)
        ws_rows = self._table_rows(r_ws.stdout)
        self.assertIn("⏳ [NEXT]", ws_rows["proj_a:F3"])
        self.assertIn("[blocked: F1 (NEXT) -> F2 (NEXT)]", ws_rows["proj_a:F3"])
        self.assertIn("⏳ [NEXT]", ws_rows["proj_b:F2"])
        self.assertIn("[blocked: proj_a:F1 (NEXT) -> proj_a:F2 (NEXT) -> proj_a:F3 (NEXT)]", ws_rows["proj_b:F2"])
        self.assertIn("🎯 [NEXT]", ws_rows["proj_b:F1"])

        r_ws_ready = self._run([str(SCRIPT), "-w", "list", "NEXT", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("proj_a:F1", r_ws_ready.stdout)
        self.assertIn("proj_a:F4", r_ws_ready.stdout)
        self.assertIn("proj_b:F1", r_ws_ready.stdout)
        self.assertNotIn("proj_a:F2", r_ws_ready.stdout)
        self.assertNotIn("proj_b:F2", r_ws_ready.stdout)

        # Completing F1 unblocks F2 -> F2 becomes ready with [deps: DONE] and moves before F3/F5
        self._run([str(SCRIPT), "done", "F1", "-m", "d1"], cwd=str(proj_a), check=True)
        r_after_done = self._run([str(SCRIPT), "list", "-w"], cwd=str(proj_a), check=True)
        ws_after = {
            line.split()[0]: line
            for line in r_after_done.stdout.splitlines()
            if line.startswith("  ")
        }
        self.assertIn("🎯 [NEXT]", ws_after["proj_a:F2"])
        self.assertIn("[deps: DONE]", ws_after["proj_a:F2"])
        self.assertIn("⏳ [NEXT]", ws_after["proj_a:F3"])
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
        self.assertIn("⏳ [NEXT]", r_cyc_list.stdout)

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
        self.assertIn("🔵 [WIP]", wip_rows["F1"])
        self.assertIn("⏳ [WIP]", wip_rows["F3"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT)]", wip_rows["F3"])
        self.assertIn("⏳ [NEXT]", wip_rows["F2"])
        self.assertIn("[blocked: F1 (WIP)]", wip_rows["F2"])
        self.assertIn("⏳ [NEXT]", wip_rows["F4"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT) -> F3 (WIP)]", wip_rows["F4"])

        r_wip_ws = self._run([str(SCRIPT), "list", "-w"], cwd=str(wip_ws), check=True)
        wip_ws_rows = self._table_rows(r_wip_ws.stdout)
        self.assertIn("🔵 [WIP]", wip_ws_rows["alpha:F1"])
        self.assertIn("⏳ [WIP]", wip_ws_rows["alpha:F3"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT)]", wip_ws_rows["alpha:F3"])
        self.assertIn("⏳ [NEXT]", wip_ws_rows["alpha:F4"])
        self.assertIn("[blocked: F1 (WIP) -> F2 (NEXT) -> F3 (WIP)]", wip_ws_rows["alpha:F4"])

    def test_done_prints_newly_unblocked_local_and_orchestrator_tasks(self):
        ws = self.tmp / "ws_done"
        repo_a = ws / "repo_a"
        repo_b = ws / "repo_b"
        orch_dir = ws / ".todo_projects"
        for d in (repo_a, repo_b, orch_dir):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Local chain in repo_a: F1 and F2 both required for F4; F3 depends only on F1
        self._run([str(SCRIPT), "add", "Prereq 1"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Prereq 2"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Single waiter", "--depends", "F1"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Dual waiter", "--depends", "F1, F2"], cwd=str(repo_a), check=True)
        self._run([str(SCRIPT), "add", "Already ready"], cwd=str(repo_a), check=True)

        # Workspace orchestrator task in .todo_projects depending on repo_a:F1 -> repo_b:F1
        self._run([str(SCRIPT), "add", "Repo B step"], cwd=str(repo_b), check=True)
        self._run(
            [str(SCRIPT), "add", "Orch release", "--depends", "repo_a:F1, repo_b:F1"],
            cwd=str(orch_dir),
            check=True,
        )

        # Completing F1 unblocks local F3, does NOT unblock F4 (still waiting on F2) or F5 (had no deps)
        r_done1 = self._run([str(SCRIPT), "done", "F1", "-m", "d1"], cwd=str(repo_a), check=True)
        self.assertIn("Unblocked: F3", r_done1.stdout)
        self.assertNotIn("F4", r_done1.stdout)
        self.assertNotIn("F5", r_done1.stdout)
        self.assertNotIn(".todo_projects:F1", r_done1.stdout)

        # Completing F2 unblocks local F4
        r_done2 = self._run([str(SCRIPT), "done", "F2", "-m", "d2"], cwd=str(repo_a), check=True)
        self.assertIn("Unblocked: F4", r_done2.stdout)

        # Completing F3 has no downstream dependents -> no Unblocked: line
        r_done3 = self._run([str(SCRIPT), "done", "F3", "-m", "d3"], cwd=str(repo_a), check=True)
        self.assertNotIn("Unblocked:", r_done3.stdout)

        # Completing repo_b:F1 completes all deps for .todo_projects:F1 and reports it
        r_done_b = self._run([str(SCRIPT), "done", "F1", "-m", "db1"], cwd=str(repo_b), check=True)
        self.assertIn("Unblocked: .todo_projects:F1", r_done_b.stdout)

    def test_nested_orchestrators_external_alias_and_cycle_safety(self):
        import os
        from unittest import mock

        mod = self.todo_md_mod
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
        (todo_flow / ".todo_projects").write_text("todo_md\nrun_block\nmeta_orch\n", encoding="utf-8")
        (meta_orch / ".todo_projects").write_text("todo_flow\n~/chrome/canary\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"HOME": str(home)}):
            for key in ("TODO_MD_PROJECTS", "TODO_MD_WORKSPACE", "TODO_MD_CWD"):
                os.environ.pop(key, None)
            cfg = mod.read_configured_todo_projects(meta_orch, ws, include_env=False)
            self.assertEqual(
                {p.name for p in cfg},
                {"meta_orch", "todo_flow", "todo_md", "run_block", "canary"},
            )
            orchs, union = mod.discover_orchestrators_for_project(todo_md_p, ws)
            self.assertTrue({"todo_flow", "meta_orch"} <= {p.name for p in orchs})
            self.assertIn(canary.resolve(), union)
            self.assertEqual(mod.resolve_project_dir(todo_md_p, "chrome/canary"), canary.resolve())
            self.assertEqual(mod.resolve_project_dir(todo_md_p, "canary"), canary.resolve())
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

        r_next = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(todo_md_p))
        self._assert_ok(["next-id", "F1"], r_next)
        self.assertEqual(r_next.stdout.strip(), "todo_flow:F1", msg=r_next.stderr)

        r_chain = self._run([str(SCRIPT), "chain", "-f", "todo_md:F1"], cwd=str(todo_md_p), check=True)
        self.assertIn("Next actionable: todo_flow:F1", r_chain.stdout)

        r_show = self._run([str(SCRIPT), "F1"], cwd=str(todo_md_p), check=True)
        self.assertIn("Dependencies (blocked):", r_show.stdout)
        self.assertIn("todo_flow:F1", r_show.stdout)

        r_list = self._run([str(SCRIPT), "list", "active"], cwd=str(todo_md_p), check=True)
        self.assertIn("[blocked: todo_flow:F1 (NEXT)]", self._flat_text(r_list.stdout), msg=r_list.stdout)

        self._run([str(SCRIPT), "done", "todo_flow:F1", "-m", "done"], cwd=str(ws), check=True)
        r_next_done = self._run([str(SCRIPT), "next-id", "F1"], cwd=str(todo_md_p))
        self._assert_ok(["next-id", "F1"], r_next_done)
        self.assertEqual(r_next_done.stdout.strip(), "F1")
        r_show_done = self._run([str(SCRIPT), "F1"], cwd=str(todo_md_p), check=True)
        self.assertNotIn("Dependencies (blocked)", r_show_done.stdout)


if __name__ == "__main__":
    unittest.main()
