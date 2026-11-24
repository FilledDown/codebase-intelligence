# Behavioral analysis (Layer D: what the software does)

## Contents
- Purpose
- Tracing procedure
- Adapting to the architecture
- What to capture on every flow
- Recording a flow
- When to stop

## Purpose

File lists and import graphs say what exists. Behaviour is what happens when something runs: which code executes, in what order, which state changes, what can fail, and what leaves the process. Trace flows by reading code, following calls from a trigger to its effects.

## Tracing procedure

1. **Pick the trigger.** A user action, an HTTP route, a CLI command, a scheduled job, a message, a game event. If the user did not name one, choose from the entry points and the highest-traffic hubs in the graph.
2. **Find the first handler.** Read the entry point; follow registration (router tables, decorators, event subscriptions, command parsers) to the function that receives the trigger. Registration is often convention-based, so search for the route string or event name rather than relying on imports.
3. **Follow calls one hop at a time.** At each step note the function, the data it receives, what it decides, and what it calls next. Use the graph to find where a callee lives, then read the callee: names lie.
4. **Record state transitions.** Variables, objects, database rows, cache entries, files, UI state that change, and in what order.
5. **Record side effects.** Network calls, writes, emitted events, logs, notifications, timers.
6. **Follow the failure paths.** For each fallible step: what is thrown or returned, who catches it, what the caller sees, whether state is left half-updated.
7. **Mark each hop VERIFIED or INFERRED.** VERIFIED means you read the call site and the callee. INFERRED means you followed a name, a convention or a framework behaviour you did not read.

## Adapting to the architecture

Do not force every system into "UI → service → DB → UI". Choose the shape that fits:

| System type | Typical trace shape |
|---|---|
| Web service | request → middleware → route handler → service/logic → data access → response; plus auth and validation points |
| Single-page app | event → handler → state update → (async call → state update) → render |
| CLI | argv parsing → command dispatch → work → output/exit code |
| Library | public function → internal helpers → return value or raised error; trace the public API, not `main` |
| Event/queue consumer | message arrival → deserialise → handler → side effects → ack/retry/dead-letter |
| Pipeline / batch | input read → stages → output write; where it can resume or re-run |
| Game / realtime | tick or event → systems/scripts → state replication; client/server authority |
| Embedded / driver | interrupt or poll → state machine → hardware effect |

## What to capture on every flow

- **Trigger and preconditions** (who/what, what must already be true).
- **Ordered steps** with `file:symbol` for each.
- **State transitions** and where state lives.
- **Asynchrony**: awaits, callbacks, threads, queues; ordering guarantees and race windows you can see.
- **Side effects** and their idempotency (what happens if the step runs twice).
- **Error paths** and what is left behind after a failure.
- **Where it crosses a boundary** (process, network, trust level): see `data-flow-analysis.md`.

## Recording a flow

Use a numbered list, one line per step, with an evidence tag:

```
Flow: user submits login form
1. [VERIFIED] web/routes.py:login_post receives form → calls auth.service.authenticate
2. [VERIFIED] auth/service.py:authenticate loads user via users/repo.py:find_by_email
3. [INFERRED] password check delegated to library named in auth/crypto.py (library source not read)
4. [VERIFIED] on failure raises AuthError (auth/service.py) → caught in web/routes.py, returns 401, no state changed
5. [UNKNOWN] session storage backend: configured via SESSION_BACKEND, value not present in repo
```

## When to stop

Stop tracing when you reach a framework or library boundary you do not own, a point where behaviour depends on runtime configuration you cannot see, or the depth that answers the user's question. Say where you stopped and why. A flow that ends in UNKNOWN with a named missing fact is more useful than one that guesses.
