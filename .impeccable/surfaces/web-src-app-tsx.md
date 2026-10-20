---
version: 1
slug: "web-src-app-tsx"
primary_target: "web/src/App.tsx"
related_targets: []
---

Scope: Kairos copilot chat, the first web surface (web/). Mode: Operate.
Audience: store/category planner deciding weekly orders; secondary, interview reviewers.
Task: ask a question, watch the graph work, read a grounded answer, inspect the evidence behind every figure.
Constraints: read-only; evidence comes from the same REST endpoints the tools use; states ok, blocked, degraded, budget_exhausted, ungrounded must be visible.

## Direction contract

THESIS: Each question is a requisition on a multi-part form pad. The answer is typed onto the white top copy; the evidence is the canary copy under it; the audit facts (trace, tokens, cost, data version) are the pink copy. Refuses the category default: dark dashboard, chat bubbles, sidebar of cards, blue accent.

OWN-WORLD: Flat paper sheets (#F7F7F4 white, #F4E38A canary, #F1C9D2 pink), preprinted ledger-green rules and field captions (#4F7A63), carbon-blue fill ink (#23306B) for everything the system wrote, one stamp per answer (VERIFIED in carbon blue, UNVERIFIED/BLOCKED in errata red). Archivo for preprinted form text, Fragment Mono only for filled numbers and IDs. Square corners, 1px rules, no shadows except one short hard-edged sheet offset for the stacked copies. Dark mode is the carbon sheet: blue-black ground, pale transferred ink.

STORY: The planner sees a pad of past requisitions, types a question into the open form, watches the routing slip fill line by line (guard, route, cache, LLM, tools, verify, finalize), then reads a filled answer with a stamp. They flip to the canary copy to see the tool data and chart that produced each number, and the pink copy for the audit trail.

FIRST VIEWPORT: Three columns on desktop. Left 240px: the pad, numbered requisitions with store/SKU and status mark, "New requisition" at top. Centre: the open form, numbered header row, question field, routing slip, answer body in carbon ink, stamp at lower right. Right 420px: the copy stack with tabs Canary (evidence) and Pink (audit). Empty state shows a blank form with three example requisitions to fill. Primary action: the question field plus Submit at the form's foot.

FORM: Carbon-copy requisition pad, own list position 4 of 7, seed key 2aef8acb. Raises: visible ledger grid as structure (Crouwel); one ink owns live state (Metro); focused requisition opens its copies, others fold (streaming wall); tool trace bars sized by real latency (Labanotation); one mono at tabular density for numbers (Ikeda).

Adaptation (after first render): figures inside answer prose are Archivo semibold tabular, not Fragment Mono; mono figures in running text read as spaced-out digits. Identifiers (stores, SKUs, run ids) and all table and field values stay in Fragment Mono.

Signature interaction: the routing slip. Each graph node stamps its line as SSE events arrive, tool calls draw latency-length bars, and the final stamp lands with a 2-frame 90ms step, no easing.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
