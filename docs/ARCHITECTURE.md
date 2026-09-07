# Solution AI — Architecture & Roadmap

## Design principles (from spec)
- Tool-based, not hard-coded commands: the AI is given tool *definitions*
  (`backend/ai/base.py::ToolDefinition`) via the `ToolRegistry`
  (`backend/tools/registry.py`) and decides which to call — nothing is a
  hard-coded if/else on user phrasing.
- `AIProvider` abstraction (`backend/ai/base.py`) — no code outside
  `backend/ai/` may import a vendor SDK directly. Same pattern repeated for
  `TTSProvider`/`STTProvider` (`backend/voice/`) and `EmbeddingProvider`
  (`backend/memory/embeddings.py`). Switching a provider in `.env` never
  requires an application code change.
- Every tool has a `PermissionLevel` (SAFE / LOW_RISK / SENSITIVE /
  DANGEROUS), enforced centrally in `ToolRegistry.execute()` — a tool cannot
  bypass confirmation by being written carelessly, because the check happens
  outside the tool's own code.
- No fake functionality: a feature is only reported as done once it has
  actually been implemented and verified — by you, on your machine, for
  anything requiring a display/mic/network/Postgres this sandbox can't
  provide. See "What hasn't been tested" below.

## Phase status

| Phase | Contents | Status |
|---|---|---|
| 1. Foundation | Electron, React, TS, FastAPI, PostgreSQL, WebSocket wired together | Built |
| 2. AI | AIProvider abstraction + Anthropic implementation, chat, streaming, conversation history | Built (Anthropic only) |
| 2b. AI (tool calling) | AgentOrchestrator, ToolRegistry, permission/confirmation system | Built |
| 3. Voice | STT (local Whisper default), TTS (Edge TTS default), wake-word scaffold, /api/voice | Built — push-to-talk only, see note below |
| 4. Computer Control | Mouse/keyboard/window/app control, system control (volume/lock/shutdown), notifications | Built |
| 5. Vision | Screen/window/region capture, Claude vision integration | Built |
| 6. Web | search_web (DuckDuckGo/Brave), open_url, read_webpage, find_on_page | Built |
| 7. Memory | pgvector semantic search, remember/search tools, pluggable embeddings | Built |
| 8. Coding Agent | Filesystem + terminal tools with sandboxing/dangerous-command detection | Built (tools only) |
| 9. Autonomous Agent | TaskManager with retries, background execution, APScheduler recurring tasks | Built |
| 10. MCP | MCP client (stdio), tool discovery/registration into the same registry | Built |
| 11. Packaging | electron-builder + PyInstaller config for a Windows installer | Built (config only — never run) |

All phases now have real, non-mocked code. What's left is what could only
ever happen on your machine: installing dependencies, running it, and
telling me what actually breaks.

## Important limitations to know about, honestly

- Voice is push-to-talk, not continuous listening yet. POST /api/voice takes
  one recorded clip and returns a response; there's no persistent mic
  stream, wake-word gating on live audio, or barge-in/interrupt handling
  wired end-to-end yet. backend/voice/wake_word.py and ALWAYS_LISTENING
  exist for that follow-up but aren't connected to anything yet.
- The wake word is not literally "Hey Solution." openwakeword only ships
  pretrained models for a few fixed phrases; the closest available is
  "hey_jarvis". An exact custom "Hey Solution" model needs training with
  openWakeWord's provided notebook — not done here.
- Packaging has never been run. No Node/electron-builder/PyInstaller in this
  sandbox. The npm run dist pipeline follows documented electron-
  builder/PyInstaller patterns, but the first time it actually runs will be
  on your machine, and will likely need iteration (icon paths, PyInstaller
  hidden-import issues with packages like mss/pyaudio are common).
- MCP client is untested against a live server — no MCP server was
  available to connect to here.
- Voice/vision/computer-control tools have never executed — no display, mic,
  or speakers in this sandbox. Syntax and import structure were checked;
  actual runtime behavior is unverified.

## Why some things were built the way they were

- Anthropic-only for now. OpenAI/Gemini raise a clear NotImplementedError in
  provider_factory.py pointing at the pattern to copy.
- DuckDuckGo scraping as the no-key web search default, upgrading
  automatically to Brave's API if BRAVE_API_KEY is set.
- Local embeddings (sentence-transformers) as the memory default so memory
  works without any API key, switchable via EMBEDDING_PROVIDER=openai.
- MCP tools default to SENSITIVE permission, not whatever the server claims.

## Suggested next real-world steps, in order

1. Run README.md's Phase 1 acceptance test (chat works end to end).
2. Try a few tool-calling requests ("what's my CPU usage", "search the web
   for X") and confirm the confirmation dialog appears for SENSITIVE actions
   and blocks execution until you click Allow.
3. Try /api/voice with a recorded WAV clip (push-to-talk, not wake word).
4. Attempt npm run dist and report the exact first error — packaging is the
   phase most likely to need real back-and-forth.
