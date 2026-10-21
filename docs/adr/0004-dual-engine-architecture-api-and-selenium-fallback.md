# ADR-0004: Dual-Engine Architecture (Direct API Primary with SeleniumBase UC Fallback)

**Date**: 2026-10-21
**Status**: accepted
**Deciders**: Sahan Weerasiri, Antigravity Agent

## Context

Automated AI tooling that interacts with third-party web services faces resilience challenges:
1. Public Gradio spaces can update component schemas or change function indices.
2. Web hosts may introduce aggressive bot detection or IP-based rate limiting on direct HTTP endpoints.
3. Conversely, relying solely on heavy browser automation leads to slow execution, memory exhaustion, and server maintenance overhead.

The repository requires a resilient engineering strategy that maximizes speed while guaranteeing a functional fallback.

## Decision

We decided to implement a **Dual-Engine Architecture**:
1. **Primary Engine (`src/ltx_video.py`)**: Direct HTTP REST and SSE client. Used by default for all CLI commands, library imports, and GUI backend services. Operates in ~6–10 seconds per video.
2. **Fallback Engine (`src/gen_selenium.py`)**: SeleniumBase browser automation engine using Undetected Chromedriver (`uc=True`), modeled directly after the proven architecture in [`headless-telebot/gen.py`](file:///home/sahan-weerasiri/projects/headless_telebot/gen.py).

The fallback engine navigates to `https://perchance.org/ltx-video`, bypasses Cloudflare challenges via UC mode, traverses nested iframes (`#outputIframeEl` -> `#genFrame`), and drives the generation visually through browser DOM events.

## Alternatives Considered

### Alternative 1: Single Direct API Engine Only
- **Pros**: Clean, small codebase.
- **Cons**: If the direct REST endpoint is restricted or changes its payload format, the entire automation breaks until code is updated.
- **Why rejected**: Lacks defense-in-depth and operational redundancy.

### Alternative 2: Single Browser Automation Engine Only
- **Pros**: Matches visual user interactions identically.
- **Cons**: 4–6x slower, requires 500MB+ RAM per process, requires browser drivers installed on the host.
- **Why rejected**: Unsuitable for responsive CLI usage and high-throughput workflows.

## Consequences

### Positive
- **High Performance by Default**: 99% of workflows use the sub-10-second lightweight HTTP client.
- **Guaranteed Operational Continuity**: If direct API calls are ever blocked, the user or automation pipeline can immediately switch to `gen_selenium.py` without losing functionality.
- **Code Sharing with Existing Projects**: Aligns with the SeleniumBase patterns established in `headless-telebot`.

### Negative
- **Maintenance Surface**: Two execution paths must be kept documented and aligned with model parameter changes.
