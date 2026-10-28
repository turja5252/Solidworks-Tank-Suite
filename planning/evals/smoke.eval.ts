import { defineEval } from "@grok/agent-sdk/evals";

export default defineEval({
  tags: ["smoke"],
  description: "Saves a structured plan for a small feature request.",
  async test(t) {
    await t.send(
      "Plan adding a JSON export button to the Tank Properties tab. Keep it short.",
    );
    t.succeeded();
    t.calledTool("save_plan");
  },
});
