# Decision Support Agent System

A multi-agent AI debate system that helps users make better decisions. Four AI agents debate a user's decision topic, then a judge delivers a balanced verdict.

**Built for:** A university project / proposal demo — not for production use.

## Architecture

```
User Topic → Moderator opens debate
           → Pro Agent (argues FOR)
           → Con Agent (argues AGAINST)
           → Repeat for 3 rounds
           → Judge summarises & recommends
```

- **Backend**: FastAPI (Python) — layered architecture with clean domain models
- **Frontend**: React + Vite + TypeScript
- **LLM**: OpenAI-compatible (OpenAI, DeepSeek, etc.) via a single `LLMService` wrapper
- **Persistence**: In-memory (swappable via repository ABC)
- **Demo Mode**: Built-in simulated responses — runs fully offline with no API key

## Quick Start (Demo Mode — No API Key Required)

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # DEMO_MODE=true is already the default
uvicorn app.main:app --reload # → http://localhost:8000

# 2. Frontend (separate terminal)
cd frontend
npm install
npm run dev                   # → http://localhost:5173

# 3. Open http://localhost:5173 and enter a decision topic
```

The debate will complete in about 2 seconds with realistic simulated arguments from all four agents.

## Setup with a Real LLM

### 1. Environment

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Configure `.env`

| Variable | Default | Description |
|----------|---------|-------------|
| `DEMO_MODE` | `true` | `false` to make real API calls |
| `LLM_PROVIDER` | `openai` | Informational only |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | Use `https://api.deepseek.com` for DeepSeek |
| `LLM_API_KEY` | (empty) | Your API key |
| `LLM_MODEL` | `gpt-4o-mini` | Model name for your provider |
| `LLM_MAX_TOKENS` | `1024` | Max tokens per response |
| `LLM_TEMPERATURE` | `0.7` | 0.0–2.0 |
| `DEBATE_MAX_ROUNDS` | `3` | Number of debate rounds |

### 3. Run

```bash
# Terminal 1 — FastAPI
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload

# Terminal 2 — Vite
cd frontend && npm run dev
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/debates/` | Create a new debate |
| `GET` | `/api/debates/{id}` | Get debate state |
| `POST` | `/api/debates/{id}/start` | Start debate pipeline |
| `GET` | `/api/debates/{id}/rounds/{n}` | Get a specific round |
| `GET` | `/health` | Health check |

### Demo Flow (curl)

```bash
# 1. Create a debate
curl -X POST http://localhost:8000/api/debates/ \
  -H "Content-Type: application/json" \
  -d '{"topic": "Should I learn Rust?"}'

# 2. Start it (returns immediately with IN_PROGRESS)
curl -X POST http://localhost:8000/api/debates/{id}/start

# 3. Poll for results
curl http://localhost:8000/api/debates/{id}
```

## Project Structure

```
backend/
├── app/
│   ├── api/              # FastAPI routers & Pydantic schemas
│   ├── domain/           # Pure domain models (no framework deps)
│   ├── agents/           # AI agent implementations
│   │   ├── base.py       # BaseAgent ABC
│   │   ├── pro_agent.py  # FOR side
│   │   ├── con_agent.py  # AGAINST side
│   │   ├── moderator.py  # Neutral steer
│   │   ├── judge.py      # Final verdict
│   │   └── registry.py   # Auto-registration decorator
│   ├── services/         # Business logic (DebateService, LLMService)
│   ├── storage/          # In-memory repository (swappable ABC)
│   └── main.py           # App factory with logging config
├── tests/                # 187+ tests (pytest)
├── requirements.txt
├── .env.example
└── pyproject.toml

frontend/
├── src/
│   ├── pages/            # HomePage, DebatePage
│   ├── components/       # TopicForm, DebateRound, AgentMessage, etc.
│   ├── hooks/            # useDebate, usePolling
│   ├── services/         # API client
│   └── types/            # TypeScript interfaces
└── package.json
```

## Demo Script (for the Proposal)

The demo runs entirely offline with `DEMO_MODE=true`. Follow these steps:

1. **Start both servers** (instructions above)
2. **Open the app** at http://localhost:5173
3. **Enter a topic** — suggested topics:
   - "Should I pursue graduate school?"
   - "Should I learn Rust in 2026?"
   - "Should I switch to a remote-first job?"
   - "Should I invest in cryptocurrency?"
   - "Should I start my own business?"
4. **Click "Start Debate"**
5. **Watch the debate unfold** — each round loads progressively via polling (~1.5s intervals)
6. **The verdict appears** after 3 rounds with a recommendation

### What to Highlight

- **Architecture**: Clean domain layer with zero framework imports, decorator-based agent registry, repository pattern
- **Demo Mode**: No API key needed, runs fully offline with realistic responses
- **Frontend**: Progressive loading with skeleton states, error boundaries, chat-style UI
- **Test Coverage**: 187 tests covering domain, API, services, agents, storage, and demo mode
- **Extensibility**: Adding a new agent requires only one file (implement `BaseAgent` + `@AgentRegistry.register`)

## Extending

### Add a new agent

```python
# backend/app/agents/critic_agent.py
from app.agents.base import BaseAgent
from app.agents.registry import AgentRegistry

@AgentRegistry.register("critic")
class CriticAgent(BaseAgent):
    SYSTEM_PROMPT = "You are a critical reviewer..."
    def build_prompt(self, context): ...
```

No other files need changing — the registry discovers it automatically.

### Swap storage

Implement `DebateRepository` (PostgreSQL, Redis, etc.) and inject it into `DebateService`.

## Testing

```bash
cd backend && source .venv/bin/activate
python -m pytest tests/ -v     # 187 tests
ruff check app/ tests/          # lint
```

## Common Commands

```bash
make backend         # Install deps + run uvicorn
make frontend        # Install deps + run vite
make test            # Run all backend tests
make lint            # Ruff + TypeScript checks
make clean           # Remove venv, node_modules, caches
```

## License

University project — educational use.
