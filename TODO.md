# 🎯 [NEXT] F9: Always expand at least one task in default todo_md overview

- Update `cmd_summary` in `src/parser.py` so that when `full=False` and `TODO.md` has no `WIP`, `NEXT`, or `QUESTION` tasks (only `NEW` and/or `HOLD`), the first ordered task is rendered in full while subsequent `NEW`/`HOLD` tasks remain compacted.
- Keep `todo_md [--full]` documentation in sync across `src/header.py`, `src/rules/todo_md.md`, and `README.md`.
- Add unit tests in `tests/test_todo_md.py` verifying that default `todo_md` expands the first `NEW`/`HOLD` task when no higher-priority tasks exist and keeps all `NEW`/`HOLD` tasks compact when at least one `WIP`/`NEXT`/`QUESTION` task is shown in full.

# ⚪ [NEW] P1: JSON output mode (`--json`)

Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F3: Clarify repository scope rule in .bundle to target the owning repository

- Update the repository scope instruction in .bundle and todo_md.md (and synced documentation if applicable) to state explicitly that each task must be recorded in the TODO.md of the repository it belongs to (targeting that project via <project>:<ID> or running todo_md in that target project), never in an unrelated project's backlog.
- Document task dependencies using 'Depends on: <ID>' (same project) or 'Depends on: <project>:<ID>' (cross-project, e.g. agents_bundle:F5 or chrome/canary:F1) in the task body.

# ⚪ [NEW] F6: Move exported rules and bundles from src/ to agents/

- Depends on: agents_bundle:F7
- Move src/rules/todo_md.md and src/bundles/todo_md.bundle to agents/ once agents_bundle supports the root agents/ directory.
- Update AGENTS.md, README.md, and tests to reference the new paths under agents/.

# ⚪ [NEW] F7: Cross-project workspace discovery, <project>:<ID> addressing, and Depends on support

- Detect a todo_md-managed project by the presence of both TODO.md and TODO_ARCHIVE.md (without climbing to git rev-parse --show-toplevel when invoked in a subproject or a workspace directory without TODO.md).
- When invoked in a directory without TODO.md + TODO_ARCHIVE.md (or when -w / --workspace is passed), scan subdirectories up to a bounded depth (e.g. 3 levels, skipping hidden directories '.*' and build/vendor directories) without stopping at intermediate projects so both root projects (e.g. chrome) and nested subprojects (e.g. chrome/canary) are discovered as separate project namespaces.
- Add 'todo_md projects' to list discovered workspace projects and their open task counts, and support '-w' / '--workspace' for cross-project task overviews and queries.
- Support universal '<project>:<ID>' and '<project>' addressing across CLI commands (e.g. 'todo_md agents_bundle:F5', 'todo_md chrome/canary:F1', 'todo_md add agents-rules ...') using POSIX '/' separators on all platforms (Linux, macOS, Windows), resolving '<project>' relative to the current workspace root (parent of the current repository root or TODO_MD_WORKSPACE).
- Support '--depends <ref>[,<ref>...]' on 'todo_md add' and 'todo_md edit' (storing '- Depends on: <ref>' in the task body), validate dependency targets in 'todo_md check', and surface dependency status ([DONE] vs blocked) in task output.
- Update todo_md.bundle to run 'todo_md -w' when 'workspace=1' is passed.
