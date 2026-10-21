# ADR-0001: Direct HTTP and SSE API Automation Over Browser Scraping

**Date**: 2026-10-21
**Status**: accepted
**Deciders**: Sahan Weerasiri, Antigravity Agent

## Context

The initial goal of the project is to automate AI video generation using the Lightricks LTX-Video Distilled model, as observed in browser network traces (`docs/findings/data.txt`) and Perchance telemetry (`docs/findings/data2.txt`). 

We needed to establish the foundational architecture for executing video generation programmatically from terminal scripts, automated workflows, and future user interfaces.

The primary constraints are:
- **Execution Speed**: Video generation should be triggered immediately without the startup overhead of browser engines.
- **Resource Footprint**: Running full browser instances (Chromium, Brave, or Firefox) consumes excessive CPU/RAM (300MB–1GB+ per instance).
- **Process Reliability**: Headless browsers suffer from rendering timeouts, DOM mutation race conditions, and fragile CSS/XPath selectors.

## Decision

We decided to interact **directly with the backend Gradio 5 REST and Server-Sent Events (SSE) API** (`https://lightricks-ltx-video-distilled.hf.space`) using lightweight Python HTTP requests (`requests` library) rather than browser-driven UI automation.

Specifically, the workflow:
1. Uploads input media via `POST /gradio_api/upload`.
2. Queries preprocessing and dimension calculations via `POST /gradio_api/queue/join?` (`fn_index: 0`).
3. Dispatches inference jobs via `POST /gradio_api/queue/join?` (`fn_index: 5` for Image-to-Video, `fn_index: 4` for Text-to-Video).
4. Streams execution status and progress updates over `GET /gradio_api/queue/data?session_hash=<hash>` using `text/event-stream`.
5. Streams the completed MP4 artifact from the server file endpoint to disk.

## Alternatives Considered

### Alternative 1: Pure Browser Automation (Selenium / Playwright / Puppeteer)
- **Pros**: Matches exact user interaction in the browser; immune to internal API schema shifts as long as the visual UI remains stable.
- **Cons**: High memory and CPU usage, requires browser binary installations, execution is 4–6x slower, and prone to iframe loading race conditions.
- **Why rejected**: Inefficient for automated CLI and service pipelines. Direct API requests execute the complete generation lifecycle in ~6.5 seconds.

### Alternative 2: Official `gradio_client` Python SDK
- **Pros**: High-level Python abstractions provided by the Gradio team.
- **Cons**: Introduces heavy transitive dependencies, has rigid blocking queue polling loops, and occasionally breaks when Hugging Face Spaces run newer or custom Gradio major versions (e.g. Gradio 5.42+ vs older client specs).
- **Why rejected**: Direct HTTP requests with standard `requests` and SSE line parsing gave complete control over timeouts, connection reuse, and zero external dependency bloat.

## Consequences

### Positive
- **Extreme Speed**: Eliminates browser launch latency; job submission and streaming starts in sub-second time.
- **Minimal Dependencies**: Only standard Python `requests` and `Pillow` are required.
- **Real-Time Visibility**: Direct access to Gradio's SSE messages (`estimation`, `process_starts`, `progress`, `process_completed`).
- **Headless & Container-Ready**: Can run seamlessly on headless Linux servers, Docker containers, and CI environments without X11/Xvfb.

### Negative
- **API Coupling**: If Hugging Face Space updates the function signature indices (`fn_index`), the payload structure must be updated.

### Risks
- **Endpoint Drift**: Changes to component IDs or Gradio API versions.
  - *Mitigation*: The client inspects `/config` on the Space and validates endpoints on initialization.
