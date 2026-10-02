# Court4 Agent Instructions

Court4 is an evidence-first sports video analytics platform.

## Product principles

- Court4 must be reliable, truthful, and useful to athletes and coaches.
- Never present measurements more confidently than the evidence supports.
- Do not fabricate metrics, Match IQ claims, tactical events, or player conclusions.
- Verified evidence is the source of truth.
- Pickleball is the current primary supported sport.
- Padel remains gated until explicitly enabled.
- `BALL_TRACKING_ENABLED=false` must remain unchanged unless explicitly requested.

## Engineering safety

- Preserve auth, ownership, rate limiting, storage integrity, and lifecycle safety.
- Do not weaken tests to make them pass.
- Do not delete or wipe Railway volumes.
- Do not change Railway variables unless explicitly requested.
- Prefer repository-managed processing workspaces over legacy `/app/data/output` paths.
- Inspect existing architecture before redesigning behavior.
- Keep changes narrow and evidence-driven.

## Multi-agent safety rules

- Only one agent may edit the working tree at a time.
- Switch agents only when:
  1. the current agent is blocked by a usage limit, or
  2. implementation is complete and an independent review is deliberately requested.
- Do not switch agents simply because another agent is available.
- Continue existing implementation; do not redesign completed work for preference.
- Structural changes require a concrete defect or explicit instruction.
- Reviewers are read-only unless explicitly asked to implement a blocker fix.
- Do not duplicate tests unless there is a distinct uncovered failure mode.
- Do not treat agreement between agents as proof of correctness.
- Tests, staging evidence, logs, persisted state, code, and git diff are authoritative.

## Handoff durability

- Do not wait until task completion to update `docs/dev/CURRENT_TASK.md`.
- Update it:
  - when starting a substantial task;
  - after each meaningful implementation milestone;
  - after important validation/test results;
  - when assumptions or remaining work change.
- If interrupted unexpectedly, the handoff file should still describe the latest known state.
- Git status, git diff, code, and test results are authoritative if the handoff note is stale.

## Working rules

- Always inspect `git status` and the current diff before editing.
- If another agent worked on the task, inspect existing changes before continuing.
- Preserve validated changes unless a concrete defect is found.
- Do not stage, commit, push, or deploy unless explicitly asked.
- Run focused tests first.
- Broaden validation only when the touched scope justifies it.
