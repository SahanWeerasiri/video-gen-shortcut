# ADR-0005: GUI Service Architecture and Environment Configuration

**Date**: 2026-10-21
**Status**: accepted
**Deciders**: Sahan Weerasiri, Antigravity Agent

## Context

The user requested a Graphical User Interface (GUI) in addition to the CLI tool to allow visual interaction, real-time video playback, prompt parameter tuning, and image file uploading.

A web GUI service introduces operational concerns:
- Network binding (host, port) to avoid conflicts on developer machines or containerized hosts.
- Storage paths for uploaded source images and generated output videos.
- Dynamic configuration of the backend Hugging Face Space endpoint and optional authentication tokens.
- Separation of development vs. production settings.

## Decision

We decided to adopt a **12-Factor App Environment Configuration strategy** centered around `.env` (templated by `.env.example`).

The configuration covers:
1. **Server & GUI Networking**:
   - `GUI_HOST`: Default `0.0.0.0` (accessible across local network or container bridges).
   - `GUI_PORT`: Default `7860` (standard for Gradio / AI interfaces) or `8080`.
   - `APP_ENV`: `development` | `production`.
   - `DEBUG`: Boolean flag controlling verbose logging and auto-reloading.
2. **Backend Engine Target**:
   - `LTX_BACKEND_URL`: Target Hugging Face Space endpoint (`https://lightricks-ltx-video-distilled.hf.space`).
   - `HF_TOKEN`: Optional Hugging Face User Access Token for higher rate limits or private space forks.
3. **Model & Generation Defaults**:
   - `DEFAULT_DURATION`: 2.0s
   - `DEFAULT_WIDTH`: 704
   - `DEFAULT_HEIGHT`: 512
   - `DEFAULT_GUIDANCE_SCALE`: 1.0
   - `DEFAULT_IMPROVE_TEXTURE`: true
   - `DEFAULT_NEGATIVE_PROMPT`: Standard negative prompt to suppress artifacts.
4. **Storage & File Management**:
   - `OUTPUT_DIR`: Storage destination for generated videos (defaults to `./downloaded_files`).
   - `MAX_UPLOAD_SIZE_MB`: Maximum input image size (default `50MB`).
5. **Selenium Fallback Settings**:
   - `SELENIUM_HEADLESS`: Boolean controlling headless vs headed browser execution.
   - `BROWSER_BINARY_PATH`: Path to the Chromium/Brave binary.

## Alternatives Considered

### Alternative 1: Hardcoding Server Ports and Hostnames in Code
- **Pros**: Zero initial setup.
- **Cons**: Ports conflict if multiple services run simultaneously (e.g. running alongside other AI tools on port 7860 or 3000); requires code edits to change settings.
- **Why rejected**: Violates 12-factor configuration principles and makes deployment rigid.

### Alternative 2: Passing All Parameters via CLI Flags
- **Pros**: Explicit invocation.
- **Cons**: Cumbersome for running persistent GUI services or managing background daemons (e.g. via PM2, systemd, or Docker).
- **Why rejected**: Environment variables provide cleaner integration with daemons and containers.

## Consequences

### Positive
- **Flexible Deployment**: Works out of the box locally, in Docker, or behind reverse proxies (Nginx, Caddy).
- **Safe Secrets Handling**: API tokens and private endpoints stay in `.env`, which is ignored by `.gitignore` and scanned by pre-commit hooks.
- **Unified Settings**: Shared between the CLI, GUI server, and test runners.

### Negative
- Users must copy `.env.example` to `.env` if custom ports or tokens are desired (though sane defaults are provided if `.env` is absent).
