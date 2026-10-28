---
description: Use when turning a non-trivial goal into a structured implementation plan with steps, dependencies, and acceptance criteria.
---

# Implementation plan procedure

1. Restate the goal in one sentence. If scope is ambiguous, list at most
   three clarifying assumptions and proceed with the most likely reading.
2. Split the work into ordered steps. Each step names a concrete outcome
   (file, API, UI surface, or decision), not a vague phase.
3. Note dependencies between steps (`dependsOn` titles) when order matters.
4. Call out risks or open questions only when they could change the plan.
5. Write acceptance criteria under **Done when** that a reviewer could check.
6. Call `save_plan` with the structured fields, then reply in the
   instructions output shape.
