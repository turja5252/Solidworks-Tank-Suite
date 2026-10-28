import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";

const stepSchema = z.object({
  title: z.string().min(1).max(120),
  detail: z.string().min(1).max(2000),
  dependsOn: z.array(z.string()).optional(),
});

export default defineTool({
  description: prompt`
    Persist the current implementation plan for this session.
    Call once the plan is complete enough to act on. Overwrites the
    session's previous saved plan.
  `,
  effect: "idempotent",
  inputSchema: z.object({
    goal: z.string().min(1).max(500),
    assumptions: z.array(z.string()).optional(),
    steps: z.array(stepSchema).min(1).max(40),
    risks: z.array(z.string()).optional(),
    doneWhen: z.array(z.string()).min(1).max(20),
  }),
  async execute(plan, ctx) {
    const id = `plan:${ctx.session.id}`;
    const record = {
      id,
      sessionId: ctx.session.id,
      savedAt: new Date().toISOString(),
      ...plan,
    };
    await ctx.host.kv.put(id, record);
    await ctx.host.files.forSession(ctx.session.id).write(
      "plan.json",
      JSON.stringify(record, null, 2),
    );
    return {
      id,
      stepCount: plan.steps.length,
      savedAt: record.savedAt,
    };
  },
});
