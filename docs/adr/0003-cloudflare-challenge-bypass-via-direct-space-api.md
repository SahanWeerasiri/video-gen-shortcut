# ADR-0003: Cloudflare Challenge Bypass via Direct Space API Architecture

**Date**: 2026-10-21
**Status**: accepted
**Deciders**: Sahan Weerasiri, Antigravity Agent

## Context

During exploration of `https://perchance.org/ltx-video`, automated HTTP requests directly to `perchance.org` were met with HTTP 403 Forbidden responses caused by Cloudflare Turnstile bot protection (*"Just a moment..."*).

We investigated whether Cloudflare posed a blocker to programmatic CLI automation, and evaluated how the client should be structured to guarantee continuous, unblocked operation.

## Decision

We decided to **completely decouple the CLI from `perchance.org` and target the Hugging Face Space origin directly** (`https://lightricks-ltx-video-distilled.hf.space`).

Through DOM and network analysis with SeleniumBase, we verified that:
1. `perchance.org/ltx-video` is strictly a presentation wrapper embedding the Hugging Face Space inside an iframe (`<iframe id="genFrame" src="https://lightricks-ltx-video-distilled.hf.space">`).
2. Cloudflare Turnstile protection is placed exclusively at the `perchance.org` domain boundary.
3. Hugging Face Spaces (`*.hf.space`) expose their Gradio API endpoints directly via Uvicorn/FastAPI without Cloudflare Turnstile, CAPTCHA challenges, or bot-blocking intermediaries for standard HTTP requests.

## Alternatives Considered

### Alternative 1: Solving Cloudflare Turnstile via Headless Browser Solvers (e.g., 2Captcha, Turnstile solvers)
- **Pros**: Navigates through `perchance.org` front door.
- **Cons**: Adds third-party billing costs, introduces 10–30 second latency per request, fragile, and often breaks when Cloudflare updates fingerprinting algorithms.
- **Why rejected**: Wholly unnecessary because the actual inference backend is not behind Cloudflare.

### Alternative 2: Proxied Requests Through Perchance Session Cookies
- **Pros**: Maintains association with Perchance telemetry.
- **Cons**: Subject to cookie expiration and Cloudflare session invalidation.
- **Why rejected**: The generation API is hosted independently on Hugging Face infrastructure.

## Consequences

### Positive
- **100% Reliable Programmatic Access**: Automated CLI scripts and background workers execute without ever encountering Cloudflare challenges.
- **Zero Third-Party Solver Overhead**: No external CAPTCHA-solving services or API keys required.
- **Direct Connection Latency**: Eliminates the intermediate proxy hop through Perchance.

### Negative
- **Perchance Telemetry**: Imports and counters tracked via Perchance plugins (`data2.txt`) are not incremented when calling the Hugging Face Space directly. (This is desirable for private/automated batch workflows).

### Risks
- **Hugging Face WAF Policies**: Hugging Face could potentially introduce rate limits or WAF policies on public spaces in the future.
  - *Mitigation*: We implement Space health verification (`check_and_wake_space()`), support optional Hugging Face auth tokens (`HF_TOKEN`), and provide a full browser-based SeleniumBase fallback (`src/gen_selenium.py`).
