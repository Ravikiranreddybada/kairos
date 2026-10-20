# ADR-0012: Explicit agent graph and read-only tools

Status: Accepted · Date: 2026-10-18 · Node order superseded by ADR-0016 (guard → route → cache)

## Context

A free-running ReAct loop puts every policy (budgets, guards, verification) inside the prompt, where it is untestable and can be talked around. An agent that can write to an ERP turns any successful prompt injection into a business loss.

## Decision

The copilot is a LangGraph state machine: guard → cache → route → llm ⇄ tools → verify → finalize, with code-enforced step/token budgets and a grounding verifier. All tools are read-only. Anything that changes the world (placing an order) will be a separate, human-approved workflow.

## Consequences

+ Each policy is a node or an edge with its own test (blocked injection spends 0 tokens; loop stops at budget; degraded mode on outage).
+ Prompt injection's worst case is a wrong *answer*, which the verifier and the planner can catch – never a wrong *action*.
− Less "autonomous". This is the intended trade-off for a decision-support tool.

## Alternatives considered

ReAct agent executor (opaque policies); multi-agent planner/worker (more latency and failure modes for no capability gain); write-capable tools with confirmation prompts (prompt-level confirmation is bypassable).
