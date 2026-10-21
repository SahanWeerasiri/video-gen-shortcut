# ADR-0002: Client-Side Session Hash Generation Scheme

**Date**: 2026-10-21
**Status**: accepted
**Deciders**: Sahan Weerasiri, Antigravity Agent

## Context

Gradio applications use a query parameter named `session_hash` across queue endpoints (`/gradio_api/queue/join?` and `/gradio_api/queue/data?session_hash=...`). This hash correlates a client's queued inference requests with its dedicated Server-Sent Events (SSE) response channel.

When analyzing the Perchance integration (`https://perchance.org/ltx-video`) and the network log (`docs/findings/data.txt`), it was initially unclear whether `session_hash` was:
1. A server-issued security session token or anti-bot challenge result.
2. A cryptographic signature derived from client IP / cookies.
3. A client-generated pseudo-random identifier.

## Decision

We determined and decided to use **stateless client-side pseudo-random 11-character alphanumeric generation** for the `session_hash`.

Replicating Gradio's native client implementation:
- **Gradio JavaScript Client:**
  ```javascript
  const session_hash = Math.random().toString(36).substring(2, 13);
  ```
- **Python Implementation:**
  ```python
  import random, string
  session_hash = ''.join(random.choices(string.ascii_lowercase + string.digits, k=11))
  ```

Every generation job uses a freshly generated `session_hash` to isolate the SSE stream and eliminate state sharing.

## Alternatives Considered

### Alternative 1: Handshaking with Perchance to Obtain a Session Token
- **Pros**: Matches potential token-handshake assumptions.
- **Cons**: Perchance does not generate or manage the Gradio hash; it merely renders an iframe embedding Hugging Face. Handshaking with Perchance would introduce unnecessary complexity and Cloudflare challenges.
- **Why rejected**: Proved through source code analysis that the hash is entirely an internal Gradio frontend concept, not issued by Perchance.

### Alternative 2: Static or Reused Session Hash
- **Pros**: Fewer random calls.
- **Cons**: If multiple concurrent jobs or re-runs use the same hash, Gradio's queue server can cross-route SSE event streams, leading to duplicate progress messages or dropped event listeners.
- **Why rejected**: Generates non-deterministic race conditions during concurrent runs.

## Consequences

### Positive
- **Completely Stateless**: No pre-flight authentication or handshake roundtrips needed just to generate a session identifier.
- **Zero Collision Risk**: An 11-character base-36 string provides $36^{11} \approx 1.3 \times 10^{17}$ possible combinations, eliminating collision probability across jobs.
- **Instant Connection**: Allows immediate registration with `/gradio_api/queue/join?`.

### Negative
- None identified.
