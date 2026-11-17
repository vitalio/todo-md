# 🎯 [NEXT] F30: Emit Title header in todo_md show preamble for downstream bundle and TUI display

- Emit `Title: <base_title>` in `cmd_show` (`src/commands.py`) immediately after `Task: <ID>`, stripping any trailing `— *note*` via `_strip_heading_note` so `Task:` stays the bare ID while `Title:` carries the clean task summary.
- Sync `src/header.py` (`--help`), `src/rules/todo_md.md`, `README.md`, and `tests/test_todo_md.py`, and rebuild `todo_md` via `python3 build.py`.

# 🎯 [NEXT] D2: Design standalone task file mode (-f / --file) for shortlists and ad-hoc task files

- Role: design
- Explore and specify `-f <path>` / `--file <path>` support across `todo_md` subcommands (`overview`, `list`, `show`, `next-id`, `queue`, `files`, `check`, `add`, `edit`, `append`, `status`, `next`) so `todo_md` can inspect and manipulate any Markdown task file (such as a temporary shortlist generated during planning or dispatch) outside a repository's `TODO.md`.
- Define behavior when `TODO_ARCHIVE.md` is absent beside the target file: allow read/check and in-file status mutations without requiring an archive file, and specify explicit error or `--archive <path>` handling for `done` / `cancel` / `archive`.
- Define interaction and precedence with `-C <dir|project>` (`F20`), `TODO_MD_CWD`, positional `.md` paths, and cross-project `<project>:<ID>` dependency lookups via `TODO_MD_WORKSPACE` when inspecting a shortlist in `/tmp` or another directory.
- Target files for downstream implementation: `src/cli.py`, `src/parser.py`, `src/commands.py`, `src/header.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# 🎯 [NEXT] F25: Detect stale completion date notes on active tasks in todo_md check

- Extend `validate_all` in `src/parser.py` so `todo_md check` (and automatic post-mutation validation) reports an error when an active task in `TODO.md` retains a completion date stamp (`— *YYYY-MM-DD...*`) in its heading, instructing the user to move it back to `TODO_ARCHIVE.md` or clear the stale note.
- Target files: `src/parser.py`, `src/rules/todo_md.md`, `README.md`, `tests/test_todo_md.py`.

# ⚪ [NEW] P1: JSON output mode (`--json`)

Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F3: Clarify repository scope rule in .bundle to target the owning repository

- Update the repository scope instruction in .bundle and todo_md.md (and synced documentation if applicable) to state explicitly that each task must be recorded in the TODO.md of the repository it belongs to (targeting that project via <project>:<ID> or running todo_md in that target project), never in an unrelated project's backlog.
- Document task dependencies using 'Depends on: <ID>' (same project) or 'Depends on: <project>:<ID>' (cross-project, e.g. agents_bundle:F5 or chrome/canary:F1) in the task body.

# ⚪ [NEW] F6: Move exported rules and bundles from src/ to agents/

- Depends on: agents_bundle:F7, agents_bundle:F15
- Move `src/rules/todo_md.md` and `src/bundles/todo_md.bundle` to `agents/` using the unified logical bundle/rule layout once `agents_bundle` supports it.
- Update `AGENTS.md`, `README.md`, and tests to reference the new paths under `agents/`.

# ⚪ [NEW] F14: Clarify in todo_md rule that backlog-only commits in plan/design/audit run in the same block without a separate diff-review turn

- Update the `Validation & commits` section in `src/rules/todo_md.md` to explicitly state that in `role=plan`, `role=design`, and `role=audit`, `todo_md` mutations can be batched and committed in the same execution block (via `-c` on the final `todo_md` command or `git add TODO*.md && git commit`) without waiting for a separate diff-review turn.
- Rebuild and reinstall `todo_md` (and keep any synced docs/tests in `tests/` green) so exported rules reflect the updated wording.

# ⚪ [NEW] F16: Migrate workflow bundle and docs from role=execute and role=audit to role=work and role=review

- Depends on: agents-rules:F9, agents-rules:F16
- Update `src/bundles/todo_md.bundle`, `src/rules/todo_md.md`, `README.md`, and unit tests in `tests/test_todo_md.py` to use `role=work` and `role=review` instead of `role=execute` and `role=audit` (preserving legacy aliases only if needed during transition).
- Rebuild and reinstall `todo_md` and release a PATCH version.

# ⚪ [NEW] F17: Document task prefix conventions (F, B, D) and design-task lifecycle in todo_md rule and bundle

- Document standard task ID prefixes in `src/rules/todo_md.md`: `F` (feature / default), `B` (bugfix / defect), and `D` (design / architectural exploration / raw idea routed to `role=design` before decomposition into `F` tasks).
- Update `src/bundles/todo_md.bundle` (`[if role=design]`) so design tasks (`D*`) are closed via `todo_md done <ID>` once architectural invariants are persisted in `AGENTS.md` and follow-up `F*` implementation tasks are created.
- Rebuild and reinstall `todo_md`, keep `README.md` and `tests/test_todo_md.py` in sync, and release a PATCH version.
