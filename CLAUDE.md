# CLAUDE.md

## Skills

Project skills from [mattpocock/skills](https://github.com/mattpocock/skills) (aihero.dev/skills) live in `.claude/skills/`. All of them are model-invocable: use them proactively whenever a task matches a skill's description, without waiting to be asked. For example:

- Planning a feature or design → `grilling` / `grill-with-docs`, then `to-spec` and `to-tickets`
- Building features or fixing bugs → `tdd`; hard bugs or regressions → `diagnosing-bugs`
- Building from a spec or tickets → `implement` / `implement-spec`
- Before committing a change → `code-review`; writing a PR body → `pr`
- Design questions → `prototype`, `codebase-design`, `domain-modeling`
- Ending a long session → `handoff`; after a session → `retro`

Run `/setup-matt-pocock-skills` once to configure the issue tracker, triage labels and docs location.
