---
name: openclaw-compat
description: OpenClaw compatibility skill for planning and dry-run analysis using repository contracts.
---

# OpenClaw Compatibility Skill

## When to use
- User asks for OpenClaw planning, compatibility checks, or contract/schema walkthroughs.
- You need a stable integration surface for agent reasoning without touching runtime code.

## Primary scope
- `openclaw/**`
- `README.md`
- `ARCHITECTURE.md`

## Behavior
1. Read OpenClaw manifest and contract schemas first.
2. Produce planning-oriented output, not runtime code rewrites.
3. Prefer dry-run recommendations over direct modifications.

## Constraints
- Treat `openclaw/` as canonical for agent-side planning contracts.
- If runtime code changes are requested, ask for explicit confirmation first.

## Outputs
- Contract mapping summaries
- Input/output payload expectations
- Risk notes for integration boundaries
