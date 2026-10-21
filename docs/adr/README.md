# Architecture Decision Records (ADRs)

Architecture Decision Records (ADRs) capture key technical and architectural decisions made across the lifecycle of the **video-gen-shortcut** project.

## Index of Decisions

| ADR | Title | Status | Date |
|:---:|:------|:------:|:----:|
| [ADR-0001](0001-direct-http-sse-over-browser-automation.md) | Direct HTTP and SSE API Automation Over Browser Scraping | `accepted` | 2026-10-21 |
| [ADR-0002](0002-client-side-session-hash-generation.md) | Client-Side Session Hash Generation Scheme | `accepted` | 2026-10-21 |
| [ADR-0003](0003-cloudflare-challenge-bypass-via-direct-space-api.md) | Cloudflare Challenge Bypass via Direct Space API Architecture | `accepted` | 2026-10-21 |
| [ADR-0004](0004-dual-engine-architecture-api-and-selenium-fallback.md) | Dual-Engine Architecture (Direct API Primary with SeleniumBase UC Fallback) | `accepted` | 2026-10-21 |
| [ADR-0005](0005-gui-service-architecture-and-configuration.md) | GUI Service Architecture and Environment Configuration | `accepted` | 2026-10-21 |

---

## How to Add a New ADR

1. Duplicate the template format: [`docs/adr/template.md`](template.md).
2. Save as `docs/adr/NNNN-decision-title.md` (incrementing the 4-digit number).
3. Follow the standard sections:
   - **Context:** The problem or design decision we faced.
   - **Decision:** The chosen path and rationale.
   - **Alternatives Considered:** Options analyzed and evaluated.
   - **Consequences:** Positive, negative trade-offs, and risks.
4. Add the entry to the index table above.
