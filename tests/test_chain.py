#!/usr/bin/env python3
"""Tests for todo_md chain dependency tree rendering, role queues, Quest Momentum, and orchestrator scoping."""

import os
import re
from pathlib import Path
import pty
import subprocess
import unittest
from tests.helpers import SCRIPT, TodoMdTestCase


class TestChain(TodoMdTestCase):
    def test_chain_command_local_workspace_hold_and_diagnostics(self):
        ws = self.tmp / "ws"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        for d in (proj_a, proj_b):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Local chain with parallel stage + sequential stage + DONE prerequisite + HOLD branch
        self._run([str(SCRIPT), "add", "Completed base"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "F1", "-m", "done1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Step A", "--next", "--depends", "F1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Step B", "--depends", "F2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Step C", "--depends", "F3"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Paused root", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "Blocked by hold", "--depends", "F5"], cwd=str(proj_a), check=True)

        r_local = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj_a), check=True)
        self.assertIn("Chain 1 -> F4: Step C [25% | done: 1, open: 3]:", r_local.stdout)
        self.assertNotIn("F1", r_local.stdout)
        self.assertIn("Held branches:", r_local.stdout)
        self.assertIn("F5 (HOLD) -> F6 (NEW)", r_local.stdout)
        self.assertLess(r_local.stdout.index("1 F2"), r_local.stdout.index("2 F3"))
        self.assertLess(r_local.stdout.index("2 F3"), r_local.stdout.index("3 F4"))

        # --limit N truncates displayed chain rows while preserving RPG progress header
        r_lim = self._run([str(SCRIPT), "chain", "--numbered=right", "--limit", "2"], cwd=str(proj_a), check=True)
        self.assertIn("Chain 1 -> F4: Step C [25% | done: 1, open: 3]:", r_lim.stdout)
        self.assertIn("1 F2", r_lim.stdout)
        self.assertIn("2 F3", r_lim.stdout)
        self.assertNotIn("1 F4", r_lim.stdout)
        self.assertNotIn("3 F4", r_lim.stdout)
        self.assertIn("Held branches:", r_lim.stdout)

        # --include-hold brings HOLD tasks and their dependents into the main chain view
        r_inc = self._run([str(SCRIPT), "chain", "--numbered=right", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertIn("Chain 1 -> F4: Step C [25% | done: 1, open: 3]:", r_inc.stdout)
        self.assertIn("Chain 2 -> F6: Blocked by hold [open: 2]:", r_inc.stdout)
        self.assertIn("F5", r_inc.stdout)
        self.assertIn("F6", r_inc.stdout)
        self.assertNotIn("Held branches:", r_inc.stdout)

        # Cross-project dependency in proj_b resolved locally and across workspace (-w / auto-workspace)
        self._run(
            [str(SCRIPT), "add", "Cross child", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "Cross leaf", "--depends", "F1"],
            cwd=str(proj_b),
            check=True,
        )
        r_b_local = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj_b), check=True)
        self.assertIn("Chain 1 -> F2: Cross leaf [20% | done: 1, open: 4]:", r_b_local.stdout)
        self.assertIn("proj_a:F2", r_b_local.stdout)
        self.assertIn("proj_a:F3", r_b_local.stdout)

        r_ws = self._run([str(SCRIPT), "chain", "--numbered=right", "-w"], cwd=str(proj_a), check=True)
        self.assertIn("Chain 1 -> proj_a:F4: Step C [25% | done: 1, open: 3]:", r_ws.stdout)
        self.assertIn("Chain 2 -> proj_b:F2: Cross leaf [20% | done: 1, open: 4]:", r_ws.stdout)
        self.assertIn("[also in: proj_b:F2]", r_ws.stdout)
        self.assertIn("[also in: proj_a:F4]", r_ws.stdout)
        self.assertIn("proj_a:F2", r_ws.stdout)
        self.assertIn("proj_b:F1", r_ws.stdout)
        self.assertIn("proj_b:F2", r_ws.stdout)
        self.assertIn("proj_a:F5 (HOLD) -> proj_a:F6 (NEW)", r_ws.stdout)

        # Auto-workspace from workspace root and -C selector
        r_ws_root = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(ws), check=True)
        self.assertIn("Chain 1 -> proj_a:F4: Step C [25% | done: 1, open: 3]:", r_ws_root.stdout)
        self.assertIn("Chain 2 -> proj_b:F2: Cross leaf [20% | done: 1, open: 4]:", r_ws_root.stdout)
        self.assertIn("proj_b:F1", r_ws_root.stdout)
        self.assertIn("proj_b:F2", r_ws_root.stdout)
        r_c = self._run([str(SCRIPT), "-C", "proj_b", "chain"], cwd=str(ws), check=True)
        self.assertIn("Chain 1 -> proj_b:F2: Cross leaf [20% | done: 1, open: 4]:", r_c.stdout)

        # Diagnostics on CANCELED blocker
        can_dir = ws / "can_chain"
        can_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(can_dir), check=True)
        self._run([str(SCRIPT), "add", "Dropped base"], cwd=str(can_dir), check=True)
        self._run([str(SCRIPT), "add", "Waiting child", "--depends", "F1"], cwd=str(can_dir), check=True)
        self._run([str(SCRIPT), "cancel", "F1", "-m", "wontfix"], cwd=str(can_dir), check=True)
        r_can = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(can_dir))
        self.assertNotEqual(r_can.returncode, 0, msg=r_can.stderr)
        self.assertIn("CANCELED", r_can.stderr)

        # Diagnostics on MISSING blocker
        miss_dir = ws / "miss_chain"
        miss_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(miss_dir), check=True)
        (miss_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Orphan\n\n- Depends on: F99\n", encoding="utf-8")
        r_miss = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss.returncode, 0, msg=r_miss.stderr)
        self.assertIn("MISSING", r_miss.stderr)

        # Diagnostics on cycle and syntax error
        cyc_dir = ws / "cyc_chain"
        cyc_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(cyc_dir), check=True)
        (cyc_dir / "TODO.md").write_text(
            "# ⚪ [NEW] F1: A\n\n- Depends on: F2\n\n# ⚪ [NEW] F2: B\n\n- Depends on: F1\n",
            encoding="utf-8",
        )
        r_cyc = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(cyc_dir))
        self.assertNotEqual(r_cyc.returncode, 0, msg=r_cyc.stderr)
        self.assertIn("dependency cycle", r_cyc.stderr)

        syn_dir = ws / "syn_chain"
        syn_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(syn_dir), check=True)
        (syn_dir / "TODO.md").write_text("# ⚪ [NEW] F1: Bad\n\n- Depends on: F2 -> \n", encoding="utf-8")
        r_syn = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(syn_dir))
        self.assertNotEqual(r_syn.returncode, 0, msg=r_syn.stderr)
        self.assertIn("empty stage in dependency clause", r_syn.stderr)

        # Invalid flags fail explicitly
        for bad_args in (
            ["chain", "--limit", "0"],
            ["chain", "--limit=abc"],
            ["chain", "--unknown"],
            ["chain", "extra"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_chain_critical_path_ranking_ready_filter_and_standalone_grouping(self):
        ws = self.tmp / "ws_rank"
        proj = ws / "proj"
        proj.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)

        # Standalone tasks only -> no false '->' arrows in Chain: header
        self._run([str(SCRIPT), "add", "Solo A"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Solo B"], cwd=str(proj), check=True)
        r_solo = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj), check=True)
        self.assertIn("Standalone tasks:", r_solo.stdout)
        self.assertNotIn("Chain:", r_solo.stdout)
        self.assertNotIn("F1 -> F2", r_solo.stdout)

        # Add a medium chain F3 -> F4 (F3 unblocks 1) and a deep chain F5 -> F6 -> F7 (F5 unblocks 2)
        self._run([str(SCRIPT), "add", "Med root"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Med leaf", "--depends", "F3"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Deep root"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Deep mid", "--depends", "F5"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Deep leaf", "--depends", "F6"], cwd=str(proj), check=True)

        r_chain = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj), check=True)
        out = r_chain.stdout
        # Deep chain (3 total tasks) ranks before medium chain (2 total tasks), both before Standalone tasks
        self.assertIn("Chain 1 -> F7: Deep leaf [open: 3]:", out)
        self.assertIn("Chain 2 -> F4: Med leaf [open: 2]:", out)
        self.assertIn("Standalone tasks:", out)
        self.assertLess(
            out.index("Chain 1 -> F7: Deep leaf [open: 3]:"),
            out.index("Chain 2 -> F4: Med leaf [open: 2]:"),
        )
        self.assertLess(out.index("1 F5"), out.index("4 F3"))
        self.assertLess(
            out.index("Chain 2 -> F4: Med leaf [open: 2]:"),
            out.index("Standalone tasks:"),
        )
        self.assertNotIn("F7 -> F3", out)
        self.assertNotIn("F4 -> F1", out)
        self.assertNotIn("F1 -> F2", out)
        self.assertIn("[ready | unblocks: 2]", out)
        self.assertIn("[ready | unblocks: 1]", out)

        # --ready filters to ready tasks only, ranks highest-leverage ready tasks first,
        # and shows unified RPG stat tags (omitting the tag on zero-stat standalone tasks)
        r_ready = self._run([str(SCRIPT), "chain", "--numbered=right", "--ready"], cwd=str(proj), check=True)
        r_out = r_ready.stdout
        self.assertIn("Ready tasks:", r_out)
        ready_rows = self._table_rows(r_out)
        self.assertEqual(sorted(ready_rows), ["1.", "2.", "3.", "4."], msg=r_out)
        self.assertIn("F5", ready_rows["1."])
        self.assertIn("[ready: +1, unblocks: 2]", ready_rows["1."])
        self.assertNotIn("F7", r_out)
        self.assertIn("F3", ready_rows["2."])
        self.assertIn("[ready: +1, unblocks: 1]", ready_rows["2."])
        self.assertIn("F1", ready_rows["3."])
        self.assertTrue(ready_rows["3."].endswith("Solo A"), msg=ready_rows["3."])
        self.assertNotIn("unblocks", ready_rows["3."])
        self.assertIn("F2", ready_rows["4."])
        self.assertTrue(ready_rows["4."].endswith("Solo B"), msg=ready_rows["4."])
        self.assertNotIn("unblocks", ready_rows["4."])

    def test_ready_short_flag_multi_chain_role_ease_and_stat_counters(self):
        proj = self.tmp / "ready_multi"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        env = {**os.environ, "COLUMNS": "160"}
        # F1 feeds two chains (F2, F3); F4 -> F5 -> F6 -> F7 is one deeper chain (F4 unblocks more tasks in total)
        self._run([str(SCRIPT), "add", "Shared root", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Branch a", "--next", "--depends", "F1"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Branch b", "--next", "--depends", "F1"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Solo root", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Solo mid", "--next", "--depends", "F4"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Solo deep", "--next", "--depends", "F5"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Solo leaf", "--next", "--depends", "F6"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "D", "Design root"], cwd=str(proj), check=True)

        r_long = self._run([str(SCRIPT), "chain", "--numbered=right", "--ready"], cwd=str(proj), env=env, check=True)
        r_short = self._run([str(SCRIPT), "chain", "-r", "--numbered=right"], cwd=str(proj), env=env, check=True)
        r_default = self._run([str(SCRIPT), "-r", "--numbered=right"], cwd=str(proj), env=env, check=True)
        self.assertEqual(r_long.stdout, r_short.stdout)
        self.assertEqual(r_long.stdout, r_default.stdout)
        rows = {k: v for k, v in self._table_rows(r_long.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(rows), ["1.", "2.", "3."], msg=r_long.stdout)
        # Top chain priority beats multi-chain leverage: F4 advances Chain 1 (the 4-task cone),
        # while F1 only feeds the lower-ranked 2-task chains
        self.assertIn("F4", rows["1."])
        self.assertIn("[ready: +1, unblocks: 3]", rows["1."])
        self.assertIn("F1", rows["2."])
        self.assertIn("[chain: 2, ready: +2, unblocks: 2]", rows["2."])
        # Role ease: work tasks rank ahead of the design root within the same status tier
        self.assertIn("D1", rows["3."])
        self.assertIn("[design]", rows["3."])
        self.assertTrue(rows["3."].endswith("Design root"), msg=rows["3."])

        r_list = self._run([str(SCRIPT), "list", "-r"], cwd=str(proj), check=True)
        self.assertIn("F1", r_list.stdout)
        self.assertIn("F4", r_list.stdout)
        self.assertNotIn("F2", r_list.stdout)

    def test_ready_quest_momentum_continues_after_done(self):
        proj = self.tmp / "ready_momentum"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        env = {**os.environ, "COLUMNS": "160"}
        self._run([str(SCRIPT), "add", "Finished root", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Continuation", "--next", "--depends", "F1"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Wide root", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Wide a", "--next", "--depends", "F3"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Wide b", "--next", "--depends", "F3"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "After continuation", "--next", "--depends", "F2"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "done", "F1"], cwd=str(proj), check=True)

        r_ready = self._run([str(SCRIPT), "chain", "-r", "--numbered=right"], cwd=str(proj), env=env, check=True)
        rows = {k: v for k, v in self._table_rows(r_ready.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(rows), ["1.", "2."], msg=r_ready.stdout)
        # F2 continues the branch of the task that was just completed, ahead of the wider F3 chain set
        self.assertIn("F2", rows["1."])
        self.assertIn("[STAGE | COMBO | ready: +1, unblocks: 1]", rows["1."])
        self.assertIn("F3", rows["2."])
        self.assertIn("[chain: 2, ready: +2, unblocks: 2]", rows["2."])

    def test_ready_stats_omit_default_chain_and_zero_ready_unlocks(self):
        proj = self.tmp / "ready_omit_defaults"
        proj.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(proj), check=True)
        env = {**os.environ, "COLUMNS": "160"}
        # F3 needs both F1 and F2, so completing F1 alone makes nothing immediately ready
        self._run([str(SCRIPT), "add", "Root a", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Root b", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "Joined", "--next", "--depends", "F1, F2"], cwd=str(proj), check=True)

        r_ready = self._run([str(SCRIPT), "chain", "-r", "--numbered=right"], cwd=str(proj), env=env, check=True)
        rows = {k: v for k, v in self._table_rows(r_ready.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(rows), ["1.", "2."], msg=r_ready.stdout)
        for key in ("1.", "2."):
            with self.subTest(row=key):
                self.assertIn("[unblocks: 1]", rows[key], msg=r_ready.stdout)
                self.assertNotIn("ready: +", rows[key])
                self.assertNotIn("chain:", rows[key])

    def test_chain_role_badges_and_role_filter(self):
        ws = self.tmp / "ws_chain_role"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Chain in proj_a: D1 (design) -> F1 (work) -> F2 (NEW defaults to plan)
        # Standalone in proj_a: P1 (NEW defaults to plan), B1 (NEXT defaults to work)
        # Held branch in proj_a: D2 (HOLD, design) -> F3 (NEXT, work)
        self._run([str(SCRIPT), "add", "D", "Design schema", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Build backend", "--next", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Plan rollout", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "P", "Unassigned idea"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "D", "Paused design", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Waiting work", "--next", "--depends", "D2"], cwd=str(proj_a), check=True)

        # Cross-project task in proj_b: F1 (work, depends on proj_a:F1)
        self._run(
            [str(SCRIPT), "add", "F", "Cross repo work", "--next", "--depends", "proj_a:F1"],
            cwd=str(proj_b),
            check=True,
        )

        # 1. Default chain displays aligned [role] column across Chain:, Standalone tasks:, and --ready
        r_all = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj_a), env={**os.environ, "COLUMNS": "160"}, check=True)
        rows = self._table_rows(r_all.stdout)
        self.assertIn("[design]", rows["1."])
        self.assertIn("[work]", rows["2."])
        self.assertIn("[plan]", rows["3."])
        self.assertIn("[work]", rows["4."])
        self.assertIn("[plan]", rows["5."])
        role_cols = {
            line.index("[design]" if "[design]" in line else ("[work]" if "[work]" in line else "[plan]"))
            for k, line in rows.items()
            if k in ("1.", "2.", "3.", "4.")
        }
        self.assertEqual(len(role_cols), 1, msg=f"misaligned role column: {rows!r}")

        r_ready_all = self._run([str(SCRIPT), "chain", "--numbered=right", "--ready"], cwd=str(proj_a), check=True)
        ready_rows = self._table_rows(r_ready_all.stdout)
        # work ranks ahead of design (role execution ease) within the same status tier
        self.assertIn("[work]", ready_rows["1."])
        self.assertIn("[design]", ready_rows["2."])

        # 2. --role work filters Chain <N>, Standalone tasks:, and preserves unblock/blocker context & Held branches
        r_work = self._run([str(SCRIPT), "chain", "--numbered=right", "--role", "WORK"], cwd=str(proj_a), check=True)
        self.assertIn("Chain 1 -> F2: Plan rollout [open: 3]:", r_work.stdout)
        self.assertIn("1 F1", r_work.stdout)
        self.assertIn("[work]", r_work.stdout)
        self.assertIn("[blocked by: D1 | unblocks: 1]", " ".join(r_work.stdout.split()))
        self.assertIn("Standalone tasks:", r_work.stdout)
        self.assertIn("B1", r_work.stdout)
        self.assertNotIn("D1: Design schema", r_work.stdout)
        self.assertNotIn("1 F2", r_work.stdout)
        self.assertNotIn("P1", r_work.stdout)
        self.assertIn("Held branches:", r_work.stdout)
        self.assertIn("D2 (HOLD) -> F3 (NEXT)", r_work.stdout)

        # 3. --role plan hides unrelated held branches and standalone tasks
        r_plan = self._run([str(SCRIPT), "chain", "--numbered=right", "--role=plan"], cwd=str(proj_a), check=True)
        self.assertIn("Chain 1 -> F2: Plan rollout [open: 3]:", r_plan.stdout)
        self.assertIn("1 F2", r_plan.stdout)
        self.assertIn("[plan]", r_plan.stdout)
        self.assertIn("[blocked by: F1]", r_plan.stdout)
        self.assertIn("Standalone tasks:", r_plan.stdout)
        self.assertIn("P1", r_plan.stdout)
        self.assertNotIn("Held branches:", r_plan.stdout)
        self.assertNotIn("D1", r_plan.stdout)
        self.assertNotIn("B1", r_plan.stdout)

        # 4. --role with --ready and -w (workspace) and --limit
        r_ws_work_ready = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w", "--role", "work", "--ready"],
            cwd=str(ws),
            check=True,
        )
        self.assertIn("Ready tasks:", r_ws_work_ready.stdout)
        self.assertIn("proj_a:B1", r_ws_work_ready.stdout)
        self.assertIn("[work]", r_ws_work_ready.stdout)
        self.assertNotIn("proj_a:D1", r_ws_work_ready.stdout)
        self.assertNotIn("proj_a:F1", r_ws_work_ready.stdout)
        self.assertNotIn("proj_b:F1", r_ws_work_ready.stdout)

        r_ws_work_lim = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w", "--role", "work", "--limit", "2"],
            cwd=str(ws),
            check=True,
        )
        lim_rows = {
            k: v for k, v in self._table_rows(r_ws_work_lim.stdout).items() if k.endswith(".")
        }
        self.assertEqual(sorted(lim_rows), ["1.", "2."], msg=r_ws_work_lim.stdout)

        # 5. Empty role match reports clean message; --include-hold brings in held matching tasks
        r_none = self._run([str(SCRIPT), "chain", "--numbered=right", "--role", "review"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: (none matching role=review)", r_none.stdout)

        r_none_ready = self._run([str(SCRIPT), "chain", "--numbered=right", "--role", "review", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("Ready tasks: (none matching role=review)", r_none_ready.stdout)

        r_work_hold = self._run([str(SCRIPT), "chain", "--numbered=right", "--role", "work", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertIn("F3", r_work_hold.stdout)
        self.assertNotIn("Held branches:", r_work_hold.stdout)

        # 6. MISSING placeholder leaves role column blank without crashing and still surfaces DAG error
        miss_dir = ws / "miss_role"
        miss_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(miss_dir), check=True)
        (miss_dir / "TODO.md").write_text("# 🎯 [NEXT] F1: Orphan\n\n- Depends on: F99\n", encoding="utf-8")
        r_miss = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss.returncode, 0, msg=r_miss.stderr)
        self.assertIn("[MISSING]", r_miss.stdout)
        self.assertIn("[work]", r_miss.stdout)
        self.assertIn("unresolved blocker F99 (MISSING)", r_miss.stderr)
        miss_rows = self._table_rows(r_miss.stdout)
        self.assertNotIn("[work]", miss_rows["1."])
        self.assertIn("[work]", miss_rows["2."])

        r_miss_role = self._run([str(SCRIPT), "chain", "--numbered=right", "--role", "work"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss_role.returncode, 0, msg=r_miss_role.stderr)
        self.assertIn("F1", r_miss_role.stdout)
        self.assertNotIn("[MISSING]", r_miss_role.stdout)
        self.assertIn("unresolved blocker F99 (MISSING)", r_miss_role.stderr)

        # 7. Invalid --role values fail explicitly
        for bad_args in (
            ["chain", "--role"],
            ["chain", "--role", ""],
            ["chain", "--role="],
            ["chain", "--role", "a\nb"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

    def test_chain_by_role_queues_and_composition(self):
        ws = self.tmp / "ws_by_role"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Completed prerequisite should not block Queue 1 (work) or Queue 2 (plan)
        self._run([str(SCRIPT), "add", "D", "Done design prereq"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(proj_a), check=True)

        # Queue 1 (work): ready work (F1), work blocked only by work/DONE (F2), standalone work (B1)
        self._run([str(SCRIPT), "add", "F", "Ready work root", "--next", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Work after work", "--next", "--depends", "F1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Standalone bugfix", "--next"], cwd=str(proj_a), check=True)

        # Queue 2 (plan): ready plan (F3, NEW fallback), plan depending on work (F4, NEW fallback), plan depending on plan (F5)
        self._run([str(SCRIPT), "add", "F", "Ready plan", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Plan after work", "--depends", "F2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Plan after plan", "--depends", "F4"], cwd=str(proj_a), check=True)

        # Queue 3 (design): ready design (D2), design depending on design (D3)
        self._run([str(SCRIPT), "add", "D", "Core design", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "D", "Followup design", "--depends", "D2"], cwd=str(proj_a), check=True)

        # Queue 4 (deferred work): work blocked by plan (F6), work blocked by design (F7),
        # and work blocked transitively by design through work (F8 -> F7 -> D2)
        self._run([str(SCRIPT), "add", "F", "Work after plan", "--next", "--depends", "F4"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Work after design", "--next", "--depends", "D2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Work transitively after design", "--next", "--depends", "F7"], cwd=str(proj_a), check=True)

        # Held branch: D4 (HOLD, design) -> F9 (NEXT, work)
        self._run([str(SCRIPT), "add", "D", "Paused design", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Waiting on held design", "--next", "--depends", "D4"], cwd=str(proj_a), check=True)

        # 1. Default --by-role renders all 4 queues in topological order + Held branches
        r_by_role = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--by-role"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_by_role.stdout
        self.assertIn("Queue 1 (work):", out)
        self.assertIn("Queue 2 (plan):", out)
        self.assertIn("Queue 3 (design):", out)
        self.assertIn("Queue 4 (deferred work):", out)
        self.assertIn("Held branches:", out)
        self.assertIn("D4 (HOLD) -> F9 (NEXT)", out)
        self.assertNotIn("Done design prereq", out)
        self.assertNotIn("[blocked by: D1]", out)
        self.assertIn("[ready | FINAL | COMBO]", out)

        # Order between queues
        self.assertLess(out.index("Queue 1 (work):"), out.index("Queue 2 (plan):"))
        self.assertLess(out.index("Queue 2 (plan):"), out.index("Queue 3 (design):"))
        self.assertLess(out.index("Queue 3 (design):"), out.index("Queue 4 (deferred work):"))

        # Topological order and membership within queues
        q1_sec = out[out.index("Queue 1 (work):"):out.index("Queue 2 (plan):")]
        q2_sec = out[out.index("Queue 2 (plan):"):out.index("Queue 3 (design):")]
        q3_sec = out[out.index("Queue 3 (design):"):out.index("Queue 4 (deferred work):")]
        q4_sec = out[out.index("Queue 4 (deferred work):"):out.index("Held branches:")]

        self.assertIn("F1", q1_sec)
        self.assertIn("F2", q1_sec)
        self.assertIn("B1", q1_sec)
        self.assertLess(q1_sec.index("F1"), q1_sec.index("F2"))
        self.assertIn("[ready]", q1_sec)
        self.assertIn("[ready | STAGE | COMBO | unblocks: 4]", q1_sec)
        self.assertIn("[blocked by: F1 | unblocks: 3]", q1_sec)
        self.assertNotIn("F6", q1_sec)
        self.assertNotIn("F7", q1_sec)

        self.assertIn("F3", q2_sec)
        self.assertIn("F4", q2_sec)
        self.assertIn("F5", q2_sec)
        self.assertLess(q2_sec.index("F4"), q2_sec.index("F5"))
        self.assertIn("[plan]", q2_sec)
        self.assertIn("[blocked by: F2 | unblocks: 2]", q2_sec)

        self.assertIn("D2", q3_sec)
        self.assertIn("D3", q3_sec)
        self.assertLess(q3_sec.index("D2"), q3_sec.index("D3"))
        self.assertIn("[design]", q3_sec)

        self.assertIn("F6", q4_sec)
        self.assertIn("F7", q4_sec)
        self.assertIn("F8", q4_sec)
        self.assertLess(q4_sec.index("F7"), q4_sec.index("F8"))
        self.assertIn("[blocked by: F4]", q4_sec)
        self.assertIn("[blocked by: D2 | unblocks: 1]", q4_sec)
        self.assertIn("[blocked by: F7]", q4_sec)

        # 2. --by-role --ready filters to ready tasks and omits Queue 4 (deferred work)
        r_ready = self._run([str(SCRIPT), "chain", "--numbered=right", "--by-role", "--ready"], cwd=str(proj_a), check=True)
        r_out = r_ready.stdout
        self.assertIn("Queue 1 (work):", r_out)
        self.assertIn("Queue 2 (plan):", r_out)
        self.assertIn("Queue 3 (design):", r_out)
        self.assertNotIn("Queue 4 (deferred work):", r_out)
        self.assertIn("F1", r_out)
        self.assertIn("B1", r_out)
        self.assertIn("F3", r_out)
        self.assertIn("D2", r_out)
        for blocked_id in ("F2", "F4", "F5", "D3", "F6", "F7", "F8"):
            self.assertNotIn(blocked_id, r_out)

        # 3. --by-role with --role filters cleanly and omits empty queues
        r_role_work = self._run([str(SCRIPT), "chain", "--numbered=right", "--by-role", "--role", "work"], cwd=str(proj_a), check=True)
        self.assertIn("Queue 1 (work):", r_role_work.stdout)
        self.assertIn("Queue 4 (deferred work):", r_role_work.stdout)
        self.assertNotIn("Queue 2 (plan):", r_role_work.stdout)
        self.assertNotIn("Queue 3 (design):", r_role_work.stdout)
        self.assertIn("Held branches:", r_role_work.stdout)

        r_role_plan = self._run([str(SCRIPT), "chain", "--numbered=right", "--by-role", "--role", "plan"], cwd=str(proj_a), check=True)
        self.assertIn("Queue 2 (plan):", r_role_plan.stdout)
        self.assertNotIn("Queue 1 (work):", r_role_plan.stdout)
        self.assertNotIn("Queue 3 (design):", r_role_plan.stdout)
        self.assertNotIn("Queue 4 (deferred work):", r_role_plan.stdout)
        self.assertNotIn("Held branches:", r_role_plan.stdout)

        r_role_none = self._run([str(SCRIPT), "chain", "--numbered=right", "--by-role", "--role", "review"], cwd=str(proj_a), check=True)
        self.assertIn("Queues: (none matching role=review)", r_role_none.stdout)

        # 4. --by-role with --limit and --include-hold
        r_lim = self._run([str(SCRIPT), "chain", "--numbered=right", "--by-role", "--limit", "4"], cwd=str(proj_a), check=True)
        lim_rows = {k: v for k, v in self._table_rows(r_lim.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(lim_rows), ["1.", "2.", "3.", "4."], msg=r_lim.stdout)
        self.assertNotIn("Queue 3 (design):", r_lim.stdout)

        r_hold = self._run([str(SCRIPT), "chain", "--numbered=right", "--by-role", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertNotIn("Held branches:", r_hold.stdout)
        h_q3 = r_hold.stdout[r_hold.stdout.index("Queue 3 (design):"):r_hold.stdout.index("Queue 4 (deferred work):")]
        h_q4 = r_hold.stdout[r_hold.stdout.index("Queue 4 (deferred work):"):]
        self.assertIn("D4", h_q3)
        self.assertIn("F9", h_q4)

        # 5. Workspace -w --by-role with cross-project design -> work dependency
        self._run(
            [str(SCRIPT), "add", "F", "Cross-project deferred work", "--next", "--depends", "proj_a:D2"],
            cwd=str(proj_b),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Cross-project ready work", "--next"],
            cwd=str(proj_b),
            check=True,
        )
        r_ws = self._run([str(SCRIPT), "chain", "--numbered=right", "-w", "--by-role"], cwd=str(ws), check=True)
        ws_q1 = r_ws.stdout[r_ws.stdout.index("Queue 1 (work):"):r_ws.stdout.index("Queue 2 (plan):")]
        ws_q4 = r_ws.stdout[r_ws.stdout.index("Queue 4 (deferred work):"):r_ws.stdout.index("Held branches:")]
        self.assertIn("proj_b:F2", ws_q1)
        self.assertIn("proj_b:F1", ws_q4)
        self.assertIn("[blocked by: proj_a:D2]", " ".join(ws_q4.split()))

    def test_chain_ready_downstream_targets(self):
        ws = self.tmp / "ws_ready_downstream"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Root D1 (design) unblocks 4 immediate dependents:
        # F1 (NEW, unblocks 0), F2 (NEXT, unblocks 1 -> F5), F3 (WIP, unblocks 0), F4 (NEW, unblocks 0)
        # Expected rank order of immediate dependents: F3 (WIP) -> F2 (NEXT) -> F1 (NEW) -> F4 (NEW)
        self._run([str(SCRIPT), "add", "D", "Root design", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Low leaf", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Next mid", "--next", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Active branch", "--status", "WIP", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Fourth branch", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Transitive leaf", "--depends", "F2"], cwd=str(proj_a), check=True)

        # Standalone task with a held dependent (excluded by default, included with --include-hold)
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Held child", "--status", "HOLD", "--depends", "B1"], cwd=str(proj_a), check=True)

        # Cross-project dependent in proj_b
        self._run([str(SCRIPT), "add", "F", "Cross repo child", "--depends", "proj_a:B1"], cwd=str(proj_b), check=True)

        r_local = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        rows = {k: v for k, v in self._table_rows(r_local.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(rows), ["1.", "2."], msg=r_local.stdout)
        # B1 (work) ranks ahead of D1 (design); its only local dependent is HOLD,
        # so without --include-hold it has zero stats and omits the trailing bracket tag
        self.assertIn("B1", rows["1."])
        self.assertTrue(rows["1."].endswith("Ready bugfix"), msg=rows["1."])
        self.assertNotIn("unblocks", rows["1."])
        # D1 has 5 active downstream tasks (F3, F2, F1, F4, F5), 4 immediate ready dependents,
        # and sits in 4 root chains (F1, F3, F4, F5)
        self.assertIn("D1", rows["2."])
        self.assertIn("[chain: 4, ready: +4, unblocks: 5]", rows["2."])

        # --role design --ready keeps downstream unblock stats of mixed roles visible on D1
        r_role = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready", "--role", "design"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        role_rows = {k: v for k, v in self._table_rows(r_role.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(role_rows), ["1."], msg=r_role.stdout)
        self.assertIn("[chain: 4, ready: +4, unblocks: 5]", role_rows["1."])

        # --include-hold includes the held dependent in --ready downstream stats
        r_hold = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready", "--include-hold"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        hold_rows = {k: v for k, v in self._table_rows(r_hold.stdout).items() if k.endswith(".")}
        self.assertIn("B1", hold_rows["1."])
        self.assertIn("[ready: +1, unblocks: 1]", hold_rows["1."])

        # Workspace -w --ready includes cross-project downstream unblock stats
        r_ws = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w", "--ready"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        ws_rows = {k: v for k, v in self._table_rows(r_ws.stdout).items() if k.endswith(".")}
        self.assertIn("proj_a:B1", ws_rows["1."])
        self.assertIn("[ready: +1, unblocks: 1]", ws_rows["1."])
        self.assertIn("proj_a:D1", ws_rows["2."])
        self.assertIn("[chain: 4, ready: +4, unblocks: 5]", ws_rows["2."])

    def test_chain_finales_section_ranking_and_after_tags(self):
        ws = self.tmp / "ws_finales"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Complete 4 prerequisites in proj_a: D1, F1, F2, F3
        self._run([str(SCRIPT), "add", "D", "Design base"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Step 1"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Step 2"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Step 3"], cwd=str(proj_a), check=True)
        for tid in ("D1", "F1", "F2", "F3"):
            self._run([str(SCRIPT), "done", tid, "-m", "done"], cwd=str(proj_a), check=True)

        # Active multi-node chain in NEXT tier: F4 (NEXT, unblocks 1) -> F5 (NEW, work)
        self._run([str(SCRIPT), "add", "F", "Chain root", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Chain leaf", "--next", "--depends", "F4"], cwd=str(proj_a), check=True)

        # Standalone task in NEXT tier (no deps ever): B1
        self._run([str(SCRIPT), "add", "B", "Standalone next", "--next"], cwd=str(proj_a), check=True)

        # Chain finale in NEXT tier with >3 DONE prerequisites: F6 (depends on D1, F1 -> F2, F3)
        self._run(
            [str(SCRIPT), "add", "F", "Finale next", "--next", "--depends", "D1, F1 -> F2, F3"],
            cwd=str(proj_a),
            check=True,
        )

        # Non-work leaf with DONE prerequisite (NEW defaults to plan role): F7 (depends on D1)
        # Must NOT appear in Chain finales:; placed in numbered Chain 1..N while keeping [ready | after: D1]
        self._run(
            [str(SCRIPT), "add", "F", "Plan after done", "--depends", "D1"],
            cwd=str(proj_a),
            check=True,
        )

        # Active chain in NEW tier (work): F8 (unblocks 1) -> F9
        self._run([str(SCRIPT), "add", "F", "New chain root", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "New chain leaf", "--next", "--depends", "F8"], cwd=str(proj_a), check=True)

        # Two work finales in NEW tier to verify done_count ranking (longer completed chain ranks above 2-task chain):
        # F10 depends on D1 (1 done), F11 depends on D1, F1, F2 (3 done) -> F11 ranks before F10 in Chain finales:
        self._run(
            [str(SCRIPT), "add", "F", "Short work finale", "--next", "--depends", "D1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Long work finale", "--next", "--depends", "D1, F1, F2"],
            cwd=str(proj_a),
            check=True,
        )

        # Cross-project finale in proj_b depending on proj_a:F3
        self._run(
            [str(SCRIPT), "add", "F", "Cross finale", "--next", "--depends", "proj_a:F3"],
            cwd=str(proj_b),
            check=True,
        )

        # 1. Default chain: work chain finales render as top-ranked Chain 1..3 entries before open multi-task chains and plan chains
        r_chain = self._run(
            [str(SCRIPT), "chain", "--numbered=right"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_chain.stdout
        c1_hdr = "Chain 1 -> F6: Finale next [80% | done: 4, open: 1]:"
        c2_hdr = "Chain 2 -> F11: Long work finale [75% | done: 3, open: 1]:"
        c3_hdr = "Chain 3 -> F10: Short work finale [50% | done: 1, open: 1]:"
        c4_hdr = "Chain 4 -> F5: Chain leaf [open: 2]:"
        c5_hdr = "Chain 5 -> F9: New chain leaf [open: 2]:"
        c6_hdr = "Chain 6 -> F7: Plan after done [50% | done: 1, open: 1]:"
        self.assertNotIn("Chain finales:", out)
        for hdr in (c1_hdr, c2_hdr, c3_hdr, c4_hdr, c5_hdr, c6_hdr):
            self.assertIn(hdr, out, msg=out)
        self.assertIn("Standalone tasks:", out)
        self.assertLess(out.index(c1_hdr), out.index(c2_hdr))
        self.assertLess(out.index(c2_hdr), out.index(c3_hdr))
        self.assertLess(out.index(c3_hdr), out.index(c4_hdr))
        self.assertLess(out.index(c4_hdr), out.index(c5_hdr))
        self.assertLess(out.index(c5_hdr), out.index(c6_hdr))
        self.assertLess(out.index(c6_hdr), out.index("Standalone tasks:"))

        fin_sec = out[out.index(c1_hdr):out.index(c4_hdr)]
        self.assertIn("F6", fin_sec)
        self.assertIn("F11", fin_sec)
        self.assertIn("F10", fin_sec)
        self.assertNotIn("F7", fin_sec)
        self.assertLess(fin_sec.index("F6"), fin_sec.index("F11"))
        self.assertLess(fin_sec.index("F11"), fin_sec.index("F10"))
        self.assertIn("[ready | FINAL | COMBO]", fin_sec)
        self.assertIn("[ready | FINAL]", fin_sec)
        self.assertNotIn("B1", fin_sec)

        chain6_sec = out[out.index(c6_hdr):out.index("Standalone tasks:")]
        self.assertIn("F7", chain6_sec)
        self.assertIn("[ready | FINAL]", chain6_sec)

        # With --all, completed DONE prerequisites expand under the finale Chain header
        r_chain_all = self._run(
            [str(SCRIPT), "chain", "--all"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out_all = r_chain_all.stdout
        c1_all_sec = out_all[out_all.index(c1_hdr):out_all.index(c2_hdr)]
        for done_id in ("D1", "F1", "F2", "F3", "F6"):
            self.assertIn(done_id, c1_all_sec, msg=c1_all_sec)

        # 2. --ready ranks work chain finales first within their status tier (F6 before F4 and B1; F11 (done: 3) before F10 (done: 1) before F8; F7 is not a finale so ranks after F8)
        r_ready = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        ready_rows = {k: v for k, v in self._table_rows(r_ready.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(ready_rows), ["1.", "2.", "3.", "4.", "5.", "6.", "7."], msg=r_ready.stdout)
        # All fixtures are NEXT/work except F7 (NEW -> plan): finales rank first, then ready chain roots
        # ordered by parent chain rank (F4 in Chain 4 before F8 in Chain 5), then standalone, then plan
        expected_ready = [
            ("F6", "[FINAL | COMBO]"),
            ("F11", "[FINAL]"),
            ("F10", "[FINAL]"),
            ("F4", "[ready: +1, unblocks: 1]"),
            ("F8", "[ready: +1, unblocks: 1]"),
            ("B1", None),
            ("F7", "[FINAL]"),
        ]
        for idx, (tid, tag) in enumerate(expected_ready, start=1):
            row = ready_rows[f"{idx}."]
            self.assertIn(tid, row, msg=r_ready.stdout)
            if tag is not None:
                self.assertIn(tag, row, msg=r_ready.stdout)
        self.assertTrue(ready_rows["6."].endswith("Standalone next"), msg=ready_rows["6."])

        # 3. --by-role ranks chain finales first within their status tier in each role queue
        r_by_role = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--by-role"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        br_rows = {k: v for k, v in self._table_rows(r_by_role.stdout).items() if k.endswith(".")}
        self.assertIn("F6", br_rows["1."], msg=r_by_role.stdout)
        self.assertIn("[ready | FINAL | COMBO]", br_rows["1."])
        self.assertIn("F11", br_rows["2."], msg=r_by_role.stdout)
        self.assertIn("F10", br_rows["3."], msg=r_by_role.stdout)

        # 4. --role and --limit apply consistently starting from top-ranked finale Chain 1:
        r_lim = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--limit", "1"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        self.assertNotIn("Chain finales:", r_lim.stdout)
        self.assertIn(c1_hdr, r_lim.stdout)
        self.assertIn("F6", r_lim.stdout)
        self.assertNotIn("F11", r_lim.stdout)
        self.assertNotIn("Chain 2", r_lim.stdout)
        self.assertNotIn("Standalone tasks:", r_lim.stdout)

        r_role_lim = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--role", "plan", "--limit", "1"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        self.assertNotIn("Chain finales:", r_role_lim.stdout)
        self.assertIn("Chain 1 -> F7: Plan after done [50% | done: 1, open: 1]:", r_role_lim.stdout)
        self.assertIn("F7", r_role_lim.stdout)
        self.assertIn("[ready | FINAL]", r_role_lim.stdout)
        self.assertNotIn("F6", r_role_lim.stdout)

        # 5. Workspace -w formats cross-project finale as a Chain header with done stats
        r_ws = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        self.assertIn("proj_b:F1: Cross finale [75% | done: 3, open: 1]:", r_ws.stdout)
        self.assertIn("[ready | FINAL | COMBO]", r_ws.stdout)

    def test_chain_rpg_progress_transitive_done_bug_and_role_ranking(self):
        ws = self.tmp / "ws_rpg_rank"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # In proj_b, create DONE base tasks D1 -> F1 and a CANCELED task F2
        self._run([str(SCRIPT), "add", "D", "Cross done root"], cwd=str(proj_b), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(proj_b), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Cross done mid", "--depends", "D1"],
            cwd=str(proj_b),
            check=True,
        )
        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(proj_b), check=True)
        self._run([str(SCRIPT), "add", "F", "Cross canceled"], cwd=str(proj_b), check=True)
        self._run([str(SCRIPT), "cancel", "F2", "-m", "drop"], cwd=str(proj_b), check=True)

        # In proj_a, create local DONE task F1 depending on proj_b:F1, CANCELED proj_b:F2, and missing F99
        # Only DONE tasks (proj_a:F1, proj_b:F1, proj_b:D1 = 3 DONE tasks) should count in done_nodes!
        self._run(
            [str(SCRIPT), "add", "F", "Local done step", "--depends", "proj_b:F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(proj_a), check=True)
        arch_path = proj_a / "TODO_ARCHIVE.md"
        arch_txt = arch_path.read_text(encoding="utf-8")
        arch_txt = arch_txt.replace(
            "- Depends on: proj_b:F1",
            "- Depends on: proj_b:F1, proj_b:F2, F99",
            1,
        )
        arch_path.write_text(arch_txt, encoding="utf-8")

        # Chain A (non-bug work chain linked to 3 transitive DONE tasks: F2 -> F3)
        # 3 done + 2 open = 5 tasks, 60% | 3 done, 2 open
        self._run(
            [str(SCRIPT), "add", "F", "Progress chain open 1", "--next", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Progress chain open 2", "--next", "--depends", "F2"],
            cwd=str(proj_a),
            check=True,
        )

        # Chain B (ready bug B1 -> F4): ready_bugs=1, total_bugs=1, dist=0 -> ranks #1!
        self._run([str(SCRIPT), "add", "B", "Ready bug root", "--next"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "After ready bug", "--next", "--depends", "B1"],
            cwd=str(proj_a),
            check=True,
        )

        # Chain C (blocked bug at distance 1: F5 -> B2): ready_bugs=0, total_bugs=1, dist=1 -> ranks #2!
        self._run([str(SCRIPT), "add", "F", "Pre-bug step", "--next"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "B", "Blocked bug dist 1", "--next", "--depends", "F5"],
            cwd=str(proj_a),
            check=True,
        )

        # Chain D (blocked bug at distance 2: F6 -> F7 -> B3): ready_bugs=0, total_bugs=1, dist=2 -> ranks #3!
        self._run([str(SCRIPT), "add", "F", "Far bug step 1", "--next"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Far bug step 2", "--next", "--depends", "F6"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "B", "Blocked bug dist 2", "--next", "--depends", "F7"],
            cwd=str(proj_a),
            check=True,
        )

        # Chain E (plan chain: F8 [plan] -> F9 [plan]): 0 bugs, role=plan -> ranks after work Chain A!
        self._run(
            [str(SCRIPT), "add", "F", "Plan chain root"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Plan chain leaf", "--depends", "F8"],
            cwd=str(proj_a),
            check=True,
        )

        # Chain F (design chain: D1 [design] -> D2 [design]): 0 bugs, role=design -> ranks after plan Chain E!
        self._run([str(SCRIPT), "add", "D", "Design chain root", "--next"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "D", "Design chain leaf", "--depends", "D1"],
            cwd=str(proj_a),
            check=True,
        )

        # Standalone tasks to verify bug-first, role-ease, and status ordering:
        # - D3: NEXT, design
        # - F10: NEXT, plan
        # - F11: NEW, work
        # - B4: NEXT, work (bug task B* must rank above other work tasks!)
        self._run([str(SCRIPT), "add", "D", "Standalone design next", "--next"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Standalone plan next"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "F", "Standalone work new", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Standalone bug new", "--next"], cwd=str(proj_a), check=True)

        r_chain = self._run(
            [str(SCRIPT), "chain", "--numbered=right"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_chain.stdout

        # Verify numbered RPG progress headers and transitive DONE count (excluding CANCELED/MISSING)
        h1 = "Chain 1 -> F4: After ready bug [open: 2]:"
        h2 = "Chain 2 -> B2: Blocked bug dist 1 [open: 2]:"
        h3 = "Chain 3 -> B3: Blocked bug dist 2 [open: 3]:"
        h4 = "Chain 4 -> F3: Progress chain open 2 [60% | done: 3, open: 2]:"
        h5 = "Chain 5 -> F9: Plan chain leaf [open: 2]:"
        h6 = "Chain 6 -> D2: Design chain leaf [open: 2]:"
        for h in (h1, h2, h3, h4, h5, h6):
            self.assertIn(h, out, msg=out)

        # Verify chain ranking order:
        # Chain 1 (B1 -> F4, ready bug) -> Chain 2 (F5 -> B2, bug dist 1)
        # -> Chain 3 (F6 -> F7 -> B3, bug dist 2) -> Chain 4 (F2 -> F3, work, 5 total tasks)
        # -> Chain 5 (F8 -> F9, plan) -> Chain 6 (D1 -> D2, design)
        self.assertLess(out.index("1 B1"), out.index("3 F5"), msg=out)
        self.assertLess(out.index("3 F5"), out.index("5 F6"), msg=out)
        self.assertLess(out.index("5 F6"), out.index("8 F2"), msg=out)
        self.assertLess(out.index("8 F2"), out.index("10 F8"), msg=out)
        self.assertLess(out.index("10 F8"), out.index("12 D1"), msg=out)

        # Verify Standalone tasks ordering: B4 (bug, work, NEW) -> F11 (work, NEW) -> F10 (plan, NEXT) -> D3 (design, NEXT)
        solo_sec = out[out.index("Standalone tasks:"):]
        self.assertLess(solo_sec.index("B4"), solo_sec.index("F11"), msg=solo_sec)
        self.assertLess(solo_sec.index("F11"), solo_sec.index("F10"), msg=solo_sec)
        self.assertLess(solo_sec.index("F10"), solo_sec.index("D3"), msg=solo_sec)

        # Complete B1: B1 moves to DONE; if B1 -> F4 -> F12 had 2 open tasks left, total_tasks and total_bugs stay non-decreasing
        # Complete F2 in Chain 4: Chain 4 is now a finale F3 with 4 done tasks; complete F5 in Chain 2 so B2 becomes ready!
        self._run([str(SCRIPT), "done", "F5", "-m", "done"], cwd=str(proj_a), check=True)
        # Add another task after B2 so Chain (F5 [DONE] -> B2 -> F12) stays a 2-open-task chain with 1 done task:
        # 3 tasks, 33% | 1 done, 2 open, and now B2 is ready!
        self._run(
            [str(SCRIPT), "add", "F", "Followup after B2", "--next", "--depends", "B2"],
            cwd=str(proj_a),
            check=True,
        )
        r_after = self._run(
            [str(SCRIPT), "chain", "--numbered=right"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        # B2 -> F12 (3 tasks, 33% | 1 done, 2 open) now has a ready bug AND higher total_tasks (3 vs 2) than B1 -> F4!
        self.assertIn("Chain 1 -> F12: Followup after B2 [33% | done: 1, open: 2]:", r_after.stdout)
        self.assertLess(r_after.stdout.index("1 B2"), r_after.stdout.index("3 B1"), msg=r_after.stdout)

        # Verify role-weighted velocity & effort ranking between chains with identical role_ease and status:
        # Compare two work-only NEW chains with 1 done prerequisite (proj_b:D1):
        # - Fast 2-open work chain (F13 -> F14, remaining_effort = 2, velocity = 1/3)
        # - Long 3-open work chain (F15 -> F16 -> F17, remaining_effort = 3, velocity = 1/4)
        # Fast 2-open work chain has higher weighted velocity (1/3 > 1/4) and lower effort (2 < 3), so it ranks before the 3-open chain!
        self._run(
            [str(SCRIPT), "add", "F", "Fast vel 1", "--next", "--depends", "proj_b:D1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Fast vel 2", "--next", "--depends", "F13"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Slow vel 1", "--next", "--depends", "proj_b:D1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Slow vel 2", "--next", "--depends", "F15"],
            cwd=str(proj_a),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Slow vel 3", "--next", "--depends", "F16"],
            cwd=str(proj_a),
            check=True,
        )
        r_vel = self._run(
            [str(SCRIPT), "chain", "--numbered=right"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        self.assertLess(r_vel.stdout.index("F13"), r_vel.stdout.index("F15"), msg=r_vel.stdout)

        # Verify workspace -w mode matches bug prefix on <project>:<ID> in Standalone tasks:
        self._run([str(SCRIPT), "add", "F", "Proj B next work", "--next"], cwd=str(proj_b), check=True)
        r_ws = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        ws_solo = r_ws.stdout[r_ws.stdout.index("Standalone tasks:"):]
        self.assertLess(ws_solo.index("proj_a:B4"), ws_solo.index("proj_b:F3"), msg=ws_solo)
        self.assertLess(ws_solo.index("proj_a:F11"), ws_solo.index("proj_b:F3"), msg=ws_solo)

    def test_chain_todo_projects_orchestrator_dag_child_scoping_cwd_refs_and_ansi_dimming(self):
        ws = self.tmp / "ws_orch"
        todo_flow = ws / "todo_flow"
        run_block = ws / "run_block"
        todo_md_proj = ws / "todo_md"
        unlisted_proj = ws / "unlisted_proj"
        for d in (todo_flow, run_block, todo_md_proj, unlisted_proj):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)

        # Configure .todo_projects in todo_flow listing run_block and todo_md (unlisted_proj is excluded)
        (todo_flow / ".todo_projects").write_text(
            "# Workspace projects managed by todo_flow\nrun_block\ntodo_md  # inline comment\n",
            encoding="utf-8",
        )

        # Unlisted project has an open task that should be excluded when .todo_projects is present
        self._run([str(SCRIPT), "add", "F", "Unlisted project task"], cwd=str(unlisted_proj), check=True)

        # Child project run_block has F1 (which will be sequenced by todo_flow), standalone F2,
        # finale F3 (with local DONE prerequisite D1), and held branch H -> F4
        self._run([str(SCRIPT), "add", "F", "Run block sequenced task", "--next"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "F", "Run block standalone task", "--next"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "add", "D", "Run block done design"], cwd=str(run_block), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(run_block), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Run block finale task", "--next", "--depends", "D1"],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "D", "Run block held root", "--status", "HOLD"],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Run block held leaf", "--next", "--depends", "D2"],
            cwd=str(run_block),
            check=True,
        )

        # Child project todo_md has F1 (part of the cross-project chain), standalone F2,
        # finale F3 (after local DONE D1), and held task D2
        self._run([str(SCRIPT), "add", "F", "Todo md downstream task", "--next"], cwd=str(todo_md_proj), check=True)
        self._run([str(SCRIPT), "add", "F", "Todo md standalone task", "--next"], cwd=str(todo_md_proj), check=True)
        self._run([str(SCRIPT), "add", "D", "Todo md done design"], cwd=str(todo_md_proj), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(todo_md_proj), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Todo md finale task", "--next", "--depends", "D1"],
            cwd=str(todo_md_proj),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "D", "Todo md held task", "--status", "HOLD"],
            cwd=str(todo_md_proj),
            check=True,
        )

        # Orchestrator todo_flow has D1 (design), F1 (work), and F2 sequencing:
        # D1, F1 -> run_block:F1 -> todo_md:F1
        # Plus an unrelated chain in todo_flow (F3 -> F4) and standalone F5
        self._run([str(SCRIPT), "add", "D", "Flow design prereq", "--next"], cwd=str(todo_flow), check=True)
        self._run([str(SCRIPT), "add", "F", "Flow work prereq", "--next"], cwd=str(todo_flow), check=True)
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Flow release milestone",
                "--depends",
                "D1, F1 -> run_block:F1 -> todo_md:F1",
            ],
            cwd=str(todo_flow),
            check=True,
        )
        self._run([str(SCRIPT), "add", "F", "Flow internal step 1"], cwd=str(todo_flow), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Flow internal step 2", "--depends", "F3"],
            cwd=str(todo_flow),
            check=True,
        )
        self._run([str(SCRIPT), "add", "F", "Flow standalone task"], cwd=str(todo_flow), check=True)

        base_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")}
        base_env["COLUMNS"] = "160"

        # 1. Running `todo_md chain` inside orchestrator todo_flow automatically builds chains across
        # todo_flow, run_block, and todo_md without requiring -w, and formats todo_flow tasks without prefix
        r_orch = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(todo_flow), env=base_env, check=True)
        out_orch = r_orch.stdout
        self.assertIn("D1", out_orch)
        self.assertIn("F1", out_orch)
        self.assertNotIn("todo_flow:D1", out_orch)
        self.assertIn("run_block:F1", out_orch)
        self.assertIn("[blocked by: D1, F1 | unblocks: 2]", out_orch)
        self.assertIn("todo_md:F1", out_orch)
        self.assertIn("run_block:F3", out_orch)
        self.assertIn("todo_md:F3", out_orch)
        self.assertNotIn("unlisted_proj", out_orch)

        # 2. `todo_md chain -w` filters discovery to .todo_projects when present (excluding unlisted_proj)
        r_ws = self._run([str(SCRIPT), "chain", "--numbered=right", "-w"], cwd=str(ws), env=base_env, check=True)
        self.assertIn("todo_flow:D1", r_ws.stdout)
        self.assertIn("run_block:F1", r_ws.stdout)
        self.assertIn("todo_md:F1", r_ws.stdout)
        self.assertNotIn("unlisted_proj", r_ws.stdout)

        # 3. Running `todo_md chain` directly inside child project `run_block`:
        # - discovers todo_flow orchestrator DAG so F1 is blocked by todo_flow:D1, todo_flow:F1
        # - omits `run_block:` prefix for local tasks (F1, F2, F3) while keeping `todo_flow:` and `todo_md:`
        # - filters Chain finales, Chains, Standalone tasks, and Held branches to only those involving run_block
        r_child_direct = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(run_block), env=base_env, check=True)
        out_direct = r_child_direct.stdout
        self.assertNotIn("Chain finales:", out_direct)
        self.assertIn("Chain 1 -> F3: Run block finale task [50% | done: 1, open: 1]:", out_direct)
        self.assertIn("F3", out_direct)
        self.assertIn("[ready | FINAL | COMBO]", out_direct)
        self.assertNotIn("todo_md:F3", out_direct)
        self.assertIn("Chain 2 -> todo_flow:F2: Flow release milestone [open: 5]:", out_direct)
        self.assertIn("todo_flow:D1", out_direct)
        self.assertIn("todo_flow:F1", out_direct)
        self.assertIn("F1", out_direct)
        self.assertNotIn("run_block:F1", out_direct)
        self.assertIn("[blocked by: todo_flow:D1, todo_flow:F1 | unblocks: 2]", out_direct)
        self.assertIn("todo_md:F1", out_direct)
        self.assertIn("todo_flow:F2", out_direct)
        # Unrelated chains/tasks from todo_flow and todo_md are filtered out
        self.assertNotIn("Flow internal step", out_direct)
        self.assertNotIn("Flow standalone task", out_direct)
        self.assertNotIn("Todo md standalone task", out_direct)
        self.assertIn("Standalone tasks:", out_direct)
        self.assertIn("F2", out_direct)
        self.assertIn("Held branches:", out_direct)
        self.assertIn("D2 (HOLD) -> F4 (NEXT)", out_direct)
        self.assertNotIn("todo_md:D2", out_direct)

        # 4. Running `todo_md -C run_block chain` (and `--project run_block`) from outside `run_block`
        # keeps the `run_block:` prefix on run_block tasks so IDs are ready for copy-paste in cwd
        for from_cwd in (ws, todo_flow):
            with self.subTest(from_cwd=from_cwd.name):
                r_ext = self._run(
                    [str(SCRIPT), "-C", "run_block", "chain"],
                    cwd=str(from_cwd),
                    env=base_env,
                    check=True,
                )
                out_ext = r_ext.stdout
                self.assertIn("run_block:F3", out_ext)
                self.assertIn("run_block:F1", out_ext)
                self.assertIn("[blocked by: todo_flow:D1, todo_flow:F1 | unblocks: 2]", out_ext)
                self.assertIn("run_block:F2", out_ext)
                self.assertIn("run_block:D2 (HOLD) -> run_block:F4 (NEXT)", out_ext)
                self.assertNotIn("Flow internal step", out_ext)
                self.assertNotIn("Todo md standalone task", out_ext)

        # 5. Project-scoped `--ready` and `--by-role` filters to target project tasks while preserving orchestrator blockers
        # Because run_block:F1 is blocked by todo_flow:D1 (design) and todo_flow:F1 (work),
        # run_block:F1 is NOT ready in `--ready` and is placed in `Queue 4 (deferred work)` in `--by-role`!
        r_ready = self._run(
            [str(SCRIPT), "-C", "run_block", "chain", "--ready"],
            cwd=str(ws),
            env=base_env,
            check=True,
        )
        self.assertIn("run_block:F3", r_ready.stdout)
        self.assertIn("run_block:F2", r_ready.stdout)
        self.assertNotIn("run_block:F1", r_ready.stdout)
        self.assertNotIn("todo_flow:", r_ready.stdout)
        self.assertNotIn("todo_md:", r_ready.stdout)

        r_by_role = self._run(
            [str(SCRIPT), "-C", "run_block", "chain", "--by-role"],
            cwd=str(ws),
            env=base_env,
            check=True,
        )
        self.assertIn("Queue 1 (work):", r_by_role.stdout)
        self.assertIn("run_block:F3", r_by_role.stdout)
        self.assertIn("run_block:F2", r_by_role.stdout)
        self.assertIn("Queue 4 (deferred work):", r_by_role.stdout)
        self.assertIn("run_block:F1", r_by_role.stdout)
        self.assertNotIn("Queue 3 (design):", r_by_role.stdout)
        self.assertNotIn("todo_md:F2", r_by_role.stdout)

        # 6. ANSI dim-italic styling for external-project tasks inside displayed chains:
        # - In pipes (default without FORCE_COLOR): no ANSI escape sequences
        self.assertNotIn("\033[", out_direct)
        # - With FORCE_COLOR=1: external tasks (todo_flow:*, todo_md:*) inside Chain 1 are wrapped in \033[2;3m...\033[0m,
        #   while target-project tasks (run_block:*) are rendered in normal text without dim styling!
        color_env = {**base_env, "FORCE_COLOR": "1", "COLUMNS": "72"}
        r_color = self._run(
            [str(SCRIPT), "-C", "run_block", "chain", "--numbered=right"],
            cwd=str(ws),
            env=color_env,
            check=True,
        )
        color_lines = r_color.stdout.splitlines()
        dim_lines = [ln for ln in color_lines if ln.startswith("\033[2;3m")]
        normal_task_lines = [ln for ln in color_lines if ln.startswith("  ") and not ln.startswith("\033[")]
        self.assertTrue(any("2 todo_flow:F1" in ln for ln in dim_lines), msg=r_color.stdout)
        self.assertTrue(any("3 todo_flow:D1" in ln for ln in dim_lines), msg=r_color.stdout)
        self.assertTrue(any("5 todo_md:F1" in ln for ln in dim_lines), msg=r_color.stdout)
        self.assertTrue(any("6 todo_flow:F2" in ln for ln in dim_lines), msg=r_color.stdout)
        self.assertFalse(any("4 run_block:F1" in ln for ln in dim_lines), msg=r_color.stdout)
        self.assertTrue(any("4 run_block:F1" in ln for ln in normal_task_lines), msg=r_color.stdout)
        self.assertTrue(any("7 run_block:F2" in ln for ln in normal_task_lines), msg=r_color.stdout)
        self.assertTrue(any("1 run_block:F3" in ln for ln in normal_task_lines), msg=r_color.stdout)

        # Verify column alignment is identical with and without ANSI color even when wrapping at COLUMNS=72
        r_plain_72 = self._run(
            [str(SCRIPT), "-C", "run_block", "chain", "--numbered=right"],
            cwd=str(ws),
            env={**base_env, "COLUMNS": "72"},
            check=True,
        )
        stripped_color = self.todo_md_mod._strip_ansi(r_color.stdout)
        self.assertEqual(stripped_color, r_plain_72.stdout)

        # - With NO_COLOR=1 (and no FORCE_COLOR) on a real PTY: plain text without ANSI codes
        master_fd, slave_fd = pty.openpty()
        try:
            proc_pty = subprocess.run(
                [str(SCRIPT), "-C", "run_block", "chain"],
                cwd=str(ws),
                env={**base_env, "NO_COLOR": "1"},
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                close_fds=True,
                check=False,
            )
        finally:
            os.close(slave_fd)
        pty_chunks: list[bytes] = []
        while True:
            try:
                data = os.read(master_fd, 4096)
                if not data:
                    break
                pty_chunks.append(data)
            except OSError:
                break
        os.close(master_fd)
        pty_out = b"".join(pty_chunks).decode("utf-8", errors="replace")
        self.assertEqual(proc_pty.returncode, 0, msg=pty_out)
        self.assertNotIn("\033[", pty_out)

        # 7. Support .todo_projects.local and TODO_MD_PROJECTS env override
        (todo_flow / ".todo_projects").unlink()
        (todo_flow / ".todo_projects.local").write_text("run_block\ntodo_md\n", encoding="utf-8")
        r_local_cfg = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(run_block), env=base_env, check=True)
        self.assertIn("[blocked by: todo_flow:D1, todo_flow:F1 | unblocks: 2]", r_local_cfg.stdout)

        (todo_flow / ".todo_projects.local").unlink()
        env_projects = {**base_env, "TODO_MD_PROJECTS": "todo_flow,run_block,todo_md"}
        r_env_orch = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(todo_flow), env=env_projects, check=True)
        self.assertIn("run_block:F1", r_env_orch.stdout)
        self.assertNotIn("unlisted_proj", r_env_orch.stdout)
        r_env_child = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(run_block), env=env_projects, check=True)
        self.assertIn("[blocked by: todo_flow:D1, todo_flow:F1 | unblocks: 2]", r_env_child.stdout)
        self.assertNotIn("Flow internal step", r_env_child.stdout)

    def test_root_anchored_chains_quest_momentum_also_in_and_all_done_tasks(self):
        mod = self.todo_md_mod
        ws = self.tmp / "ws_f52"
        todo_flow = ws / "todo_flow"
        run_block = ws / "run_block"
        for d in (todo_flow, run_block):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)
        (todo_flow / ".todo_projects").write_text("run_block\n", encoding="utf-8")

        base_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")}
        base_env["COLUMNS"] = "160"
        color_env = {**base_env, "FORCE_COLOR": "1", "COLUMNS": "160"}

        # 1. Forked DAG with shared DONE prerequisite (todo_flow:D1) and shared open prerequisite (run_block:F1)
        # feeding into two independent closing root goals:
        # - Goal A (run_block:F3, 4 tasks total: todo_flow:D1 [DONE] -> run_block:F1 -> run_block:F2 -> run_block:F3)
        # - Goal B (run_block:F4, 3 tasks total: todo_flow:D1 [DONE] -> run_block:F1 -> run_block:F4)
        self._run([str(SCRIPT), "add", "D", "Shared architecture spec"], cwd=str(todo_flow), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(todo_flow), check=True)

        self._run(
            [str(SCRIPT), "add", "F", "Shared core parser", "--next", "--depends", "todo_flow:D1"],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Goal A mid step", "--next", "--depends", "F1"],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Goal A closing root", "--next", "--depends", "F2"],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Goal B closing root", "--next", "--depends", "F1"],
            cwd=str(run_block),
            check=True,
        )

        # Also add a competing NEXT chain (run_block:F5 [NEXT] -> run_block:F6 [NEXT] -> run_block:F7 [NEXT])
        # with 0 done tasks (3 tasks total) to test Quest Momentum & started-chain status floor!
        self._run([str(SCRIPT), "add", "F", "Competing next 1", "--next"], cwd=str(run_block), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Competing next 2", "--next", "--depends", "F5"],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Competing next root", "--next", "--depends", "F6"],
            cwd=str(run_block),
            check=True,
        )

        # Inspect plan_execution_chains() entries directly
        old_cwd = Path.cwd()
        try:
            os.chdir(run_block)
            dag_default = mod.build_execution_chain_dag(run_block)
            plan_default = mod.plan_execution_chains(dag_default)
            dag_all = mod.build_execution_chain_dag(run_block, include_done=True)
            plan_all = mod.plan_execution_chains(dag_all, include_done=True)
        finally:
            os.chdir(old_cwd)

        stats_def = plan_default["chain_stats"]
        self.assertEqual(len(stats_def), 3)
        by_root_ref = {str(e["root_ref"]): e for e in stats_def}
        self.assertEqual(set(by_root_ref), {"F3", "F4", "F7"})
        self.assertEqual(by_root_ref["F3"]["root"], (run_block.resolve(), "F3"))
        self.assertEqual(by_root_ref["F3"]["root_title"], "Goal A closing root")
        self.assertEqual(by_root_ref["F4"]["root"], (run_block.resolve(), "F4"))
        self.assertEqual(by_root_ref["F4"]["root_title"], "Goal B closing root")
        # Shared prerequisite F1 and todo_flow:D1 record the other root chain ref in rank order
        self.assertEqual(by_root_ref["F4"]["also_in"].get((run_block.resolve(), "F1")), ["F3"])
        self.assertEqual(by_root_ref["F3"]["also_in"].get((run_block.resolve(), "F1")), ["F4"])
        self.assertEqual(by_root_ref["F4"]["also_in"].get((todo_flow.resolve(), "D1")), ["F3"])
        self.assertEqual(by_root_ref["F3"]["also_in"].get((todo_flow.resolve(), "D1")), ["F4"])
        self.assertEqual(
            len(plan_all["chains"][0]),
            by_root_ref["F4"]["total_tasks"],
        )

        # Because F3 and F4 chains already have done_count=1 > 0, their started-chain status floor is NEXT (1),
        # and their weighted_velocity (1/3 and 1/4) > 0 beats unstarted F7 (0/3), even though F1..F4 are NEW!
        self.assertEqual([str(e["root_ref"]) for e in stats_def], ["F4", "F3", "F7"])

        # Verify CLI output without --all:
        r_def = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(run_block), env=base_env, check=True)
        out_def = r_def.stdout
        self.assertIn("Chain 1 -> F4: Goal B closing root [33% | done: 1, open: 2]:", out_def)
        self.assertIn("Chain 2 -> F3: Goal A closing root [25% | done: 1, open: 3]:", out_def)
        self.assertIn("Chain 3 -> F7: Competing next root [open: 3]:", out_def)
        self.assertIn("[also in: F3]", out_def)
        self.assertIn("[also in: F4]", out_def)
        self.assertNotIn("todo_flow:D1", out_def)

        # Verify CLI output with --all (plain text and ANSI color with target highlighting):
        r_all_plain = self._run([str(SCRIPT), "chain", "--numbered=right", "--all"], cwd=str(run_block), env=base_env, check=True)
        out_all_plain = r_all_plain.stdout
        self.assertIn("todo_flow:D1", out_all_plain)
        self.assertIn("✅ [DONE]", out_all_plain)
        self.assertRegex(out_all_plain, r"todo_flow:D1\s+✅ \[DONE\]\s+\[design\]\s+Shared architecture spec.*\[also in: F3\]")
        self.assertRegex(out_all_plain, r"todo_flow:D1\s+✅ \[DONE\]\s+\[design\]\s+Shared architecture spec.*\[also in: F4\]")
        self.assertLess(out_all_plain.index("1 todo_flow:D1"), out_all_plain.index("2 F1"))

        # Test composable ANSI styling under --all:
        # - unhighlighted external DONE (todo_flow:D1) -> \033[2;3;90m
        r_all_color = self._run([str(SCRIPT), "chain", "--numbered=right", "--all"], cwd=str(run_block), env=color_env, check=True)
        self.assertTrue(
            any(ln.startswith("\033[2;3;90m") and "todo_flow:D1" in ln for ln in r_all_color.stdout.splitlines()),
            msg=r_all_color.stdout,
        )
        self.assertEqual(mod._strip_ansi(r_all_color.stdout), out_all_plain)

        # - highlighted external DONE (`todo_md chain --all todo_flow:D1`) -> \033[1;3;93m preserving ✅ [DONE]
        r_all_hl_ext = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--all", "todo_flow:D1"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        self.assertTrue(
            any(
                ln.startswith("\033[1;3;93m") and "todo_flow:D1" in ln and "✅ [DONE]" in ln
                for ln in r_all_hl_ext.stdout.splitlines()
            ),
            msg=r_all_hl_ext.stdout,
        )

        # 2. Verify monotonic Quest Momentum across `todo_md status ... WIP` and `todo_md done ...`:
        # Switch F2 in Goal A (F3 chain) to WIP -> F3 chain becomes active quest (tier 0) and ranks #1!
        self._run([str(SCRIPT), "status", "F2", "WIP"], cwd=str(run_block), check=True)
        old_cwd = Path.cwd()
        try:
            os.chdir(run_block)
            plan_wip = mod.plan_execution_chains(mod.build_execution_chain_dag(run_block))
        finally:
            os.chdir(old_cwd)
        f3_wip_entry = next(e for e in plan_wip["chain_stats"] if e["root_ref"] == "F3")
        self.assertEqual(plan_wip["chain_stats"][0]["root_ref"], "F3")
        self.assertTrue(f3_wip_entry["is_active_quest"])
        self.assertEqual(f3_wip_entry["best_status"], 0)
        rank_key_before_done = f3_wip_entry["rank_key"]

        # Now complete F1 and then F2 via `todo_md done` (leaving F3 in NEW status, not yet switched to WIP!):
        # Because F2 is now the most recently completed DONE task at the top of TODO_ARCHIVE.md,
        # Goal A retains `is_active_quest=True` (tier 0), its rank_key is monotonically non-increasing,
        # and it stays at Chain 1 above F7 (all NEXT)!
        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(run_block), check=True)
        # Add another step F8 after F3 so Goal A (now rooted at F8) remains a 2-open-task chain after F2 is done
        self._run(
            [str(SCRIPT), "add", "F", "Goal A post-root step", "--next", "--depends", "F3"],
            cwd=str(run_block),
            check=True,
        )
        old_cwd = Path.cwd()
        try:
            os.chdir(run_block)
            plan_before_f2_done = mod.plan_execution_chains(mod.build_execution_chain_dag(run_block))
        finally:
            os.chdir(old_cwd)
        f8_before = next(e for e in plan_before_f2_done["chain_stats"] if e["root_ref"] == "F8")
        # Completing F1 turns F4 into a 1-open-task ready work finale (Chain 1), followed by F8 (Chain 2) ahead of F7
        self.assertEqual([e["root_ref"] for e in plan_before_f2_done["chain_stats"]], ["F4", "F8", "F7"])

        # Complete WIP task F2 -> remaining open tasks in F8 chain are F3 (NEW) and F8 (NEW)!
        self._run([str(SCRIPT), "done", "F2", "-m", "done"], cwd=str(run_block), check=True)
        old_cwd = Path.cwd()
        try:
            os.chdir(run_block)
            plan_after_f2_done = mod.plan_execution_chains(mod.build_execution_chain_dag(run_block))
        finally:
            os.chdir(old_cwd)
        f8_after = next(e for e in plan_after_f2_done["chain_stats"] if e["root_ref"] == "F8")
        self.assertTrue(f8_after["is_active_quest"])
        self.assertEqual(f8_after["best_status"], 0)
        self.assertLessEqual(f8_after["rank_key"], f8_before["rank_key"])
        self.assertLessEqual(f8_after["rank_key"][:-1], rank_key_before_done[:-1])
        self.assertEqual([e["root_ref"] for e in plan_after_f2_done["chain_stats"]], ["F4", "F8", "F7"])

        # Also verify local DONE task highlighting and dimming under `todo_md chain --all`:
        r_all_local_done = self._run([str(SCRIPT), "chain", "--numbered=right", "--all"], cwd=str(run_block), env=color_env, check=True)
        self.assertTrue(
            any(ln.startswith("\033[2;90m") and " F1 " in ln and "✅ [DONE]" in ln for ln in r_all_local_done.stdout.splitlines()),
            msg=r_all_local_done.stdout,
        )
        r_all_hl_local_done = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--all", "F1"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and " F1 " in ln and "✅ [DONE]" in ln for ln in r_all_hl_local_done.stdout.splitlines()),
            msg=r_all_hl_local_done.stdout,
        )

    def test_nested_milestone_subchains_tree_connectors_and_multiline_wrapped_bars(self):
        mod = self.todo_md_mod

        # 1. Direct unit test for _wrap_table_row() with cont_prefix preserving vertical bars
        prefix = "  │   ├─ 1. F1            🎯 [NEXT]       [work]      "
        desc = (
            "Long nested sub-chain task description that wraps cleanly across multiple lines "
            "without ellipsis truncation while keeping active vertical tree bars"
        )
        wrapped_80 = mod._wrap_table_row(prefix, desc, term_width=80, cont_prefix="  │   │   ")
        w_lines = wrapped_80.splitlines()
        self.assertGreaterEqual(len(w_lines), 3, msg=wrapped_80)
        self.assertTrue(w_lines[0].startswith(prefix), msg=wrapped_80)
        for cont_line in w_lines[1:]:
            self.assertTrue(cont_line.startswith("  │   │   "), msg=cont_line)
            self.assertEqual(cont_line.index(cont_line.lstrip(" │")), mod._display_width(prefix), msg=cont_line)
            self.assertLessEqual(mod._display_width(cont_line), 80, msg=cont_line)
        self.assertNotIn("...", wrapped_80)

        # Narrow terminal fallback with cont_prefix still preserves tree bars
        wrapped_narrow = mod._wrap_table_row(prefix, desc, term_width=64, cont_prefix="  │   │   ")
        n_lines = wrapped_narrow.splitlines()
        self.assertGreaterEqual(len(n_lines), 2, msg=wrapped_narrow)
        for cont_line in n_lines[1:]:
            self.assertTrue(cont_line.startswith("  │   │   "), msg=cont_line)
            self.assertLessEqual(mod._display_width(cont_line), 64, msg=cont_line)

        # 2. Multi-project workspace with nested milestone sub-chains, DONE prerequisites, and long titles
        ws = self.tmp / "ws_f53"
        todo_flow = ws / "todo_flow"
        run_block = ws / "run_block"
        for d in (todo_flow, run_block):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "init"], cwd=str(d), check=True)
        (todo_flow / ".todo_projects").write_text("run_block\n", encoding="utf-8")

        base_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")}
        wide_env = {**base_env, "COLUMNS": "220"}
        wrap_env = {**base_env, "COLUMNS": "82"}
        color_wrap_env = {**base_env, "FORCE_COLOR": "1", "COLUMNS": "82"}

        # External DONE prerequisite in todo_flow: D1
        self._run(
            [str(SCRIPT), "add", "D", "Completed external architecture foundation spec"],
            cwd=str(todo_flow),
            check=True,
        )
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(todo_flow), check=True)

        # External open milestone in todo_flow: F1 (depends on D1 and local F2)
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "External parser prerequisite with a comprehensive multi-line wrapped description for sub-chain testing",
                "--next",
                "--depends",
                "D1",
            ],
            cwd=str(todo_flow),
            check=True,
        )
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "External milestone aggregator combining completed foundation and open parser prerequisite",
                "--next",
                "--depends",
                "F1",
            ],
            cwd=str(todo_flow),
            check=True,
        )

        # In run_block:
        # - F1: leaf prerequisite (ready)
        # - F2: intermediate milestone depending on todo_flow:F2 and local F1
        # - F3: parallel sibling prerequisite feeding directly into root F4
        # - F4: closing root task depending on F2 and F3
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Local engine prerequisite with detailed description verifying wrapped tree continuation bars",
                "--next",
            ],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Local intermediate milestone integrating external aggregator and local engine prerequisite",
                "--next",
                "--depends",
                "todo_flow:F2, F1",
            ],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Parallel sibling verification suite feeding directly into the closing release goal",
                "--next",
            ],
            cwd=str(run_block),
            check=True,
        )
        self._run(
            [
                str(SCRIPT),
                "add",
                "F",
                "Closing root questline goal delivering nested milestone sub-chains and wrapped tree rows",
                "--next",
                "--depends",
                "F2, F3",
            ],
            cwd=str(run_block),
            check=True,
        )

        # 3. Default `todo_md chain` (without --all) renders nested Sub-chain headers, ├── / │   / └─► connectors
        r_wide = self._run([str(SCRIPT), "chain", "--tree", "--numbered=right"], cwd=str(run_block), env=wide_env, check=True)
        out_wide = r_wide.stdout
        self.assertIn(
            "Chain 1 -> F4: Closing root questline goal delivering nested milestone sub-chains and wrapped tree rows "
            "[14% | done: 1, open: 6]:",
            out_wide,
        )
        # Outer Sub-chain -> F2 (1 done + 4 open = 5 tasks -> 20% | done: 1, open: 4)
        self.assertIn(
            "  ├── Sub-chain -> F2: Local intermediate milestone integrating external aggregator and local engine prerequisite "
            "[20% | done: 1, open: 4]:",
            out_wide,
        )
        # Inner Sub-chain -> todo_flow:F2 (1 done + 2 open = 3 tasks -> 33% | done: 1, open: 2)
        self.assertIn(
            "  │   ├── Sub-chain -> todo_flow:F2: External milestone aggregator combining completed foundation and open parser prerequisite "
            "[33% | done: 1, open: 2]:",
            out_wide,
        )
        # Verify tree connectors:
        # - todo_flow:F1 inside inner Sub-chain has `│   │   ├── 1 todo_flow:F1`
        # - todo_flow:F2 closes inner Sub-chain with `│   │   └─► 2 todo_flow:F2`
        # - F1 inside outer Sub-chain has `│   ├── 3 F1`
        # - F2 closes outer Sub-chain with `│   └─► 4 F2`
        # - F3 at top chain level has `├── 5 F3`
        # - F4 closes Chain 1 with `└─► 6 F4`
        self.assertIn("  │   │   ├── 1 todo_flow:F1", out_wide)
        self.assertIn("  │   │   └─► 2 todo_flow:F2", out_wide)
        self.assertIn("  │   ├── 3 F1", out_wide)
        self.assertIn("  │   └─► 4 F2", out_wide)
        self.assertIn("  ├── 5 F3", out_wide)
        self.assertIn("  └─► 6 F4", out_wide)
        self.assertNotIn("todo_flow:D1", out_wide)

        # 4. With `--all`, DONE prerequisite todo_flow:D1 becomes visible inside the inner Sub-chain,
        # and turning todo_flow:F1 into a DONE-backed sub-chain (50% | 1 done, 1 open)!
        r_all_wide = self._run([str(SCRIPT), "chain", "--tree", "--numbered=right", "--all"], cwd=str(run_block), env=wide_env, check=True)
        out_all_wide = r_all_wide.stdout
        self.assertIn(
            "  │   │   ├── Sub-chain -> todo_flow:F1: External parser prerequisite with a comprehensive multi-line wrapped description for sub-chain testing "
            "[50% | done: 1, open: 1]:",
            out_all_wide,
        )
        self.assertIn("  │   │   │   ├── 1 todo_flow:D1", out_all_wide)
        self.assertIn("  │   │   │   └─► 2 todo_flow:F1", out_all_wide)
        self.assertIn("  │   │   └─► 3 todo_flow:F2", out_all_wide)
        self.assertIn("  │   ├── 4 F1", out_all_wide)
        self.assertIn("  │   └─► 5 F2", out_all_wide)
        self.assertIn("  ├── 6 F3", out_all_wide)
        self.assertIn("  └─► 7 F4", out_all_wide)

        # 5. Multi-line wrapping at COLUMNS=82 preserves active vertical bars (`│   `) on wrapped continuation lines
        # without `...` truncation, and composes cleanly with ANSI styling (`_style_task_row()`)
        r_wrap_plain = self._run(
            [str(SCRIPT), "chain", "--tree", "--numbered=right", "--all", "run_block:F2", "todo_flow:D1"],
            cwd=str(run_block),
            env=wrap_env,
            check=True,
        )
        r_wrap_color = self._run(
            [str(SCRIPT), "chain", "--tree", "--numbered=right", "--all", "run_block:F2", "todo_flow:D1"],
            cwd=str(run_block),
            env=color_wrap_env,
            check=True,
        )
        plain_lines = r_wrap_plain.stdout.splitlines()
        color_lines = r_wrap_color.stdout.splitlines()
        self.assertEqual(mod._strip_ansi(r_wrap_color.stdout), r_wrap_plain.stdout)
        self.assertNotIn("...", r_wrap_plain.stdout)

        # Wrapped continuation lines inside nested sub-chains keep vertical bars `│   `
        self.assertTrue(
            any(ln.startswith("  │   │   │   │   ") and "Completed external architecture" not in ln for ln in plain_lines),
            msg=r_wrap_plain.stdout,
        )
        self.assertTrue(
            any(ln.startswith("  │   │   ") and "Local engine prerequisite" not in ln for ln in plain_lines),
            msg=r_wrap_plain.stdout,
        )
        for ln in plain_lines:
            if ln.startswith("  "):
                self.assertLessEqual(mod._display_width(ln), 82, msg=f"overflowed 82 cols: {ln!r}")

        # Verify composable ANSI styling across wrapped lines and tree connectors:
        # - Highlighted external DONE task `todo_flow:D1` -> \033[1;3;93m on both first line and wrapped continuation line
        d1_idx = next(i for i, ln in enumerate(color_lines) if "1 todo_flow:D1" in ln)
        self.assertTrue(color_lines[d1_idx].startswith("\033[1;3;93m  │   │   │   ├── 1 todo_flow:D1"), msg=color_lines[d1_idx])
        self.assertTrue(color_lines[d1_idx + 1].startswith("\033[1;3;93m  │   │   │   │   "), msg=color_lines[d1_idx + 1])

        # - Unhighlighted external open task `todo_flow:F2` -> \033[2;3m on both first line and wrapped continuation line
        ext_f2_idx = next(i for i, ln in enumerate(color_lines) if "3 todo_flow:F2" in ln)
        self.assertTrue(color_lines[ext_f2_idx].startswith("\033[2;3m  │   │   └─► 3 todo_flow:F2"), msg=color_lines[ext_f2_idx])
        self.assertTrue(color_lines[ext_f2_idx + 1].startswith("\033[2;3m  │   "), msg=color_lines[ext_f2_idx + 1])

        # - Highlighted local milestone `F2` -> \033[1;93m on both Sub-chain header and closing milestone row + continuation
        sub_f2_idx = next(i for i, ln in enumerate(color_lines) if "Sub-chain -> F2:" in ln)
        self.assertTrue(color_lines[sub_f2_idx].startswith("\033[1;93m  ├── Sub-chain -> F2:"), msg=color_lines[sub_f2_idx])
        row_f2_idx = next(i for i, ln in enumerate(color_lines) if "5 F2 " in ln)
        self.assertTrue(color_lines[row_f2_idx].startswith("\033[1;93m  │   └─► 5 F2"), msg=color_lines[row_f2_idx])
        self.assertTrue(color_lines[row_f2_idx + 1].startswith("\033[1;93m  │   "), msg=color_lines[row_f2_idx + 1])


    def test_flat_default_tree_flag_numbered_alignment_and_short_limit(self):
        proj = self.tmp / "flatproj"
        proj.mkdir()
        self._run([str(SCRIPT), "-C", str(proj), "init"], check=True)
        for n in range(1, 11):
            add_args = [str(SCRIPT), "add", f"Task {n}"]
            if n > 1:
                add_args += ["--depends", f"F{n - 1}"]
            self._run(add_args, cwd=str(proj), check=True)
        expected_refs = [f"F{n}" for n in range(1, 11)]

        # Default: flat topological rows without numbers, connectors, or Sub-chain headers
        out = self._run([str(SCRIPT), "chain"], cwd=str(proj), check=True).stdout
        self.assertIn("Chain 1 -> F10: Task 10", out)
        for banned in ("├", "└", "│", "Sub-chain"):
            self.assertNotIn(banned, out)
        self.assertIsNone(re.search(r"^\s+\d+\s+F\d+\b", out, re.M), msg=out)
        self.assertEqual(re.findall(r"^  (F\d+) ", out, re.M), expected_refs, msg=out)

        # --tree / -t: 4-char connectors, closing task flush with siblings
        out_tree = self._run([str(SCRIPT), "chain", "--tree"], cwd=str(proj), check=True).stdout
        out_t = self._run([str(SCRIPT), "chain", "-t"], cwd=str(proj), check=True).stdout
        self.assertEqual(out_tree, out_t)
        self.assertIn("  ├── F1 ", out_tree)
        self.assertIn("  └─► F10 ", out_tree)
        self.assertEqual(
            re.findall(r"^  (?:│   )*[├└]─[─►] (F\d+) ", out_tree, re.M), expected_refs, msg=out_tree
        )

        # --numbered[=left|right]: period-free numbers padded to len(str(total_rows)) == 2
        out_left = self._run([str(SCRIPT), "chain", "--numbered"], cwd=str(proj), check=True).stdout
        out_left_exp = self._run([str(SCRIPT), "chain", "--numbered=left"], cwd=str(proj), check=True).stdout
        self.assertEqual(out_left, out_left_exp)
        self.assertIsNotNone(re.search(r"^  1  F1 ", out_left, re.M), msg=out_left)
        self.assertIsNotNone(re.search(r"^  10 F10 ", out_left, re.M), msg=out_left)
        out_right = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj), check=True).stdout
        self.assertIsNotNone(re.search(r"^   1 F1 ", out_right, re.M), msg=out_right)
        self.assertIsNotNone(re.search(r"^  10 F10 ", out_right, re.M), msg=out_right)
        out_tree_num = self._run(
            [str(SCRIPT), "chain", "--tree", "--numbered"], cwd=str(proj), check=True
        ).stdout
        self.assertIn("├── 1  F1 ", out_tree_num, msg=out_tree_num)
        self.assertIn("└─► 10 F10 ", out_tree_num, msg=out_tree_num)
        r_bad = self._run([str(SCRIPT), "chain", "--numbered=middle"], cwd=str(proj))
        self.assertNotEqual(r_bad.returncode, 0, msg=r_bad.stdout)

        # -l N / --limit N, with -n N kept as a backward-compatible alias
        r_l = self._run([str(SCRIPT), "chain", "-l", "2"], cwd=str(proj), check=True).stdout
        r_n = self._run([str(SCRIPT), "chain", "-n", "2"], cwd=str(proj), check=True).stdout
        r_long = self._run([str(SCRIPT), "chain", "--limit", "2"], cwd=str(proj), check=True).stdout
        self.assertEqual(r_l, r_n)
        self.assertEqual(r_l, r_long)
        self.assertEqual(re.findall(r"^  (F\d+) ", r_l, re.M), ["F1", "F2"], msg=r_l)

    def test_unify_filter_search_highlight_toggle_and_all_across_todo_projects(self):
        ws = self.tmp / "unify_ws"
        todo_flow = ws / "todo_flow"
        todo_md_p = ws / "todo_md"
        run_block_p = ws / "run_block"
        for d in (todo_flow, todo_md_p, run_block_p):
            d.mkdir(parents=True)
            self._run([str(SCRIPT), "-C", str(d), "init"], check=True)

        # Configure .todo_projects inside orchestrator todo_flow
        (todo_flow / ".todo_projects").write_text("todo_flow\ntodo_md\nrun_block\n", encoding="utf-8")

        # Add tasks with overlapping IDs across projects + archived DONE/CANCELED tasks
        self._run(
            [str(SCRIPT), "-C", str(todo_md_p), "add", "Nested todo_projects support", "--next"],
            check=True,
        )  # todo_md:F1
        self._run(
            [str(SCRIPT), "-C", str(todo_md_p), "add", "Archived completed leaf task", "--next"],
            check=True,
        )  # todo_md:F2
        self._run([str(SCRIPT), "-C", str(todo_md_p), "done", "F2", "-m", "done"], check=True)

        self._run(
            [str(SCRIPT), "-C", str(run_block_p), "add", "Runner isolation", "--next"],
            check=True,
        )  # run_block:F1
        self._run(
            [str(SCRIPT), "-C", str(run_block_p), "add", "Dropped experiment", "--next"],
            check=True,
        )  # run_block:F2
        self._run([str(SCRIPT), "-C", str(run_block_p), "cancel", "F2", "-m", "superseded"], check=True)

        self._run(
            [
                str(SCRIPT),
                "-C",
                str(todo_flow),
                "add",
                "Orchestrator rollout",
                "--next",
                "--depends",
                "todo_md:F1",
                "-b",
                "Coordinates rollout after todo_md:F1 lands.",
            ],
            check=True,
        )  # todo_flow:F1

        base_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")}
        color_env = {**base_env, "FORCE_COLOR": "1", "COLUMNS": "140"}

        # 1. Bare -f F1 matches all tasks with ID F1 across all projects in active view
        r_bare_f = self._run([str(SCRIPT), "-f", "F1"], cwd=str(todo_flow), env=color_env, check=True)
        plain_bare_f = self.todo_md_mod._strip_ansi(r_bare_f.stdout)
        self.assertIn("todo_md:F1", plain_bare_f)
        self.assertIn("F1", plain_bare_f)
        self.assertIn("run_block:F1", plain_bare_f)
        for expected_tok in ("todo_md:F1", "F1 ", "run_block:F1"):
            self.assertTrue(
                any("\033[" in ln and "93m" in ln and expected_tok in ln for ln in r_bare_f.stdout.splitlines()),
                msg=f"expected {expected_tok!r} to be highlighted in:\n{r_bare_f.stdout}",
            )

        # 2. Project-qualified -f todo_md:F1 matches ONLY todo_md:F1 (not run_block:F1 or local todo_flow:F1)
        r_qual_f = self._run([str(SCRIPT), "-f", "todo_md:F1"], cwd=str(todo_flow), env=color_env, check=True)
        plain_qual_f = self.todo_md_mod._strip_ansi(r_qual_f.stdout)
        self.assertIn("todo_md:F1", plain_qual_f)
        self.assertNotIn("run_block:F1", plain_qual_f)
        self.assertIn("Next actionable: todo_md:F1", plain_qual_f)
        self.assertTrue(
            any("\033[" in ln and "93m" in ln and "todo_md:F1" in ln for ln in r_qual_f.stdout.splitlines()),
            msg=r_qual_f.stdout,
        )
        self.assertFalse(
            any(
                "\033[" in ln and "93m" in ln and "  F1 " in ln
                for ln in r_qual_f.stdout.splitlines()
            ),
            msg=r_qual_f.stdout,
        )

        # Project-qualified -f todo_flow:F1 matches ONLY todo_flow:F1 (not todo_md:F1 or run_block:F1)
        r_flow_f = self._run([str(SCRIPT), "-f", "todo_flow:F1"], cwd=str(todo_flow), env=color_env, check=True)
        plain_flow_f = self.todo_md_mod._strip_ansi(r_flow_f.stdout)
        self.assertNotIn("run_block:F1", plain_flow_f)
        self.assertTrue(
            any(
                "\033[" in ln and "93m" in ln and "Orchestrator rollout" in ln
                for ln in r_flow_f.stdout.splitlines()
            ),
            msg=r_flow_f.stdout,
        )
        self.assertFalse(
            any("\033[" in ln and "93m" in ln and "  todo_md:F1 " in ln for ln in r_flow_f.stdout.splitlines()),
            msg=r_flow_f.stdout,
        )

        # 3. -H / --highlight disables focus and renders the full Quest-Log with matched tasks highlighted
        r_qual_hl = self._run(
            [str(SCRIPT), "-f", "todo_md:F1", "-H"], cwd=str(todo_flow), env=color_env, check=True
        )
        plain_qual_hl = self.todo_md_mod._strip_ansi(r_qual_hl.stdout)
        self.assertIn("todo_md:F1", plain_qual_hl)
        self.assertIn("run_block:F1", plain_qual_hl)
        self.assertNotIn("Next actionable:", plain_qual_hl)
        self.assertTrue(
            any("\033[" in ln and "93m" in ln and "todo_md:F1" in ln for ln in r_qual_hl.stdout.splitlines()),
            msg=r_qual_hl.stdout,
        )
        self.assertFalse(
            any("\033[" in ln and "93m" in ln and "run_block:F1" in ln for ln in r_qual_hl.stdout.splitlines()),
            msg=r_qual_hl.stdout,
        )
        # Shorthand -H todo_md:F1 equals -f todo_md:F1 -H
        r_shorthand_hl = self._run(
            [str(SCRIPT), "-H", "todo_md:F1"], cwd=str(todo_flow), env=color_env, check=True
        )
        self.assertEqual(r_qual_hl.stdout, r_shorthand_hl.stdout)

        # 4. -s / --search inside orchestrator without -w searches across all .todo_projects (ID, <project>:<ID>, title, body)
        r_s_id = self._run([str(SCRIPT), "-s", "todo_md:F1"], cwd=str(todo_flow), env=color_env, check=True)
        plain_s_id = self.todo_md_mod._strip_ansi(r_s_id.stdout)
        self.assertIn("todo_md:F1", plain_s_id)
        self.assertIn("Orchestrator rollout", plain_s_id)
        self.assertNotIn("run_block:F1", plain_s_id)

        r_s_hl = self._run(
            [str(SCRIPT), "-s", "Runner isolation", "-H"], cwd=str(todo_flow), env=color_env, check=True
        )
        plain_s_hl = self.todo_md_mod._strip_ansi(r_s_hl.stdout)
        self.assertIn("todo_md:F1", plain_s_hl)
        self.assertIn("run_block:F1", plain_s_hl)
        self.assertTrue(
            any("\033[" in ln and "93m" in ln and "run_block:F1" in ln for ln in r_s_hl.stdout.splitlines()),
            msg=r_s_hl.stdout,
        )
        self.assertFalse(
            any("\033[" in ln and "93m" in ln and "todo_md:F1" in ln for ln in r_s_hl.stdout.splitlines()),
            msg=r_s_hl.stdout,
        )

        # 5. --all unifies active and archived (DONE/CANCELED) tasks across Quest-Log, -s, and -f
        r_all_s_done = self._run(
            [str(SCRIPT), "--all", "-s", "Archived completed leaf"], cwd=str(todo_flow), check=True
        )
        self.assertIn("todo_md:F2", r_all_s_done.stdout)
        self.assertIn("✅ [DONE]", r_all_s_done.stdout)
        self.assertNotIn("run_block:F2", r_all_s_done.stdout)

        r_all_f_canc = self._run(
            [str(SCRIPT), "--all", "-f", "run_block:F2"], cwd=str(todo_flow), check=True
        )
        self.assertIn("run_block:F2", r_all_f_canc.stdout)
        self.assertIn("❌ [CANCELED]", r_all_f_canc.stdout)
        self.assertNotIn("todo_md:F2", r_all_f_canc.stdout)

        # Archive status filter with -f / -s scopes to matched archived tasks unless -H is set
        r_arch_scoped = self._run(
            [str(SCRIPT), "-w", "ARCHIVE", "-f", "todo_md:F2"], cwd=str(todo_flow), check=True
        )
        self.assertIn("todo_md:F2", r_arch_scoped.stdout)
        self.assertNotIn("run_block:F2", r_arch_scoped.stdout)

        r_arch_hl = self._run(
            [str(SCRIPT), "-w", "ARCHIVE", "-f", "todo_md:F2", "-H"], cwd=str(todo_flow), check=True
        )
        self.assertIn("todo_md:F2", r_arch_hl.stdout)
        self.assertIn("run_block:F2", r_arch_hl.stdout)

    def test_chain_tree_subchain_stats_scope_to_rendered_subtree(self):
        proj = self.tmp / "diamond"
        proj.mkdir()
        self._run([str(SCRIPT), "-C", str(proj), "init"], check=True)

        def add(title, deps=None, kind="F"):
            args = [str(SCRIPT), "add", kind, title]
            if deps:
                args += ["--depends", deps]
            self._run(args, cwd=str(proj), check=True)

        add("Completed base", kind="D")
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(proj), check=True)
        add("Shared leaf", "D1")
        add("Shared milestone", "F1")
        add("Left extra")
        add("Right extra")
        add("Left branch", "F2,F3")
        add("Right branch", "F2,F4")
        add("Final", "F5,F6")

        base_env = {
            k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")
        }
        env = {**base_env, "COLUMNS": "200"}

        def headers(out):
            return {
                m.group(1): m.group(2)
                for m in re.finditer(r"Sub-chain -> (\S+): .*? (\[[^\]]*\]):$", out, re.M)
            }

        out = self._run([str(SCRIPT), "chain", "--tree"], cwd=str(proj), env=env, check=True).stdout
        h = headers(out)
        self.assertEqual(h["F2"], "[33% | done: 1, open: 2]", msg=out)
        self.assertEqual(sorted([h["F5"], h["F6"]]), ["[20% | done: 1, open: 4]", "[open: 2]"], msg=out)
        self.assertNotIn("F1", h, msg=out)

        out_all = self._run([str(SCRIPT), "chain", "--tree", "--all"], cwd=str(proj), env=env, check=True).stdout
        h_all = headers(out_all)
        self.assertEqual(h_all["F1"], "[50% | done: 1, open: 1]", msg=out_all)
        self.assertEqual(h_all["F2"], "[33% | done: 1, open: 2]", msg=out_all)
        self.assertEqual(
            sorted([h_all["F5"], h_all["F6"]]), ["[20% | done: 1, open: 4]", "[open: 2]"], msg=out_all
        )

        color_env = {**env, "FORCE_COLOR": "1"}
        out_hl = self._run(
            [str(SCRIPT), "chain", "--tree", "-H", "F1"], cwd=str(proj), env=color_env, check=True
        ).stdout
        branch_hdrs = [ln for ln in out_hl.splitlines() if "Sub-chain -> F5:" in ln or "Sub-chain -> F6:" in ln]
        self.assertEqual(len(branch_hdrs), 2, msg=out_hl)
        self.assertEqual(sum("\033[1;93m" in ln for ln in branch_hdrs), 1, msg=out_hl)

    def test_chain_nested_orchestrators_and_external_path_alias(self):
        import os

        ws = self.tmp / "ws_nested"
        home = self.tmp / "home_nested"
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
        env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("TODO_MD_PROJECTS", "TODO_MD_WORKSPACE", "TODO_MD_CWD")
        }
        env["HOME"] = str(home)
        self._run(
            [str(SCRIPT), "add", "F", "Canary base", "--next"],
            cwd=str(canary), env=env, check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Leaf consumer", "--next", "--depends", "chrome/canary:F1"],
            cwd=str(todo_md_p), env=env, check=True,
        )
        for cwd in (todo_md_p, todo_flow, meta_orch):
            with self.subTest(cwd=cwd.name):
                r = self._run([str(SCRIPT), "chain"], cwd=str(cwd), env=env, check=True)
                flat = self._flat_text(r.stdout)
                self.assertIn("chrome/canary:F1", flat, msg=r.stdout)
                self.assertIn("Canary base", flat, msg=r.stdout)
        r_c = self._run(
            [str(SCRIPT), "-C", "chrome/canary", "show", "F1"],
            cwd=str(todo_md_p), env=env, check=True,
        )
        self.assertIn("Canary base", r_c.stdout)

    def test_ready_ranking_follows_top_chain_priority(self):
        proj = self.tmp / "readychain"
        proj.mkdir()
        self._run([str(SCRIPT), "-C", str(proj), "init"], check=True)
        self._run([str(SCRIPT), "add", "F", "Chain A head", "--next"], cwd=str(proj), check=True)
        self._run(
            [str(SCRIPT), "add", "B", "Chain A bug", "--next", "--depends", "F1"],
            cwd=str(proj),
            check=True,
        )
        self._run([str(SCRIPT), "add", "F", "Chain B head", "--next"], cwd=str(proj), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Chain B middle", "--next", "--depends", "F2"],
            cwd=str(proj),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Chain B tail", "--next", "--depends", "F3"],
            cwd=str(proj),
            check=True,
        )

        out_chain = self._run([str(SCRIPT), "chain"], cwd=str(proj), check=True).stdout
        self.assertIn("Chain 1 -> B1", out_chain)

        out_ready = self._run([str(SCRIPT), "chain", "--ready"], cwd=str(proj), check=True).stdout
        self.assertIn("Chain A head", out_ready)
        self.assertIn("Chain B head", out_ready)
        self.assertLess(out_ready.index("Chain A head"), out_ready.index("Chain B head"), msg=out_ready)


if __name__ == "__main__":
    unittest.main()
