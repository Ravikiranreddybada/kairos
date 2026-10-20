# ADR-0010: Deterministic FakeLLM eval gate in CI

Status: Accepted · Date: 2026-10-18

## Context

Agent behaviour can regress from any change: a tool description, a guard regex, a router rule, a schema change. Running a real LLM on every PR costs money, needs secrets in CI, and is non-deterministic, so failures are noisy.

## Decision

`FakeLLM` implements `LLMClient` with deterministic planning and answers written only from tool outputs. The golden set (28 cases at time of writing, ground truth recomputed from live SQL) runs on every PR through the *real* graph, tools, guards, verifier and cache, with thresholds in `evals/thresholds.json`. A nightly job runs the same suite against Claude.

## Consequences

+ Every PR is gated for free; failures are reproducible.
+ The eval already caught real bugs during development (a routing bug where "how long can promotions run" triggered the what-if tool).
− FakeLLM does not measure the real model's reasoning; that is the nightly job's role. The two together cover plumbing (PR) and model quality (nightly).

## Alternatives considered

Record/replay cassettes (brittle on any prompt change); real model on every PR (cost, flakiness, secrets).
