# /perseus (Experimental)

Local-first persistent memory system for AI agents.

## Runtime

- Target: Claude Code
- Invocation: run or reference `/perseus` in Claude Code
- Workspace assumption: repository-local command with shell and file access
- Status: EXPERIMENTAL, opt-in, not part of default workflows

## Overview

EXPERIMENTAL. This skill documents a repo-native integration path for Perseus Vault (https://github.com/Perseus-Computing-LLC/perseus-vault), a local-first, encrypted, persistent memory system for AI agents: one Rust binary, one SQLite file, no cloud dependency. Perseus lets an agent write durable facts, decisions, and context (`perseus_vault_remember`, `perseus_vault_capture`) and later retrieve them (`perseus_vault_recall`) across otherwise stateless sessions.

Use this skill when the user wants Perseus Vault explained, wants it wired into this repository, or wants Perseus combined with `graphify` (or tokensave) so structural knowledge becomes durable, recallable learning instead of a fresh analysis every run.

Because this integration is experimental:

- it is opt-in and not part of the default workflow
- it does not run automatically from any other skill, hook, or wrapper in this repository
- it does not install, download, or execute the upstream installer on the user's behalf without the user explicitly running it themselves

## Install And Bootstrap

Perseus Vault is third-party, upstream tooling. This repository does not vendor it.

1. Install the official `perseus-vault` binary if it is not already available (the user runs this explicitly; do not run an installer script on the user's behalf without confirmation):
   ```bash
   curl -sSf https://raw.githubusercontent.com/Perseus-Computing-LLC/perseus-vault/main/scripts/install.sh | sh
   ```
2. Start the local memory server against a user-scoped database file (never a path inside this repository):
   ```bash
   perseus-vault serve --db ~/.perseus-vault/data/perseus-vault.db
   ```
3. Wire it as an MCP server for the assistant/client in use:
   ```bash
   perseus-vault install-client --hooks --rules
   ```

If `perseus-vault` is not installed or the MCP server is not reachable, fail soft: state that Perseus is unavailable and continue without it. Do not block any other workflow on Perseus being present.

## Workflow

Perseus exposes both a CLI and an MCP tool surface. Prefer the MCP tools when the assistant is already wired to the Perseus MCP server; fall back to the CLI otherwise.

Core MCP tools:

- `perseus_vault_remember`: write a durable fact/decision
- `perseus_vault_recall`: retrieve prior memories relevant to the current task
- `perseus_vault_capture`: capture a larger artifact or summary into memory

Core CLI verbs: `serve`, `stats`, `forget`, `prune`, `purge`, `decay`, `vault-export`, `vault-import`, `obsidian-sync`, `prepare`, `capture` (all as `perseus-vault <verb>`).

Before starting repeat work on a task, call `perseus_vault_recall` for relevant prior memories. After completing durable, reusable work, call `perseus_vault_remember` or `perseus_vault_capture` to persist it. Do not persist transient, task-local, or secret details.

## Combine With Graphify

Pair Perseus's durable memory with the repository's structural graph rather than treating either in isolation.

1. Build or refresh the repo graph first, per the `graphify` skill.
2. Read `graphify-out/GRAPH_REPORT.md` and `graphify-out/graph.json` for findings relevant to the current task.
3. Capture the durable, reusable subset (architecture decisions, ownership boundaries, call-flow findings, dependency-risk notes) into Perseus with `perseus_vault_capture`. Not the full raw graph.
4. In a later session, call `perseus_vault_recall` before re-running `graphify query` or `graphify explain`, so earlier findings inform the question.

`graphify-out/` stays the disposable, regenerable graph; Perseus is the durable cross-session memory layer on top of it.

## Non-Negotiables

- EXPERIMENTAL and opt-in; never invoked automatically by another skill.
- Do not commit the Perseus vault database, exported vault files, or any encryption key/secret material.
- The vault database is user-scoped local state (default `~/.perseus-vault/`), never a path inside this repository's tracked tree.
- Fail soft if the CLI or MCP server is unavailable.
- Keep this integration repo-native: do not depend on Perseus assets stored outside the current repository.
- Persist only durable, reusable findings; never secrets, credentials, customer data, or machine-local workspace paths.
