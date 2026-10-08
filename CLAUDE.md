# Claude Code Instructions

## Development Workflow

When the user requests implementation work, feature development, or bug fixes:

- Use `$development SPEC` (skill: `.claude/skills/development/SKILL.md`, command: `.claude/commands/development.md`) for structured test-driven development (TDD), optional spec-driven development (SDD, via `/sdd`), and parallel agent coordination.
- Codex counterpart: `skills/development/` (also exposed at `.agents/skills/development`); keep it in sync with the Claude skill.
- Treat `.codex/instructions.md` as the source of truth for repository conventions and quality standards.
- Follow the skill's plan-clarify-implement-commit workflow. TDD records go under `docs/fixes/<branch-name>/<task-name>/`.
- Never commit to `main`; work on `develop` or a feature/fix branch.

## Code Understanding

- Use the tokensave MCP tools (`tokensave_context`, `tokensave_search`, `tokensave_callers`, `tokensave_impact`) before broad file scans or manual exploration.
- Graphify (`/graphify`) is an optional complement for regenerable graph reports; fall back to targeted file reads only when neither can answer the question.
- MCP servers for LLM-assisted development are listed in `mcp/mcp.json`.

## Available Skills and Commands

- `$development` / `/development`: structured TDD workflow, optional SDD, parallel agent coordination (pass a specification or feature request).
- `/graphify`: build, refresh, query, or explain the Graphify knowledge graph (optional; needs the `graphify` CLI).
- `/perseus`: EXPERIMENTAL opt-in local-first cross-session agent memory (needs `perseus-vault`).
