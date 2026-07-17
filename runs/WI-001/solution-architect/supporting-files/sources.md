# External technical sources

Checked on 2026-07-16.

1. OpenAI, [Text generation](https://developers.openai.com/api/docs/guides/text)
   - Supports using the Responses API for direct text generation.
   - LittleDuck inference: keep this dependency behind a provider adapter so the public application contract is supplier-independent.

2. OpenAI, [Streaming API responses](https://developers.openai.com/api/docs/guides/streaming-responses)
   - Documents `stream: true`, SSE transport, typed semantic events, text deltas, completion and errors.
   - LittleDuck inference: translate provider events to a smaller, persistent `generation.*` event contract with explicit stop and replay semantics.

3. OpenAI, [Production best practices](https://developers.openai.com/api/docs/guides/production-best-practices)
   - Advises against exposing API Keys in code or public repositories and recommends environment variables or secret management.
   - LittleDuck application: API Key is server-only, encrypted at rest, and injected with a separate encryption key/secret.

No model ID is fixed by this architecture. The administrator-provided non-empty model string is the effective model, consistent with PRD V1.7.
