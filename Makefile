.PHONY: backend frontend test lint clean install

# ── Backend ──────────────────────────────────────────────────────

.PHONY: backend-install backend

backend-install:
	cd backend && python -m venv venv && \
		. venv/bin/activate && \
		pip install -r requirements.txt

backend:
	cd backend && . venv/bin/activate && \
		uvicorn app.main:app --reload

# ── Frontend ─────────────────────────────────────────────────────

.PHONY: frontend-install frontend

frontend-install:
	cd frontend && npm install

frontend:
	cd frontend && npm run dev

# ── Tests ────────────────────────────────────────────────────────

.PHONY: test test-watch

test:
	cd backend && . venv/bin/activate && \
		python -m pytest tests/ -v

test-watch:
	cd backend && . venv/bin/activate && \
		python -m pytest tests/ -v --force-reload

# ── Lint / Format ────────────────────────────────────────────────

.PHONY: lint lint-fix

lint:
	cd backend && . venv/bin/activate && \
		ruff check app/ tests/ && \
		ruff format --check app/ tests/
	cd frontend && npm run lint

lint-fix:
	cd backend && . venv/bin/activate && \
		ruff check --fix app/ tests/ && \
		ruff format app/ tests/

# ── Cleanup ──────────────────────────────────────────────────────

.PHONY: clean

clean:
	cd backend && rm -rf venv __pycache__ .pytest_cache
	cd frontend && rm -rf node_modules dist
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

# ── Install all ──────────────────────────────────────────────────

install: backend-install frontend-install
	@echo "✓ All dependencies installed"
