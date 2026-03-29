# OpenClaw Compatibility Layer

This folder provides an OpenClaw-style compatibility surface for agent planning, simulation, and dry-run execution.

Status: active for planning mode, dry-run only.

## What is here
- `openclaw.manifest.json`: task and capability manifest
- `contracts/pipeline-input.schema.json`: expected ingestion payload
- `contracts/pipeline-output.schema.json`: expected enrichment payload

## Execution policy
- Planning and analysis against this folder is allowed.
- Mutation of core application folders is blocked unless a human reviewer explicitly approves.
