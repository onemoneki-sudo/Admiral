---
name: resources
description: How parallel AI sessions share scarce machine resources - locks and queues for heavy test runs, databases, browsers, model quota and ports - and how to tell an infrastructure failure from a real one. Read before running the whole test suite, database or browser tests, real model calls, or a service that needs a port, and before deciding whether a failure is caused by the code.
---

# Shared resources

Where the project's own rules differ from this playbook, the project's rules win.

## Take a lock first

- Every scarce resource is behind a lock (`admiral lock`). A lock records its holder and pid; one whose holder exited
  or timed out may be taken over.
- If the lock is busy, queue (`admiral lock acquire --wait`); never go around it.
- Name the locks after what the project actually shares, for example: one heavy slot for whole-suite and browser runs,
  a few slots for a test database, a few for model quota, and ports handed out by the tool rather than picked by hand.

## Queueing

- Short jobs go first; nobody raises the priority of their own long job.
- Nothing waits forever: a commander raises a long job that has waited well past its turn (`admiral lock prio`).
- A job started in the background that is meant to finish gets a time limit from how long it should take: you hear
  when a job exits, not when it hangs, and a hung job keeps its lock. While you are still working, one whose output has
  stopped growing is looked into rather than waited on.

## When it was the machine, not the code

When contention crashes a worker, times out a browser or slows everything, the run says nothing about the code: rerun
it once the resource is free before investigating.

## Real model calls

- Where the product calls models, test and evaluate with the model and settings production uses now.
- When the provider starts rate limiting, stop; never push through it.
- Decide the question first and run the fewest calls that answer it; report how many calls and which model.
