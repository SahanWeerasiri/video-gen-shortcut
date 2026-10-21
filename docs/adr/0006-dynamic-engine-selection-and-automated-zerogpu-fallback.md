# ADR-0006: Dynamic Engine Selection and Automated ZeroGPU Fallback

**Date**: 2026-10-21  
**Status**: accepted  
**Deciders**: Sahan Weerasiri, Antigravity Agent  

## Context

The direct HTTP/SSE engine interacts with the Hugging Face Space for Lightricks LTX-Video Distilled (`https://lightricks-ltx-video-distilled.hf.space`). Because the space is hosted on Hugging Face **ZeroGPU** infrastructure, anonymous or high-usage requests are subject to strict compute quotas (`You have exceeded your ZeroGPU quota`). When this quota is exhausted, direct requests fail immediately with an error.

Users needed:
1. An uninterrupted generation pipeline that does not abruptly halt when Hugging Face ZeroGPU quotas are exceeded.
2. The ability to select their preferred generation engine directly from the Web GUI:
   - Ultra-fast Direct API (~6.5s) when quota is available or when authenticated with an `HF_TOKEN`.
   - Browser-automated SeleniumBase (Perchance) engine when ZeroGPU quotas are exhausted or for anonymous unlimited use.
   - An intelligent automatic fallback mode that tries Direct first and seamlessly falls back to Selenium if an error occurs.
3. Full support for both Text-to-Video and Image-to-Video across both engines.

## Decision

We implemented **Dynamic Engine Selection with Automated ZeroGPU Fallback**:

1. **Engine Modes (`server.py`)**:
   - `auto` *(default)*: Dispatches to the Direct API client first. If a `ZeroGPU quota exceeded`, HTTP 503, or connection failure occurs, the server emits a `fallback` event via SSE to inform the UI and seamlessly invokes the Selenium browser engine (`PerchanceLTXGenerator`) to complete the video.
   - `direct`: Restricts generation to the direct Hugging Face REST/SSE API client only.
   - `selenium`: Bypasses the direct Hugging Face Space entirely and executes through SeleniumBase UC mode on Perchance.

2. **Web GUI Toggle Controls (`src/static/`)**:
   - Added a modern segmented engine control bar to [`index.html`](file:///home/sahan-weerasiri/projects/video-gen-shortcut/src/static/index.html) allowing single-click switching between `Auto Fallback`, `Direct API`, and `Selenium`.
   - Updated [`app.js`](file:///home/sahan-weerasiri/projects/video-gen-shortcut/src/static/js/app.js) to attach engine selections to task requests and render real-time fallback badges and logs when auto-recovery occurs.

3. **Parity in Browser Automation Engine (`src/gen_selenium.py`)**:
   - Added [`generate_text_to_video`](file:///home/sahan-weerasiri/projects/video-gen-shortcut/src/gen_selenium.py) alongside [`generate_image_to_video`](file:///home/sahan-weerasiri/projects/video-gen-shortcut/src/gen_selenium.py).
   - Added `progress_callback` telemetry so browser automation steps (navigation, prompt injection, render wait, and download) stream live progress bars to the frontend.

## Alternatives Considered

### Alternative 1: VPN or Proxy Rotation
- **Evaluated**: Rotating IP addresses via commercial VPNs/proxies to reset anonymous IP ZeroGPU quotas.
- **Why rejected**: LTX-Video generation requires persistent, long-lived SSE connections (30–120s); network switches break the socket. Furthermore, commercial VPN/datacenter IP ranges are heavily flagged by Cloudflare Turnstile on Hugging Face and violate service Acceptable Use Policies.

### Alternative 2: Fail Hard with Quota Warning Only
- **Evaluated**: Simply reporting the ZeroGPU quota error in the UI and asking the user to wait or provide an `HF_TOKEN`.
- **Why rejected**: Provides poor user experience when an existing, functional browser-based engine is already available in the repository.

## Consequences

### Positive
- **Fault-Tolerant Video Generation**: Jobs do not fail when community GPU quotas are exhausted; the system automatically recovers via Selenium.
- **User Control**: Users can manually force either engine or rely on automatic failover.
- **Dual Mode Parity**: Both Text-to-Video and Image-to-Video are supported across both Direct and Selenium paths.
- **Transparent Feedback**: The UI clearly displays which engine generated each video (`[direct]`, `[selenium]`, or `[selenium_fallback]`).

### Negative
- **Fallback Latency**: When falling back, the initial direct attempt takes ~1–3s before triggering browser launch, resulting in slightly longer total generation time than a direct Selenium run.
