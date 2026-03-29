# Repository Agent Guardrails

This repository contains protected code paths.

## Allowed autonomous-agent scope
- Primary integration surface: `openclaw/`
- Agent configs: `.github/agents/`
- Public docs: `README.md`, `ARCHITECTURE.md`

## Restricted paths (human-reviewed changes only)
- `frontend/src/graph/`
- `sentiment-tree/pipeline/`
- `api/`

## OpenClaw compatibility note
OpenClaw-compatible task descriptors are provided under `openclaw/` for agent-side planning and dry-run analysis. Agents should treat these as the canonical integration contract.

## Safety rule
Any write outside allowed autonomous-agent scope requires explicit human approval in the PR description.
