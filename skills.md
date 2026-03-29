# Skills Index

This repository includes custom Copilot skills for OpenClaw compatibility and safety guardrails.

## Available Skills
- `.github/skills/openclaw-compat/SKILL.md`
  - Use for OpenClaw planning mode, contract/schema discovery, and dry-run analysis.
- `.github/skills/repo-guardrails/SKILL.md`
  - Use for enforcing protected path behavior and review-first workflows.

## Usage Notes
- Prefer read-first analysis before proposing file edits.
- Route agent planning tasks to `openclaw/` artifacts when possible.
- Require explicit human confirmation before runtime-code edits in protected paths.
