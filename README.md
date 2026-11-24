# AI Procurement & Vendor Manager

> Open-source, self-hosted AI procurement and vendor management platform for supplier contract comparison, pricing benchmarks, PO validation, and renewal tracking.

**Roadmap Stage:** Phase 2 — Administrative, Quality & Specialized Additions · **Status:** Full-Stack MVP Implemented

## Implemented Core Capabilities

- **Contract Comparison (`backend/app/contracts/`):** Automated MSA/DPA/Order Form ingestion, 8-family commercial playbook diffing (auto-renewal windows, price uplift caps, liability caps, payment terms, termination for convenience, DPA/breach notice, indemnification, SLA uptime), side-by-side contract comparison, and legal/procurement HITL escalation.
- **Pricing Benchmarks (`backend/app/benchmarks/`):** Normalized SKU & SaaS seat historical rate store with P25/median/P75 percentiles, quote variance & uplift analysis, annual savings estimation, and counter-offer guidance.
- **PO Validation (`backend/app/purchasing/`):** Automated quote-to-PO line-item reconciliation, arithmetic validation, cost-center budget headroom verification, benchmark unit-price sanity checks, and tiered approval routing (`procurement_manager` -> `finance_director` -> `vp_finance`).
- **Renewal Tracking (`backend/app/renewals/`):** Notice-deadline urgency tracking (`overdue`, `critical`, `upcoming`, `healthy`), cross-module AI renegotiation brief synthesis, copyable draft notices, and HITL-gated outbound notice approval.
- **Governance & Guardrails (`backend/app/core/`):** Local-first LLM router (`mock` / `ollama` / `gemini`) with automatic fallback, regex-based cloud PII redaction (`LLM_REDACT_PII_FOR_CLOUD=true`), explicit HITL approval gates, and a tamper-evident SHA-256 hash-chained `audit_logs` ledger.

## Architecture & Engineering Standards

- **Backend (`backend/`):** Python 3.12+, FastAPI, async SQLAlchemy 2.0 (`aiosqlite` for local dev/CI, `asyncpg` via `[postgres]` extra in Docker), Pydantic v2 settings with production fail-fast validation, pure ASGI security-header middleware, and `/api/v1/health` + `/ready` probes.
- **Frontend (`frontend/`):** React 18, TypeScript, Vite, Tailwind CSS, and Vitest + Testing Library workspace spanning Overview, Contracts, Pricing Benchmarks, PO Validation, Renewals, and Approvals & Audit views, served behind unprivileged Nginx in production.
- **Demo Seeding:** On startup in non-production environments (`AUTO_SEED_DEMO_DATA=true` and `APP_ENV!=production`), the API idempotently seeds 5 vendors, 8 playbook rules, 3 analyzed contracts, 12 pricing benchmarks, 4 cost-center budgets, 3 quotes, 3 POs, 4 renewal records, and 2 pending HITL approvals. `POST /api/v1/seed` is disabled (`403`) in production.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the domain module and endpoint blueprint.

## Quickstart

### Backend (Local Dev & Tests)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

Verify lint, types, and tests:

```bash
ruff check app tests
mypy app
pytest -v
```

### Frontend (Local Dev & Tests)

```bash
cd frontend
npm ci
npm run dev
```

Verify typecheck, unit tests, and production bundle:

```bash
npx tsc --noEmit
npm run test
npm run build
```

### Docker Compose

```bash
docker compose up --build
```

- Frontend UI: `http://localhost:3000`
- Backend API & OpenAPI Docs: `http://localhost:8000/docs`

---

## License

Licensed under the [MIT License](LICENSE).
