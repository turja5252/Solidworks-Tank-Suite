import { prompt } from "@grok/agent-sdk";
import { defineTool } from "@grok/agent-sdk/tools";
import * as z from "zod/v4";

export default defineTool({
  description: prompt`
    Load the implementation plan saved for this session.
    Use before revising a prior plan, or when the user asks what was planned.
  `,
  effect: "read",
  inputSchema: z.object({}),
  async execute(_input, ctx) {
    const id = `plan:${ctx.session.id}`;
    const plan = await ctx.host.kv.get(id);
    if (!plan) {
      return { found: false as const, id };
    }
    return { found: true as const, plan };
  },
});
