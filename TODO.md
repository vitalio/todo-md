# ⚪ [NEW] P1: JSON output mode (`--json`)

Allow exporting parsed tasks as JSON for scripting.

# ⚪ [NEW] F3: Clarify repository scope rule in .bundle to target the owning repository

- Update the repository scope instruction in .bundle (and synced documentation if applicable) to state explicitly that each task must be recorded in the TODO.md of the repository it belongs to (running todo_md in that target repository), never in an unrelated repository's backlog.

# ⚪ [NEW] F4: Support todo_md last, task=<ID>|last in role=audit bundle, and direct execution prompt

- Add todo_md last (and todo_md show last) to display the most recently archived task at the top of TODO_ARCHIVE.md, and keep src/header.py, src/rules/todo_md.md, and README.md in sync.
- Update src/bundles/todo_md.bundle under [if role=execute] to remove 'state a brief implementation plan' and instruct the agent to proceed directly from batched file inspection to the edit, test, and diff step.
- Update src/bundles/todo_md.bundle under [if role=audit] to handle [if task!=] by running '$ todo_md {task:}' (supporting both task=<ID> and task=last) and emitting a targeted task audit prompt.
