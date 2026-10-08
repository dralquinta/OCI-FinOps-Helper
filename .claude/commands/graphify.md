# /graphify

Knowledge graph tool for code understanding and navigation.

## Runtime

- Target: Claude Code
- Invocation: run or reference `/graphify` in Claude Code
- Workspace assumption: repository-local command with shell and file access

## Overview

Use this skill when you need a local knowledge graph for this repository, want to query or explain code structure, or want to understand dependencies and relationships.

Graphify complements the tokensave MCP tools: prefer tokensave for quick symbol lookups, and use Graphify when you need a regenerable, shareable graph report. PR steering and infrastructure rules live in `.codex/instructions.md`.

Integration principles:

- Keep Graphify integration repo-native
- Do not depend on Graphify assets stored outside the current repository
- Keep generated Graphify output under `graphify-out/`

## Install And Bootstrap

1. Install the official Graphify CLI package if not already available. The CLI command is `graphify`.
2. Build the graph from the repository root with the Graphify build command for the installed version.
3. If Graphify is not installed, say so and fall back to tokensave or targeted file reads. Do not install it without the user's confirmation.

## Workflow

- `graphify query "<question>"`: answer questions about code structure and relationships
- `graphify explain "<node>"`: explain a specific code node
- `graphify path "<from>" "<to>"`: show call paths between two nodes

Expected outputs:

- `graphify-out/graph.html`: interactive graph visualization
- `graphify-out/GRAPH_REPORT.md`: graph analysis report
- `graphify-out/graph.json`: raw graph data

## Freshness Rules

- Refresh the graph regularly during development so references stay current.
- Patterns in `.graphifyignore` (if present) are applied during graph generation. Exclude `customer_files/`, `output/`, and `*.csv`.
- If Graphify is not installed locally, operations fail with a clear error; report it and continue.

## Principles

- Keep Graphify output untracked via `.gitignore` (`graphify-out/`, `.graphify/`).
- Keep all repo docs and scripts repo-relative; do not preserve machine-local paths.
- Do not paste large graph output inline.
