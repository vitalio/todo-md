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
