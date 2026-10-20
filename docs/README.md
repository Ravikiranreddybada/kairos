# Kairos documentation

Kairos is a supply-chain decision platform. It turns raw sales history into
**decisions a planner can act on**: how much will sell (with uncertainty),
when to reorder and how much, what a promotion will do, which numbers look
wrong – and a grounded copilot that answers those questions in plain language
with every number traced to a tool output.

Read in this order:

| # | Folder | What you get | Read when |
|---|--------|--------------|-----------|
| 00 | [overview](00-overview/) | Problem, users, success metrics, scope | First, always |
| 01 | [plan](01-plan/) | Roadmap, milestones with acceptance criteria, risk register | Planning or reviewing progress |
| 02 | [requirements](02-requirements/) | Functional requirements, SLOs and non-functional budgets | Before designing a change |
| 03 | [system-design](03-system-design/) | Architecture, data flow, each subsystem in depth, scaling, security, failure modes | Before touching code |
| 04 | [tech-stack](04-tech-stack/) | Every technology, why it won, what it lost to | Questioning a dependency |
| 05 | [decisions](05-decisions/) | 22 Architecture Decision Records | Wondering "why is it like this?" |
| 06 | [evaluation](06-evaluation/) | How forecasts and the agent are measured; current results | Changing a model or prompt |
| 07 | [runbooks](07-runbooks/) | Local dev, deployment, incident playbook | Operating it |
| 08 | [build-guide](08-build-guide/) | Step-by-step build from empty repo to production | Rebuilding or extending it |
| 09 | [interview](09-interview/) | How to present it, deep-dive Q&A | Explaining it to others |

Conventions: diagrams are Mermaid (render on GitHub). Numbers quoted in docs
come from `kairos train` / `kairos eval` on the default synthetic dataset
(4 stores × 12 SKUs × 730 days, seed 7) and are reproducible bit-for-bit.
