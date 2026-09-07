# Solution AI

A JARVIS-style personal AI agent (desktop application for Windows).

**Status: Phase 1 — Foundation.** This gets Electron, React, TypeScript,
FastAPI, PostgreSQL, and a WebSocket talking to each other, plus a real
(non-mocked) chat path through Anthropic's Claude. Voice, computer control,
vision, memory, and the rest of the roadmap come in later phases — see
`docs/ARCHITECTURE.md`.

---

## 1. Install prerequisites (Windows 10/11)

You said none of these are installed yet, so here's the full path.

### 1.1 Node.js
1. Go to https://nodejs.org and download the **LTS** installer for Windows.
2. Run it, accepting the defaults (this also installs `npm`).
3. Verify — open **PowerShell** and run:
   ```powershell
   node --version
   npm --version
   ```

### 1.2 Python
1. Go to https://www.python.org/downloads/ and download **Python 3.11 or 3.12** (avoid 3.13 until library support catches up).
2. Run the installer. **Check "Add python.exe to PATH"** on the first screen — easy to miss.
3. Verify:
   ```powershell
   python --version
   pip --version
   ```

### 1.3 PostgreSQL (with pgvector)
You have two options — pick one.

**Option A — Docker Desktop (recommended, simplest):**
1. Install Docker Desktop for Windows: https://www.docker.com/products/docker-desktop/
2. From the repo root, run:
   ```powershell
   docker compose up -d
   ```
   This starts PostgreSQL 16 with the `pgvector` extension already built in, on `localhost:5432`, with the credentials already matching `.env.example`.

**Option B — Native PostgreSQL install:**
1. Install PostgreSQL from https://www.postgresql.org/download/windows/ (the installer includes pgAdmin).
2. During setup, set a password for the `postgres` superuser and remember it.
3. Create the database and user (via `psql` or pgAdmin's Query Tool):
   ```sql
   CREATE USER solution_ai WITH PASSWORD 'changeme';
   CREATE DATABASE solution_ai OWNER solution_ai;
   ```
4. Install the `pgvector` extension for your PostgreSQL version — follow https://github.com/pgvector/pgvector#windows. This step is the main reason Option A is easier.
5. Run `scripts/init_db.sql` against the `solution_ai` database.

---

## 2. Clone / unzip the project

Unzip `solution-ai.zip` somewhere convenient, e.g. `C:\Users\<you>\solution-ai`, and open PowerShell there for every command below.

---

## 3. Configure environment variables

```powershell
copy .env.example .env
```

Open `.env` in any text editor and fill in:
- `ANTHROPIC_API_KEY` — get one at https://console.anthropic.com/settings/keys
- If you used **Option B** above with a different password, update `DATABASE_URL` to match.
- `SECRET_KEY` — generate one:
  ```powershell
  python -c "import secrets; print(secrets.token_hex(32))"
  ```

**Never commit `.env`** — it's already in `.gitignore`.

---

## 4. Backend setup

```powershell
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Initialize the database (creates all tables + the pgvector extension):
```powershell
python -m backend.database.init_db
```

Run the smoke tests (these don't need a real API key or a live DB connection beyond what init_db just created):
```powershell
pytest tests/test_health.py -v
```

Start the backend:
```powershell
uvicorn backend.main:app --reload --port 8000
```

Confirm it's alive by opening http://127.0.0.1:8000/api/system/status in a browser — you should see `"status": "ok"` and `"database": {"connected": true}`. If `ai_provider` calls fail later, it'll show up as a 502 from `/api/chat`, not here — this endpoint only checks the database.

---

## 5. Frontend setup

Open a **second** PowerShell window (keep the backend running in the first):

```powershell
cd frontend
npm install
npm run dev
```

This starts Vite on http://localhost:5173. Open that URL in a browser first — you should see the Solution AI chat UI and be able to send a message and get a real Claude response streamed back over the WebSocket. **This is the Phase 1 acceptance test** — do this before moving to Electron.

---

## 6. Desktop (Electron) setup

Open a **third** PowerShell window:

```powershell
npm install
npx tsc -p desktop/electron/tsconfig.json
npm run dev:electron
```

This compiles `main.ts`/`preload.ts` to JS and launches the actual desktop window, pointed at the Vite dev server from step 5.

---

## 7. What to test right now (Phase 1 acceptance)

1. `/api/system/status` returns `"status": "ok"`.
2. In the browser at `localhost:5173`, typing a message and pressing Enter gets a real, streamed Claude response — not a placeholder.
3. Closing and reopening the browser tab, then asking "what did I just say?" — conversation history should persist (it's in Postgres).
4. The Electron window shows the same working chat.

**If any of these fail:** copy the exact error (terminal output, browser console, or network tab) back to me and I'll fix the actual cause — per your spec's section 44, nothing gets papered over with a mock.

---

## 8. Setup notes for later phases (voice, computer control, memory)

These are already coded and registered — nothing more to build — but a few
dependencies need Windows-specific attention the first time you install them:

- **Voice (Phase 3):** `faster-whisper` downloads its model (~150MB for
  "base") on first use; `edge-tts` needs no setup. Wake-word detection
  (`openwakeword`) only ships pretrained phrases — see
  `docs/ARCHITECTURE.md` for what that means for "Hey Solution" specifically.
- **Computer control (Phase 4):** `pyautogui` needs no special setup on
  Windows. `pycaw` (volume control) sometimes needs Visual C++ Redistributable
  installed — if `pip install pycaw` or a volume-control call fails, install
  the latest from https://aka.ms/vs/17/release/vc_redist.x64.exe.
- **Memory (Phase 7):** first call to `memory.remember_information` downloads
  a ~90MB sentence-transformers model. No API key needed by default.
- **Filesystem/terminal tools:** do nothing until you set `ALLOWED_FOLDERS`
  in `.env` to at least one real path — this is intentional (spec section
  30: nothing is allowed by default).
- **MCP servers (Phase 10):** most MCP servers are `npx`-launched Node
  packages — you'll need Node installed (already covered in step 1.1) and
  the specific server's package name in `MCP_SERVERS` in `.env`.

## 9. Building the Windows installer (Phase 11 — untested, expect iteration)

```powershell
pip install pyinstaller
cd backend
pyinstaller --onefile --name solution-ai-backend --paths . main.py
cd ..
npm run build:frontend
npm run build:electron
npx electron-builder
```

The output installer lands in `release/`. This has never been run end-to-end
— PyInstaller commonly needs `--hidden-import` flags added for packages like
`mss`, `pyaudio`, or `sentence-transformers` that use dynamic imports it
can't detect automatically. **Send me the exact error** from whichever step
fails first.

## 10. Project structure

```
solution-ai/
├── desktop/electron/     Electron main process + preload bridge
├── frontend/             React + TypeScript + Vite + Tailwind UI
├── backend/
│   ├── core/             config.py (all settings), logging.py
│   ├── ai/               AIProvider abstraction + AnthropicProvider
│   ├── agents/            AgentOrchestrator (tool-calling loop)
│   ├── voice/             TTS/STT abstractions + providers, wake word
│   ├── vision/            Screen capture + vision service
│   ├── memory/            pgvector memory service + embeddings
│   ├── tasks/             TaskManager (background/retryable tasks)
│   ├── scheduler/         APScheduler-based recurring tasks
│   ├── mcp/               MCP client (external tool servers)
│   ├── security/          Permission levels + confirmation system
│   ├── database/         SQLAlchemy models + session + init script
│   ├── api/              REST routes + WebSocket
│   ├── schemas/          Pydantic request/response models
│   ├── tools/            All Tool implementations + ToolRegistry
│   └── tests/
├── scripts/              SQL/setup helpers
├── docs/                 Architecture notes
├── docker-compose.yml    Optional Postgres+pgvector via Docker
└── .env.example
```

## 11. Roadmap

See `docs/ARCHITECTURE.md` for full phase status and honest limitations —
every phase from the spec now has real code, but voice is push-to-talk (not
continuous listening) and packaging has never been run end-to-end. That doc
also lists the recommended order for testing what's here.

## 12. Security notes

- API keys live only in `.env`, read only by the backend. The frontend never sees them.
- `backend/core/logging.py` redacts any field named like a secret before writing to `logs/`.
- Filesystem, terminal, and computer-control tools are gated by `ALLOWED_FOLDERS` and the
  SENSITIVE/DANGEROUS confirmation system (`backend/security/permissions.py`) — nothing
  destructive executes without you clicking "Allow" in the confirmation dialog.
- MCP server tools default to SENSITIVE permission regardless of what the server claims,
  since an external MCP server runs code you didn't write.
