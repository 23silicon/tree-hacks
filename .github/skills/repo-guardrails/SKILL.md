---
name: repo-guardrails
description: Safety and scope-enforcement skill for protected paths and human-reviewed changes.
---

# Repository Guardrails Skill

## When to use
- User requests broad edits by autonomous agents.
- You detect potential high-impact changes across core runtime folders.
- You need to enforce human review for protected paths.

## Protected paths
- `frontend/src/graph/`
- `sentiment-tree/pipeline/`
- `api/`

## Allowed autonomous write scope
- `openclaw/`
- `.github/agents/`
- `.github/skills/`
- docs at repository root

## Policy
1. Default to read-only analysis for protected paths.
2. Require explicit user confirmation before proposing or applying edits there.
3. Keep edits minimal and scoped when approved.
4. Document assumptions and touched paths clearly.

## Output checklist
- Requested scope vs. protected scope assessment
- Any required confirmation prompts
- Minimal safe change plan
