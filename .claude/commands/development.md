# $development

Structured development workflow: test-driven development (TDD), optional spec-driven development (SDD), and parallel agent coordination.

## Runtime

- Target: Claude Code
- Invocation: `$development SPEC [/sdd|/spec-driven] [/branch BRANCH-NAME] [/followup TASK-NAME|PATH]`
- Workspace assumption: repository-local command with shell and file access

## Instructions

Load and follow `.claude/skills/development/SKILL.md` exactly, after reading `.codex/instructions.md`. The request to implement is:

$ARGUMENTS
