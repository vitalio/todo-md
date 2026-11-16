# `todo_md` — Project-Specific Agent Rules

Universal workflow, language, Git, SemVer, Python CLI, and single-file build
rules are loaded via `.agents_bundle`.

## Architecture & Module Boundaries

- `src/header.py` — CLI usage docstring (`-h`/`--help`), standard library
  imports, version placeholder (`__VERSION__`, injected from `VERSION` by
  `build.py`), and task heading regexes.
- `src/parser.py` — `TODO.md` and `TODO_ARCHIVE.md` task parser, ID sequence
  tracking, and structural validator (`todo_md check`).
- `src/commands.py` — task lifecycle subcommands (`init`, `add`, `edit`,
  `append`, `status`, `next`, `done`, `cancel`, `list`, `archive`, `ids`,
  `check`). Keep `src/rules/todo_md.md`, `-h`/`--help`, and `README.md` in sync
  in the same commit whenever commands or flags change.
- `src/rules/todo_md.md` & `src/bundles/todo_md.bundle` — agent instructions
  and role/task workflow prompts for `bundle vitalio/todo_md`.
- `src/cli.py` — CLI argument routing and self-update (`update`,
  `check-update`).

## Dependency Graph & Sequencing Contract

- Single source of truth: express both prerequisites and execution order in
  `- Depends on:` lines (and `--depends`); do not duplicate order in a
  separate `- Order:` field.
- Syntax: `,` separates parallel items within a stage, `->` separates sequential
  stages (`,` binds tighter than `->`, e.g. `A, B -> C`), and multiple
  `- Depends on:` lines represent independent branches combined with AND.
- Unified DAG: dependency resolution merges explicit `->` stage edges on the
  target task with transitive `- Depends on:` edges inside referenced tasks
  (preserving one-way cross-repo boundaries when orchestrators sequence child
  tasks).
- Validation & execution: `todo_md check` detects syntax errors, missing refs,
  and transitive cycles; `DONE` unblocks while `CANCELED` or `MISSING` blocks;
  `todo_md queue <ID>` shows the ordered queue and `todo_md next-id <ID>`
  prints the first unblocked task ID for pipe composition.
