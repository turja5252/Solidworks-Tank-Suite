# Planning agent

Agent SDK agent that turns goals into structured implementation plans.

## Local loop

```bash
cd planning
npx @grok/agent-sdk validate --dir .
npx @grok/agent-sdk info --dir . --json
npx @grok/agent-sdk tool call save_plan --dir . --input '{"goal":"Ship floor module","steps":[{"title":"Sketch API","detail":"Define floor params"}],"doneWhen":["API sketched"]}'
npx @grok/agent-sdk run --dir . --message "Plan the next tank floor module"
npx @grok/agent-sdk serve --dir . --mode single --dev
# http://127.0.0.1:3000/playground
```

## Layout

| Path | Role |
| --- | --- |
| `bot/instructions.md` | Always-on planning contract |
| `bot/tools/save_plan.ts` | Persist plan for the session |
| `bot/tools/get_plan.ts` | Load the session plan |
| `bot/skills/implementation-plan.md` | Procedure for non-trivial goals |
| `evals/smoke.eval.ts` | Smoke: model calls `save_plan` |
