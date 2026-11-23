#!/usr/bin/env python3
"""Tests for todo_md chain dependency tree rendering, Quest Momentum, and orchestrator scoping."""

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
        self.assertIn("25% · 1/4 · Chain 1 -> F4: Step C:", r_local.stdout)
        self.assertNotIn("F1", r_local.stdout)
        self.assertIn("Held branches:", r_local.stdout)
        self.assertIn("F5 (HOLD) -> F6 (NEW)", r_local.stdout)
        self.assertLess(r_local.stdout.index("1 F2"), r_local.stdout.index("2 F3"))
        self.assertLess(r_local.stdout.index("2 F3"), r_local.stdout.index("3 F4"))

        # --limit N truncates displayed chain rows while preserving RPG progress header
        r_lim = self._run([str(SCRIPT), "chain", "--numbered=right", "--limit", "2"], cwd=str(proj_a), check=True)
        self.assertIn("25% · 1/4 · Chain 1 -> F4: Step C:", r_lim.stdout)
        self.assertIn("1 F2", r_lim.stdout)
        self.assertIn("2 F3", r_lim.stdout)
        self.assertNotIn("1 F4", r_lim.stdout)
        self.assertNotIn("3 F4", r_lim.stdout)
        self.assertIn("Held branches:", r_lim.stdout)

        # --include-hold brings HOLD tasks and their dependents into the main chain view
        r_inc = self._run([str(SCRIPT), "chain", "--numbered=right", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertIn("25% · 1/4 · Chain 1 -> F4: Step C:", r_inc.stdout)
        self.assertIn("0% · 0/2 · Chain 2 -> F6: Blocked by hold:", r_inc.stdout)
        self.assertIn("F5", r_inc.stdout)
        self.assertIn("F6", r_inc.stdout)
        self.assertNotIn("Held branches:", r_inc.stdout)

        # Cross-project dependency in proj_b resolved locally and across workspace (-w / auto-workspace)
        (proj_b / "TODO.md").write_text(
            "# ⚪ [NEW] F1: Cross child\n\n- Depends on: proj_a:F3\n\n"
            "# ⚪ [NEW] F2: Cross leaf\n\n- Depends on: F1\n",
            encoding="utf-8",
        )
        r_b_local = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj_b), check=True)
        self.assertIn("20% · 1/5 · Chain 1 -> F2: Cross leaf:", r_b_local.stdout)
        self.assertIn("proj_a:F2", r_b_local.stdout)
        self.assertIn("proj_a:F3", r_b_local.stdout)

        r_ws = self._run([str(SCRIPT), "chain", "--numbered=right", "-w"], cwd=str(proj_a), check=True)
        self.assertIn("25% · 1/4 · Chain 1 -> proj_a:F4: Step C:", r_ws.stdout)
        self.assertIn("20% · 1/5 · Chain 2 -> proj_b:F2: Cross leaf:", r_ws.stdout)
        self.assertIn("🔗 also in: proj_b:F2", self._flat_text(r_ws.stdout))
        self.assertIn("🔗 also in: proj_a:F4", self._flat_text(r_ws.stdout))
        self.assertIn("proj_a:F2", r_ws.stdout)
        self.assertIn("proj_b:F1", r_ws.stdout)
        self.assertIn("proj_b:F2", r_ws.stdout)
        self.assertIn("proj_a:F5 (HOLD) -> proj_a:F6 (NEW)", r_ws.stdout)

        # Auto-workspace from workspace root and -C selector
        r_ws_root = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(ws), check=True)
        self.assertIn("25% · 1/4 · Chain 1 -> proj_a:F4: Step C:", r_ws_root.stdout)
        self.assertIn("20% · 1/5 · Chain 2 -> proj_b:F2: Cross leaf:", r_ws_root.stdout)
        self.assertIn("proj_b:F1", r_ws_root.stdout)
        self.assertIn("proj_b:F2", r_ws_root.stdout)
        r_c = self._run([str(SCRIPT), "-C", "proj_b", "chain"], cwd=str(ws), check=True)
        self.assertIn("20% · 1/5 · Chain 1 -> proj_b:F2: Cross leaf:", r_c.stdout)

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
        self.assertIn("0% · 0/3 · Chain 1 -> F7: Deep leaf:", out)
        self.assertIn("0% · 0/2 · Chain 2 -> F4: Med leaf:", out)
        self.assertIn("Standalone tasks:", out)
        self.assertLess(
            out.index("0% · 0/3 · Chain 1 -> F7: Deep leaf:"),
            out.index("0% · 0/2 · Chain 2 -> F4: Med leaf:"),
        )
        self.assertLess(out.index("1 F5"), out.index("4 F3"))
        self.assertLess(
            out.index("0% · 0/2 · Chain 2 -> F4: Med leaf:"),
            out.index("Standalone tasks:"),
        )
        self.assertNotIn("F7 -> F3", out)
        self.assertNotIn("F4 -> F1", out)
        self.assertNotIn("F1 -> F2", out)
        self.assertIn("🟢 ready · 🔓 unblocks: 2", out)
        self.assertIn("🟢 ready · 🔓 unblocks: 1", out)

        # --ready filters to ready tasks only, ranks highest-leverage ready tasks first,
        # and shows unified RPG stat tags (omitting the tag on zero-stat standalone tasks)
        r_ready = self._run([str(SCRIPT), "chain", "--numbered=right", "--ready"], cwd=str(proj), check=True)
        r_out = r_ready.stdout
        self.assertIn("Ready tasks:", r_out)
        ready_rows = self._table_rows(r_out)
        self.assertEqual(sorted(ready_rows), ["1.", "2.", "3.", "4."], msg=r_out)
        self.assertIn("F5", ready_rows["1."])
        self.assertIn("🟢 ready: +1 · 🔓 unblocks: 2", ready_rows["1."])
        self.assertNotIn("F7", r_out)
        self.assertIn("F3", ready_rows["2."])
        self.assertIn("🟢 ready: +1 · 🔓 unblocks: 1", ready_rows["2."])
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
        self.assertIn("🟢 ready: +1 · 🔓 unblocks: 3", rows["1."])
        self.assertIn("F1", rows["2."])
        self.assertIn("⛓️ chain: 2 · 🟢 ready: +2 · 🔓 unblocks: 2", rows["2."])
        # Status tier: NEXT tasks rank ahead of the NEW D1 task
        self.assertIn("D1", rows["3."])
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
        self.assertIn("⚡ STAGE · 🔥 COMBO · 🟢 ready: +1 · 🔓 unblocks: 1", rows["1."])
        self.assertIn("F3", rows["2."])
        self.assertIn("⛓️ chain: 2 · 🟢 ready: +2 · 🔓 unblocks: 2", rows["2."])

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
                self.assertIn("🔓 unblocks: 1", rows[key], msg=r_ready.stdout)
                self.assertNotIn("ready: +", rows[key])
                self.assertNotIn("chain:", rows[key])

    def test_chain_prefix_and_status_filters(self):
        ws = self.tmp / "ws_chain_prefix"
        proj_a = ws / "proj_a"
        proj_b = ws / "proj_b"
        proj_a.mkdir(parents=True)
        proj_b.mkdir(parents=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "init"], cwd=str(proj_b), check=True)

        # Chain in proj_a: D1 (NEXT) -> F1 (NEXT) -> F2 (NEW)
        # Standalone in proj_a: L1 (NEW), B1 (NEXT)
        # Held branch in proj_a: D2 (HOLD) -> F3 (NEXT)
        self._run([str(SCRIPT), "add", "D", "Design schema", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Build backend", "--next", "--depends", "D1"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Plan rollout", "--depends", "F1"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "L", "Draft rule"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Ready bugfix", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "D", "Paused design", "--status", "HOLD"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "F", "Waiting work", "--next", "--depends", "D2"], cwd=str(proj_a), check=True)

        # Cross-project task in proj_b: F1 (NEXT, depends on proj_a:F1)
        (proj_b / "TODO.md").write_text(
            "# 🎯 [NEXT] F1: Cross repo work\n\n- Depends on: proj_a:F1\n",
            encoding="utf-8",
        )

        # 1. Default chain omits [role] column and ranks bugfix B1 ahead of non-bugfix tasks
        r_all = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(proj_a), env={**os.environ, "COLUMNS": "160"}, check=True)
        for role_tag in ("[design]", "[work]", "[plan]"):
            self.assertNotIn(role_tag, r_all.stdout)

        r_ready_all = self._run([str(SCRIPT), "chain", "--numbered=right", "--ready"], cwd=str(proj_a), check=True)
        ready_rows = self._table_rows(r_ready_all.stdout)
        self.assertIn("D1", ready_rows["1."])
        self.assertIn("B1", ready_rows["2."])
        self.assertIn("L1", ready_rows["3."])

        # 2. --prefix F filters Chain <N>, Standalone tasks:, and preserves unblock/blocker context & Held branches
        r_f = self._run([str(SCRIPT), "chain", "--numbered=right", "--prefix", "f"], cwd=str(proj_a), check=True)
        self.assertIn("0% · 0/3 · Chain 1 -> F2: Plan rollout:", r_f.stdout)
        self.assertIn("1 F1", r_f.stdout)
        self.assertIn("2 F2", r_f.stdout)
        self.assertIn("🔒 blocked by: D1 · 🔓 unblocks: 1", " ".join(r_f.stdout.split()))
        self.assertNotIn("D1: Design schema", r_f.stdout)
        self.assertNotIn("B1", r_f.stdout)
        self.assertNotIn("L1", r_f.stdout)
        self.assertIn("Held branches:", r_f.stdout)
        self.assertIn("D2 (HOLD) -> F3 (NEXT)", r_f.stdout)

        # 3. --prefix L hides unrelated held branches and chains
        r_l = self._run([str(SCRIPT), "chain", "--numbered=right", "--prefix=L"], cwd=str(proj_a), check=True)
        self.assertIn("Standalone tasks:", r_l.stdout)
        self.assertIn("L1", r_l.stdout)
        self.assertNotIn("Held branches:", r_l.stdout)
        self.assertNotIn("D1", r_l.stdout)
        self.assertNotIn("B1", r_l.stdout)

        # 4. --prefix with --ready, -w (workspace), and --limit
        r_ws_b_ready = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w", "--prefix", "B", "--ready"],
            cwd=str(ws),
            check=True,
        )
        self.assertIn("Ready tasks:", r_ws_b_ready.stdout)
        self.assertIn("proj_a:B1", r_ws_b_ready.stdout)
        self.assertNotIn("proj_a:D1", r_ws_b_ready.stdout)

        r_ws_f_lim = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w", "--prefix", "F", "--limit", "2"],
            cwd=str(ws),
            check=True,
        )
        lim_rows = {
            k: v for k, v in self._table_rows(r_ws_f_lim.stdout).items() if k.endswith(".")
        }
        self.assertEqual(sorted(lim_rows), ["1.", "2."], msg=r_ws_f_lim.stdout)

        # 5. Empty prefix match reports clean message; --include-hold brings in held matching tasks
        r_none = self._run([str(SCRIPT), "chain", "--numbered=right", "--prefix", "Z"], cwd=str(proj_a), check=True)
        self.assertIn("Chain: (none matching prefix=Z)", r_none.stdout)

        r_none_ready = self._run([str(SCRIPT), "chain", "--numbered=right", "--prefix", "Z", "--ready"], cwd=str(proj_a), check=True)
        self.assertIn("Ready tasks: (none matching prefix=Z)", r_none_ready.stdout)

        r_f_hold = self._run([str(SCRIPT), "chain", "--numbered=right", "--prefix", "F", "--include-hold"], cwd=str(proj_a), check=True)
        self.assertIn("F3", r_f_hold.stdout)
        self.assertNotIn("Held branches:", r_f_hold.stdout)

        # 6. MISSING placeholder renders without crashing and still surfaces DAG error
        miss_dir = ws / "miss_prefix"
        miss_dir.mkdir()
        self._run([str(SCRIPT), "init"], cwd=str(miss_dir), check=True)
        (miss_dir / "TODO.md").write_text("# 🎯 [NEXT] F1: Orphan\n\n- Depends on: F99\n", encoding="utf-8")
        r_miss = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss.returncode, 0, msg=r_miss.stderr)
        self.assertIn("⚠️ MISSING", r_miss.stdout)
        self.assertIn("unresolved blocker F99 (MISSING)", r_miss.stderr)

        r_miss_pref = self._run([str(SCRIPT), "chain", "--numbered=right", "--prefix", "F"], cwd=str(miss_dir))
        self.assertNotEqual(r_miss_pref.returncode, 0, msg=r_miss_pref.stderr)
        self.assertIn("F1", r_miss_pref.stdout)
        self.assertNotIn("⚠️ MISSING", r_miss_pref.stdout)
        self.assertIn("unresolved blocker F99 (MISSING)", r_miss_pref.stderr)

        # 7. Invalid --prefix values fail explicitly
        for bad_args in (
            ["chain", "--prefix"],
            ["chain", "--prefix", ""],
            ["chain", "--prefix="],
            ["chain", "--prefix", "AB"],
            ["chain", "--prefix", "a\nb"],
        ):
            with self.subTest(bad_args=bad_args):
                proc = self._run([str(SCRIPT), *bad_args], cwd=str(proj_a))
                self.assertNotEqual(proc.returncode, 0, msg=proc.stdout)

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
        (proj_b / "TODO.md").write_text(
            "# ⚪ [NEW] F1: Cross repo child\n\n- Depends on: proj_a:B1\n",
            encoding="utf-8",
        )

        r_local = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        rows = {k: v for k, v in self._table_rows(r_local.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(rows), ["1.", "2."], msg=r_local.stdout)
        # D1 has 5 active downstream tasks (F3, F2, F1, F4, F5), 4 immediate ready dependents,
        # and sits in 4 root chains (F1, F3, F4, F5), so it ranks ahead of standalone B1
        self.assertIn("D1", rows["1."])
        self.assertIn("⛓️ chain: 4 · 🟢 ready: +4 · 🔓 unblocks: 5", rows["1."])
        # B1's only local dependent is HOLD, so without --include-hold it has zero stats
        self.assertIn("B1", rows["2."])
        self.assertTrue(rows["2."].endswith("Ready bugfix"), msg=rows["2."])
        self.assertNotIn("unblocks", rows["2."])

        # --prefix D --ready keeps downstream unblock stats visible on D1
        r_pref = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready", "--prefix", "D"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        pref_rows = {k: v for k, v in self._table_rows(r_pref.stdout).items() if k.endswith(".")}
        self.assertEqual(sorted(pref_rows), ["1."], msg=r_pref.stdout)
        self.assertIn("⛓️ chain: 4 · 🟢 ready: +4 · 🔓 unblocks: 5", pref_rows["1."])

        # --include-hold includes the held dependent in --ready downstream stats (B1 chain ranks 1st as bug chain)
        r_hold = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--ready", "--include-hold"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        hold_rows = {k: v for k, v in self._table_rows(r_hold.stdout).items() if k.endswith(".")}
        self.assertIn("B1", hold_rows["1."])
        self.assertIn("🟢 ready: +1 · 🔓 unblocks: 1", hold_rows["1."])

        # Workspace -w --ready includes cross-project downstream unblock stats (B1 chain ranks 1st as bug chain)
        r_ws = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w", "--ready"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        ws_rows = {k: v for k, v in self._table_rows(r_ws.stdout).items() if k.endswith(".")}
        self.assertIn("proj_a:B1", ws_rows["1."])
        self.assertIn("🟢 ready: +1 · 🔓 unblocks: 1", ws_rows["1."])
        self.assertIn("proj_a:D1", ws_rows["2."])
        self.assertIn("⛓️ chain: 4 · 🟢 ready: +4 · 🔓 unblocks: 5", ws_rows["2."])

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
        (proj_b / "TODO.md").write_text(
            "# 🎯 [NEXT] F1: Cross finale\n\n- Depends on: proj_a:F3\n",
            encoding="utf-8",
        )

        # 1. Default chain: work chain finales render as top-ranked Chain 1..3 entries before open multi-task chains and plan chains
        r_chain = self._run(
            [str(SCRIPT), "chain", "--numbered=right"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_chain.stdout
        c1_hdr = "80% · 4/5 · Chain 1 -> F6: Finale next:"
        c2_hdr = "75% · 3/4 · Chain 2 -> F11: Long work finale:"
        c3_hdr = "50% · 1/2 · Chain 3 -> F10: Short work finale:"
        c4_hdr = "0% · 0/2 · Chain 4 -> F5: Chain leaf:"
        c5_hdr = "0% · 0/2 · Chain 5 -> F9: New chain leaf:"
        c6_hdr = "50% · 1/2 · Chain 6 -> F7: Plan after done:"
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
        self.assertIn("🟢 ready · 🏁 FINAL · 🔥 COMBO", fin_sec)
        self.assertIn("🟢 ready · 🏁 FINAL", fin_sec)
        self.assertNotIn("B1", fin_sec)

        chain6_sec = out[out.index(c6_hdr):out.index("Standalone tasks:")]
        self.assertIn("F7", chain6_sec)
        self.assertIn("🟢 ready · 🏁 FINAL", chain6_sec)

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
            ("F6", "🏁 FINAL · 🔥 COMBO"),
            ("F11", "🏁 FINAL"),
            ("F10", "🏁 FINAL"),
            ("F4", "🟢 ready: +1 · 🔓 unblocks: 1"),
            ("F8", "🟢 ready: +1 · 🔓 unblocks: 1"),
            ("B1", None),
            ("F7", "🏁 FINAL"),
        ]
        for idx, (tid, tag) in enumerate(expected_ready, start=1):
            row = ready_rows[f"{idx}."]
            self.assertIn(tid, row, msg=r_ready.stdout)
            if tag is not None:
                self.assertIn(tag, row, msg=r_ready.stdout)
        self.assertTrue(ready_rows["6."].endswith("Standalone next"), msg=ready_rows["6."])

        # 3. --status and --limit apply consistently starting from top-ranked finale Chain 1:
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

        r_st_lim = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--status", "NEW", "--limit", "1"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        self.assertNotIn("Chain finales:", r_st_lim.stdout)
        self.assertIn("50% · 1/2 · Chain 1 -> F7: Plan after done:", r_st_lim.stdout)
        self.assertIn("F7", r_st_lim.stdout)
        self.assertIn("🟢 ready · 🏁 FINAL", r_st_lim.stdout)
        self.assertNotIn("F6", r_st_lim.stdout)

        # 5. Workspace -w formats cross-project finale as a Chain header with done stats
        r_ws = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "-w"],
            cwd=str(ws),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        self.assertIn("75% · 3/4 · Chain 3 -> proj_b:F1: Cross finale:", r_ws.stdout)
        self.assertIn("🟢 ready · 🏁 FINAL · 🔥 COMBO", r_ws.stdout)

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
            [str(SCRIPT), "add", "F", "Local done step"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(proj_a), check=True)
        arch_path = proj_a / "TODO_ARCHIVE.md"
        arch_txt = arch_path.read_text(encoding="utf-8").rstrip() + "\n\n- Depends on: proj_b:F1, proj_b:F2, F99\n"
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

        # Chain F (design chain: D1 [NEW] -> D2 [NEW]): 0 bugs, NEW status tier
        self._run([str(SCRIPT), "add", "D", "Design chain root"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "D", "Design chain leaf", "--depends", "D1"],
            cwd=str(proj_a),
            check=True,
        )

        # Standalone tasks to verify bug-first and status-tier ordering:
        # - D3: NEW
        # - F10: NEW
        # - F11: NEXT
        # - B4: NEXT (bug task B* must rank above other tasks!)
        self._run([str(SCRIPT), "add", "D", "Standalone design new"], cwd=str(proj_a), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Standalone feature new"],
            cwd=str(proj_a),
            check=True,
        )
        self._run([str(SCRIPT), "add", "F", "Standalone feature next", "--next"], cwd=str(proj_a), check=True)
        self._run([str(SCRIPT), "add", "B", "Standalone bug next", "--next"], cwd=str(proj_a), check=True)

        r_chain = self._run(
            [str(SCRIPT), "chain", "--numbered=right"],
            cwd=str(proj_a),
            env={**os.environ, "COLUMNS": "160"},
            check=True,
        )
        out = r_chain.stdout

        # Verify numbered RPG progress headers and transitive DONE count (excluding CANCELED/MISSING)
        h1 = "0% · 0/2 · Chain 1 -> F4: After ready bug:"
        h2 = "0% · 0/2 · Chain 2 -> B2: Blocked bug dist 1:"
        h3 = "0% · 0/3 · Chain 3 -> B3: Blocked bug dist 2:"
        h4 = "60% · 3/5 · Chain 4 -> F3: Progress chain open 2:"
        h5 = "0% · 0/2 · Chain 5 -> D2: Design chain leaf:"
        h6 = "0% · 0/2 · Chain 6 -> F9: Plan chain leaf:"
        for h in (h1, h2, h3, h4, h5, h6):
            self.assertIn(h, out, msg=out)

        # Verify chain ranking order:
        # Chain 1 (B1 -> F4, ready bug) -> Chain 2 (F5 -> B2, bug dist 1)
        # -> Chain 3 (F6 -> F7 -> B3, bug dist 2) -> Chain 4 (F2 -> F3, NEXT, 5 total tasks)
        # -> Chain 5 (D1 -> D2, NEW) -> Chain 6 (F8 -> F9, NEW)
        self.assertLess(out.index("1 B1"), out.index("3 F5"), msg=out)
        self.assertLess(out.index("3 F5"), out.index("5 F6"), msg=out)
        self.assertLess(out.index("5 F6"), out.index("8 F2"), msg=out)
        self.assertLess(out.index("8 F2"), out.index("10 D1"), msg=out)
        self.assertLess(out.index("10 D1"), out.index("12 F8"), msg=out)

        # Verify Standalone tasks ordering: B4 (bug, NEXT) -> F11 (NEXT) -> D3 (NEW) -> F10 (NEW)
        solo_sec = out[out.index("Standalone tasks:"):]
        self.assertLess(solo_sec.index("B4"), solo_sec.index("F11"), msg=solo_sec)
        self.assertLess(solo_sec.index("F11"), solo_sec.index("D3"), msg=solo_sec)
        self.assertLess(solo_sec.index("D3"), solo_sec.index("F10"), msg=solo_sec)

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
        self.assertIn("33% · 1/3 · Chain 1 -> F12: Followup after B2:", r_after.stdout)
        self.assertLess(r_after.stdout.index("1 B2"), r_after.stdout.index("3 B1"), msg=r_after.stdout)

        # Verify role-weighted velocity & effort ranking between chains with identical role_ease and status:
        # Compare two work-only NEW chains with 1 done prerequisite (proj_b:D1):
        # - Fast 2-open work chain (F13 -> F14, remaining_effort = 2, velocity = 1/3)
        # - Long 3-open work chain (F15 -> F16 -> F17, remaining_effort = 3, velocity = 1/4)
        # Fast 2-open work chain has higher weighted velocity (1/3 > 1/4) and lower effort (2 < 3), so it ranks before the 3-open chain!
        (proj_a / ".todo_projects.local").write_text("proj_a\nproj_b\n", encoding="utf-8")
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
        (proj_a / ".todo_projects.local").unlink()
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
        self.assertIn("🔒 blocked by: D1, F1 · 🔓 unblocks: 2", out_orch)
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
        self.assertIn("50% · 1/2 · Chain 1 -> F3: Run block finale task:", out_direct)
        self.assertIn("F3", out_direct)
        self.assertIn("🟢 ready · 🏁 FINAL · 🔥 COMBO", out_direct)
        self.assertNotIn("todo_md:F3", out_direct)
        self.assertIn("0% · 0/5 · Chain 2 -> todo_flow:F2: Flow release milestone:", out_direct)
        self.assertIn("todo_flow:D1", out_direct)
        self.assertIn("todo_flow:F1", out_direct)
        self.assertIn("F1", out_direct)
        self.assertNotIn("run_block:F1", out_direct)
        self.assertIn("🔒 blocked by: todo_flow:D1, todo_flow:F1 · 🔓 unblocks: 2", out_direct)
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

        # 4. Running `todo_md -p run_block chain` (and `-C ../run_block` or `-C run_block`) from outside `run_block`
        # keeps the `run_block:` prefix on run_block tasks so IDs are ready for copy-paste in cwd
        for from_cwd, target_flag in ((ws, ["-C", "run_block"]), (todo_flow, ["-p", "run_block"]), (todo_flow, ["-C", "../run_block"])):
            with self.subTest(from_cwd=from_cwd.name, target_flag=target_flag):
                r_ext = self._run(
                    [str(SCRIPT), *target_flag, "chain"],
                    cwd=str(from_cwd),
                    env=base_env,
                    check=True,
                )
                out_ext = r_ext.stdout
                self.assertIn("run_block:F3", out_ext)
                self.assertIn("run_block:F1", out_ext)
                self.assertIn("🔒 blocked by: todo_flow:D1, todo_flow:F1 · 🔓 unblocks: 2", out_ext)
                self.assertIn("run_block:F2", out_ext)
                self.assertIn("run_block:D2 (HOLD) -> run_block:F4 (NEXT)", out_ext)
                self.assertNotIn("Flow internal step", out_ext)
                self.assertNotIn("Todo md standalone task", out_ext)

        # 5. Project-scoped `--ready` filters to target project tasks while preserving orchestrator blockers
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
        self.assertIn("🔒 blocked by: todo_flow:D1, todo_flow:F1 · 🔓 unblocks: 2", r_local_cfg.stdout)

        (todo_flow / ".todo_projects.local").unlink()
        env_projects = {**base_env, "TODO_MD_PROJECTS": "todo_flow,run_block,todo_md"}
        r_env_orch = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(todo_flow), env=env_projects, check=True)
        self.assertIn("run_block:F1", r_env_orch.stdout)
        self.assertNotIn("unlisted_proj", r_env_orch.stdout)
        r_env_child = self._run([str(SCRIPT), "chain", "--numbered=right"], cwd=str(run_block), env=env_projects, check=True)
        self.assertIn("🔒 blocked by: todo_flow:D1, todo_flow:F1 · 🔓 unblocks: 2", r_env_child.stdout)
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

        (run_block / ".todo_projects.local").write_text("todo_flow\nrun_block\n", encoding="utf-8")
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
        (run_block / ".todo_projects.local").unlink()

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
        self.assertIn("33% · 1/3 · Chain 1 -> F4: Goal B closing root:", out_def)
        self.assertIn("25% · 1/4 · Chain 2 -> F3: Goal A closing root:", out_def)
        self.assertIn("0% · 0/3 · Chain 3 -> F7: Competing next root:", out_def)
        self.assertIn("🔗 also in: F3", out_def)
        self.assertIn("🔗 also in: F4", out_def)
        self.assertNotIn("todo_flow:D1", out_def)

        # Verify CLI output with --all (plain text and ANSI color with target highlighting):
        r_all_plain = self._run([str(SCRIPT), "chain", "--numbered=right", "--all"], cwd=str(run_block), env=base_env, check=True)
        out_all_plain = r_all_plain.stdout
        self.assertIn("todo_flow:D1", out_all_plain)
        self.assertIn("✅ DONE", out_all_plain)
        self.assertRegex(out_all_plain, r"todo_flow:D1\s+✅ DONE\s+Shared architecture spec.*🔗 also in: F3")
        self.assertRegex(out_all_plain, r"todo_flow:D1\s+✅ DONE\s+Shared architecture spec.*🔗 also in: F4")
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
                ln.startswith("\033[1;3;93m") and "todo_flow:D1" in ln and "✅ DONE" in ln
                for ln in r_all_hl_ext.stdout.splitlines()
            ),
            msg=r_all_hl_ext.stdout,
        )

        # 2. Verify monotonic Quest Momentum across `todo_md status ... WIP` and `todo_md done ...`:
        # Switch F2 in Goal A (F3 chain) to WIP -> F3 chain becomes active quest (tier 0) and ranks #1!
        (run_block / ".todo_projects.local").write_text("todo_flow\nrun_block\n", encoding="utf-8")
        self._run([str(SCRIPT), "status", "F2", "WIP"], cwd=str(run_block), check=True)
        (run_block / ".todo_projects.local").unlink()
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
        (run_block / ".todo_projects.local").write_text("todo_flow\nrun_block\n", encoding="utf-8")
        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(run_block), check=True)
        (run_block / ".todo_projects.local").unlink()
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
            any(ln.startswith("\033[2;90m") and " F1 " in ln and "✅ DONE" in ln for ln in r_all_local_done.stdout.splitlines()),
            msg=r_all_local_done.stdout,
        )
        r_all_hl_local_done = self._run(
            [str(SCRIPT), "chain", "--numbered=right", "--all", "F1"],
            cwd=str(run_block),
            env=color_env,
            check=True,
        )
        self.assertTrue(
            any(ln.startswith("\033[1;93m") and " F1 " in ln and "✅ DONE" in ln for ln in r_all_hl_local_done.stdout.splitlines()),
            msg=r_all_hl_local_done.stdout,
        )

    def test_nested_milestone_subchains_tree_connectors_and_multiline_wrapped_bars(self):
        mod = self.todo_md_mod

        # 1. Direct unit test for _wrap_table_row() with cont_prefix preserving vertical bars
        prefix = "  │   ├─ 1. F1            🎯 [NEXT]       "
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
        (run_block / ".todo_projects.local").write_text("todo_flow\nrun_block\n", encoding="utf-8")
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
        (run_block / ".todo_projects.local").unlink()

        # 3. Default `todo_md chain` (without --all) renders nested Sub-chain headers, ├── / │   / └─► connectors
        r_wide = self._run([str(SCRIPT), "chain", "--tree", "--numbered=right"], cwd=str(run_block), env=wide_env, check=True)
        out_wide = r_wide.stdout
        self.assertIn(
            "14% · 1/7 · Chain 1 -> F4: Closing root questline goal delivering nested milestone sub-chains and wrapped tree rows:",
            out_wide,
        )
        # Outer Sub-chain -> F2 (1 done + 4 open = 5 tasks -> 20% | 1/5)
        self.assertIn(
            "  ├── 20% · 1/5 · Sub-chain -> F2: Local intermediate milestone integrating external aggregator and local engine prerequisite:",
            out_wide,
        )
        # Inner Sub-chain -> todo_flow:F2 (1 done + 2 open = 3 tasks -> 33% | 1/3)
        self.assertIn(
            "  │   ├── 33% · 1/3 · Sub-chain -> todo_flow:F2: External milestone aggregator combining completed foundation and open parser prerequisite:",
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
            "  │   │   ├── 50% · 1/2 · Sub-chain -> todo_flow:F1: External parser prerequisite with a comprehensive multi-line wrapped description for sub-chain testing:",
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
        self.assertTrue(color_lines[sub_f2_idx].startswith("\033[1;93m  ├── 20% · 1/5 · Sub-chain -> F2:"), msg=color_lines[sub_f2_idx])
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

        # Parallel branches in flat chain vs --tree dynamic subtree re-ranking:
        # Shared high-priority NEXT task F1 feeds:
        # - Branch A: F1 (NEXT, ready) -> F2 (NEW, plan tail)
        # - Branch B: F1 (NEXT, ready) -> F3 (NEW, plan) -> F4 (NEW, plan tail)
        # - Branch C: F5 (NEXT, ready) -> F6 (NEXT, blocked) -> F7 (NEW, plan tail)
        # Closing root F8 (NEW) depends on F2, F4, F7.
        branch_proj = self.tmp / "branch_rank"
        branch_proj.mkdir()
        self._run([str(SCRIPT), "-C", str(branch_proj), "init"], check=True)
        self._run([str(SCRIPT), "add", "Shared ready next", "--next"], cwd=str(branch_proj), check=True)  # F1
        self._run([str(SCRIPT), "add", "Branch A new tail", "--depends", "F1"], cwd=str(branch_proj), check=True)  # F2
        self._run([str(SCRIPT), "add", "Branch B new mid", "--depends", "F1"], cwd=str(branch_proj), check=True)  # F3
        self._run([str(SCRIPT), "add", "Branch B new tail", "--depends", "F3"], cwd=str(branch_proj), check=True)  # F4
        self._run([str(SCRIPT), "add", "Branch C ready next", "--next"], cwd=str(branch_proj), check=True)  # F5
        self._run([str(SCRIPT), "add", "Branch C blocked next", "--next", "--depends", "F5"], cwd=str(branch_proj), check=True)  # F6
        self._run([str(SCRIPT), "add", "Branch C new tail", "--depends", "F6"], cwd=str(branch_proj), check=True)  # F7
        self._run([str(SCRIPT), "add", "Closing root", "--depends", "F2, F4, F7"], cwd=str(branch_proj), check=True)  # F8

        # In flat mode, ready NEXT tasks (F1, F5) rank at the very top ahead of blocked NEXT task (F6),
        # and all NEXT tasks precede NEW tasks (F2, F3, F4, F7, F8) so Branch A's NEW tail F2 never pushes F5/F6 down!
        out_branch_flat = self._run([str(SCRIPT), "chain"], cwd=str(branch_proj), check=True).stdout
        flat_refs = re.findall(r"^  (F\d+) ", out_branch_flat, re.M)
        self.assertEqual(flat_refs[:3], ["F1", "F5", "F6"], msg=out_branch_flat)
        self.assertEqual(set(flat_refs[3:-1]), {"F2", "F3", "F4", "F7"}, msg=out_branch_flat)
        self.assertEqual(flat_refs[-1], "F8", msg=out_branch_flat)

        # In --tree mode, after Sub-chain -> F4 emits F1, F3, F4, dynamic re-ranking recomputes min_pos
        # over unemitted nodes so Sub-chain -> F7 (with unemitted NEXT tasks F5, F6) ranks ahead of
        # Branch A's F2 (whose only NEXT ancestor F1 was already emitted in Sub-chain -> F4)!
        out_branch_tree = self._run([str(SCRIPT), "chain", "--tree"], cwd=str(branch_proj), check=True).stdout
        top_sub_order = re.findall(r"^  [├└]── \d+% · \d+/\d+ · Sub-chain -> (F\d+):", out_branch_tree, re.M)
        self.assertEqual(top_sub_order, ["F4", "F7"], msg=out_branch_tree)
        self.assertEqual(
            self._row_refs(out_branch_tree),
            ["F1", "F3", "F4", "F5", "F6", "F7", "F2", "F8"],
            msg=out_branch_tree,
        )

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
        self.assertIn("✅ DONE", r_all_s_done.stdout)
        self.assertNotIn("run_block:F2", r_all_s_done.stdout)

        r_all_f_canc = self._run(
            [str(SCRIPT), "--all", "-f", "run_block:F2"], cwd=str(todo_flow), check=True
        )
        self.assertIn("run_block:F2", r_all_f_canc.stdout)
        self.assertIn("❌ CANCELED", r_all_f_canc.stdout)
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
                m.group(2): m.group(1)
                for m in re.finditer(r"(\d+% · \d+/\d+) · Sub-chain -> (\S+): .*?:$", out, re.M)
            }

        out = self._run([str(SCRIPT), "chain", "--tree"], cwd=str(proj), env=env, check=True).stdout
        h = headers(out)
        self.assertEqual(h["F2"], "33% · 1/3", msg=out)
        self.assertEqual(sorted([h["F5"], h["F6"]]), ["0% · 0/2", "20% · 1/5"], msg=out)
        self.assertNotIn("F1", h, msg=out)

        out_all = self._run([str(SCRIPT), "chain", "--tree", "--all"], cwd=str(proj), env=env, check=True).stdout
        h_all = headers(out_all)
        self.assertEqual(h_all["F1"], "50% · 1/2", msg=out_all)
        self.assertEqual(h_all["F2"], "33% · 1/3", msg=out_all)
        self.assertEqual(
            sorted([h_all["F5"], h_all["F6"]]), ["0% · 0/2", "20% · 1/5"], msg=out_all
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
        (todo_md_p / "TODO.md").write_text(
            "# 🎯 [NEXT] F1: Leaf consumer\n\n- Depends on: chrome/canary:F1\n",
            encoding="utf-8",
        )
        for cwd in (todo_md_p, todo_flow, meta_orch):
            with self.subTest(cwd=cwd.name):
                r = self._run([str(SCRIPT), "chain"], cwd=str(cwd), env=env, check=True)
                flat = self._flat_text(r.stdout)
                self.assertIn("chrome/canary:F1", flat, msg=r.stdout)
                self.assertIn("Canary base", flat, msg=r.stdout)
        r_c = self._run(
            [str(SCRIPT), "-p", "chrome/canary", "show", "F1"],
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

    def test_chain_all_tree_collapses_repeated_done_subtrees_unless_targeted(self):
        proj = self.tmp / "collapse_done_tree"
        proj.mkdir()
        self._run([str(SCRIPT), "-C", str(proj), "init"], check=True)
        # Build a completed DONE sub-chain: F1 -> F2 (both DONE)
        self._run([str(SCRIPT), "add", "F", "Foundation step alpha", "--next"], cwd=str(proj), check=True)
        self._run(
            [str(SCRIPT), "add", "F", "Foundation milestone beta", "--next", "--depends", "F1"],
            cwd=str(proj),
            check=True,
        )
        self._run([str(SCRIPT), "done", "F1", "F2", "-m", "completed foundation"], cwd=str(proj), check=True)
        # Two independent open chains (F3 -> F4 and F5 -> F6) that both depend on DONE milestone F2
        self._run(
            [str(SCRIPT), "add", "F", "Chain one stage", "--next", "--depends", "F2"],
            cwd=str(proj),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Chain one root", "--next", "--depends", "F3"],
            cwd=str(proj),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Chain two stage", "--depends", "F2"],
            cwd=str(proj),
            check=True,
        )
        self._run(
            [str(SCRIPT), "add", "F", "Chain two root", "--depends", "F5"],
            cwd=str(proj),
            check=True,
        )

        # Without target <ID>, Chain 1 expands the [100% | 2/2] F2 sub-chain once,
        # and Chain 2 collapses the repeated F2 sub-chain header without re-emitting F1/F2 rows.
        r_all_tree = self._run(
            [str(SCRIPT), "chain", "--all", "--tree", "--numbered"],
            cwd=str(proj),
            check=True,
        )
        out = r_all_tree.stdout
        c1_pos = out.index("Chain 1 -> F4:")
        c2_pos = out.index("Chain 2 -> F6:")
        c1_part = out[c1_pos:c2_pos]
        c2_part = out[c2_pos:]
        self.assertIn("100% · 2/2 · Sub-chain -> F2: Foundation milestone beta", c1_part)
        self.assertIn("Foundation step alpha", c1_part)
        self.assertIn("100% · 2/2 · Sub-chain -> F2: Foundation milestone beta", c2_part)
        self.assertIn("see above", c2_part)
        self.assertNotIn("Foundation step alpha", c2_part)
        # Row numbers stay contiguous (4 rows in Chain 1: F1, F2, F3, F4; 2 rows in Chain 2: F5, F6)
        rows = self._table_rows(out)
        self.assertEqual([k for k in rows if k.endswith(".")], ["1.", "2.", "3.", "4.", "5.", "6."], msg=out)

        # When a task inside the DONE sub-chain is explicitly targeted (e.g. chain F1 F6 --all --tree),
        # the sub-chain is expanded in both chains.
        r_targeted = self._run(
            [str(SCRIPT), "chain", "F1", "F6", "--all", "--tree"],
            cwd=str(proj),
            check=True,
        )
        t_out = r_targeted.stdout
        tc2_part = t_out[t_out.index("Chain 2 -> F6:"):]
        self.assertIn("Foundation step alpha", tc2_part)
        self.assertNotIn("see above", tc2_part)



    def test_overall_progress_header_breakdown_omissions_and_d5_ansi_palette(self):
        proj = self.tmp / "progress_hdr_proj"
        proj.mkdir()
        self._run([str(SCRIPT), "-C", str(proj), "init"], check=True)

        # Complete 2 DONE tasks (D1, F1) and cancel 1 task (F2)
        self._run([str(SCRIPT), "add", "D", "Completed design"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "done", "D1", "-m", "done"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "F", "Completed feature"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "done", "F1", "-m", "done"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "F", "Canceled feature"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "cancel", "F2", "-m", "dropped"], cwd=str(proj), check=True)

        # Open tasks: F3 (WIP, ready), F4 (NEXT, ready), F5 (NEW, blocked by F4), F6 (HOLD)
        self._run([str(SCRIPT), "add", "F", "Active wip", "--status", "WIP", "--depends", "F1"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "F", "Ready next", "--next"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "F", "Blocked new", "--depends", "F4"], cwd=str(proj), check=True)
        self._run([str(SCRIPT), "add", "F", "Paused hold", "--status", "HOLD"], cwd=str(proj), check=True)

        r_chain = self._run([str(SCRIPT), "chain"], cwd=str(proj), check=True)
        lines = r_chain.stdout.splitlines()
        # 2 done + 3 open (excluding CANCELED F2 and HOLD F6) = 5 total -> 40%
        self.assertEqual(
            lines[0],
            "40% · ✅ 2/5 · 3 open: 🟢 2 ready (1 🔵 WIP, 1 🎯 NEXT) · ⏳ 1 blocked · ⏸️ 1 held",
            msg=r_chain.stdout,
        )
        self.assertEqual(lines[1], "", msg=r_chain.stdout)

        # With --include-hold: F6 enters open and ready, held is 0 and omitted (2 done + 4 open = 6 -> 33%)
        r_hold = self._run([str(SCRIPT), "chain", "--include-hold"], cwd=str(proj), check=True)
        hold_lines = r_hold.stdout.splitlines()
        self.assertEqual(
            hold_lines[0],
            "33% · ✅ 2/6 · 4 open: 🟢 3 ready (1 🔵 WIP, 1 🎯 NEXT, 1 ⏸️ HOLD) · ⏳ 1 blocked",
            msg=r_hold.stdout,
        )
        self.assertNotIn("held", hold_lines[0])

        # With --prefix D: 1 done (D1), 0 open -> 100%, omit parenthesized breakdown, blocked, and held
        r_pref_d = self._run([str(SCRIPT), "chain", "--prefix", "D"], cwd=str(proj), check=True)
        d_lines = r_pref_d.stdout.splitlines()
        self.assertEqual(
            d_lines[0],
            "100% · ✅ 1/1 · 0 open: 🟢 0 ready",
            msg=r_pref_d.stdout,
        )
        self.assertEqual(d_lines[1], "", msg=r_pref_d.stdout)

        # Verify D5 ANSI palette in TTY mode (FORCE_COLOR=1) preserves exact display layout
        base_env = {k: v for k, v in os.environ.items() if k not in ("NO_COLOR", "FORCE_COLOR", "TODO_MD_PROJECTS")}
        color_env = {**base_env, "FORCE_COLOR": "1", "COLUMNS": "120"}
        plain_env = {**base_env, "COLUMNS": "120"}
        r_color = self._run([str(SCRIPT), "chain"], cwd=str(proj), env=color_env, check=True)
        r_plain = self._run([str(SCRIPT), "chain"], cwd=str(proj), env=plain_env, check=True)
        self.assertEqual(self.todo_md_mod._strip_ansi(r_color.stdout), r_plain.stdout)
        c_lines = r_color.stdout.splitlines()
        self.assertIn("\033[1;36m40%\033[0m", c_lines[0])
        self.assertIn("\033[32m✅ 2/5\033[0m", c_lines[0])
        self.assertIn("\033[1;35m🏁 FINAL\033[0m", r_color.stdout)
        self.assertIn("\033[1;91m🔥 COMBO\033[0m", r_color.stdout)


if __name__ == "__main__":
    unittest.main()
