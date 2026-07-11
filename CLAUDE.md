# Decision Support Agent System

A multi-agent AI debate system that helps users make decisions.
Built with FastAPI (backend) and React + Vite + TypeScript (frontend).

## Project Structure

```
├── backend/          # FastAPI Python backend
│   ├── app/
│   │   ├── api/         # Route handlers & Pydantic schemas
│   │   ├── domain/      # Pure domain models (Debate, Round, Argument)
│   │   ├── agents/      # AI agents (Pro, Con, Moderator, Judge)
│   │   ├── services/    # Business logic (DebateService, LLMService)
│   │   └── storage/     # Persistence (InMemoryDebateRepository)
│   └── tests/
├── frontend/         # React + Vite + TypeScript frontend
│   └── src/
│       ├── pages/       # HomePage, DebatePage
│       ├── components/  # TopicForm, DebateRound, AgentMessage, etc.
│       ├── hooks/       # useDebate, usePolling
│       ├── services/    # API client
│       └── types/       # TypeScript interfaces
└── CLAUDE.md
```

## Architecture

- **Layered**: API → Services → Agents + Storage → Domain
- **Auto-registering agents**: Decorator-based registry — new agents add `@AgentRegistry.register("name")`
- **4 agents**: Pro (FOR), Con (AGAINST), Moderator (steers), Judge (verdict)
- **3 rounds per debate** — configurable via `DEBATE_MAX_ROUNDS`
- **REST + polling** — frontend polls every 1.5s while debate is in progress
- **Clean domain layer** — zero framework imports in `app/domain/`

## Common Commands

```bash
# Backend
make backend         # Install deps + run uvicorn

# Frontend
make frontend        # Install deps + run vite dev server

# Tests
make test            # Run all backend tests

# Lint
make lint            # Run ruff on backend + tsc on frontend
```

## Adding a New Agent

1. Create `backend/app/agents/your_agent.py`
2. Subclass `BaseAgent` and set `SYSTEM_PROMPT`
3. Decorate with `@AgentRegistry.register("your_role")`
4. Implement `build_prompt(context) -> str`

No other files need changing.

## Design Rules

- **Domain has zero imports** from FastAPI, LLM SDKs, or HTTP libraries.
- **Agents talk only through `LLMService`** — never call an API directly.
- **Repositories implement an ABC** — swap implementations without touching services.
- **Frontend `types/debate.ts`** mirrors `backend/app/api/schemas.py`.
