---
name: resources
description: How parallel AI sessions share scarce machine resources - locks, queues and priorities for heavy test runs, databases, browsers, model quota and ports - and how to tell an infrastructure failure from a real one. Read before running a full test gate, database or browser tests, real model calls, or a service that needs a port, and before deciding whether a failure is caused by the code.
---

# Shared resources

Where the project's own rules differ from this playbook, the project's rules win.

## Take a lock first, always

- Every shared resource is behind a lock (`admiral lock`). A lock records its holder and pid; a holder that exited or timed out is stale and may be taken over safely.
- If the lock is busy, queue (`admiral lock acquire --wait`); never go around it.
- Design the lock kinds after the resources, for example:

| Lock | Guards | Rule |
|---|---|---|
| heavy gate | the full local gate, browser tests, manual browser checks and screenshots, long test partitions | one at a time; before taking it, look read-only at CI state, machines and containers |
| short slots (N of them) | short jobs on a private resource, such as tests against a private database without a browser expected under 20 minutes | at most N at once; take any free one; check free memory before taking |
| model quota (N of them) | real model evaluations | at most N groups in parallel, sequential within a group; small checks under ten calls take none |
| port | dev servers, acceptance services, proxies | allocated by the tool, never hand-picked |

## Queueing

- Short jobs first, everywhere, without negotiation: a job expected under 20 minutes queues with priority 1; a full gate or full test partition queues at 0, and nobody raises their own full gate.
- No starvation: a full gate waiting 60 minutes is raised to priority 1 by any commander. Equal priorities run in arrival order.
- A job marked short that ran over 30 minutes says why in its status and is not marked short again.
- Pushing a branch or opening a PR does not mean resources are free.

## Infrastructure failures

- When contention crashes a worker, times out a browser, hangs a container or slows everything, the result is infrastructure-invalid: rerun once after the resource frees, and do not blame the code.
- A browser test that failed while short-slot jobs were running is first rerun as is, then investigated.

## Real model calls

- Where the product itself calls models, development tests, acceptance and evaluation use the model and reasoning setting production uses now, never a name from an old script, task brief or conversation.
- When the model provider starts rate limiting, every group stops; nobody pushes through it or lifts a limit by hand.
- Before evaluating, confirm the code loaded is your worktree's.
- Precise and deep: decide the question first, design the fewest runs, reuse evidence, and run real-model checks and wide acceptance once per stage rather than after every small step. Report the number of calls and the model actually used.
