# AI Procurement & Vendor Manager

> Open-source, self-hosted AI procurement and vendor management platform for supplier contract comparison, pricing benchmarks, PO validation, and renewal tracking.

**Roadmap Stage:** Phase 2 — Administrative, Quality & Specialized Additions · **Status:** Production-Hardened Full-Stack Platform

## Core Capabilities

- **Security, RBAC & Rate Limiting (`backend/app/core/`):** HS256 JWT authentication, PBKDF2-HMAC-SHA256 password hashing, role-scoped approval enforcement (`admin`, `vp_finance`, `finance_director`, `legal_counsel`, `procurement_manager`, `analyst`), strict **separation of duties** (blocking self-approval), per-IP sliding-window rate limiting (`429 Retry-After`), and fail-fast `AUTH_REQUIRED=true` validation in production.
- **Contract Comparison & Semantic Search (`backend/app/contracts/`):** Direct `.pdf` / `.docx` / `.txt` / `.md` contract upload and ingestion, 8-family commercial playbook diffing, side-by-side contract comparison, 384-dim semantic clause embeddings for cross-vendor precedent search (`POST /api/v1/contracts/search`), and legal/procurement HITL escalation.
- **Pricing Benchmarks (`backend/app/benchmarks/`):** Normalized SKU & SaaS seat historical rate store, bulk CSV import (`POST /api/v1/benchmarks/import-csv`), P25/median/P75 percentiles, quote variance & uplift analysis, and annual savings estimation.
- **PO Validation (`backend/app/purchasing/`):** Automated quote-to-PO line-item reconciliation, arithmetic validation, cost-center budget headroom checks + CSV upsert (`POST /api/v1/purchasing/budgets/import-csv`), benchmark outlier flags, and tiered approval routing.
- **Renewal Tracking & Alerts (`backend/app/renewals/`):** Notice-deadline urgency tracking, cross-module AI renegotiation brief synthesis, Markdown brief export, deduplicated threshold alert sweeps (`0/7/30/60/90` days with webhook dispatch), and HITL-gated outbound notice approval.
- **Governance & Observability:** Local-first LLM router (`mock` / `ollama` / `gemini`) with deterministic cloud PII scrubbing (`LLM_REDACT_PII_FOR_CLOUD=true`), tamper-evident SHA-256 hash-chained `audit_logs` with CSV/signed-JSON export, Prometheus `/api/v1/health/metrics`, and optional OpenTelemetry tracing (`OTEL_ENABLED=true`).

## Database Migrations (Alembic)

Async SQLAlchemy migrations live in `backend/alembic/` (`0001_initial_schema`). Run upgrades from `backend/`:

```bash
alembic upgrade head
```

## Demo Seeding & RBAC Personas

On startup in non-production environments (`AUTO_SEED_DEMO_DATA=true` and `APP_ENV!=production`), the API idempotently seeds 6 RBAC demo users (password `ProcurementDemo2026!`), 5 vendors, 8 playbook rules, 3 analyzed contracts with clause embeddings, 12 pricing benchmarks, 4 cost-center budgets, 3 quotes, 3 POs, 4 renewal records, initial alert dispatches, and 2 pending HITL approvals. `POST /api/v1/seed` is disabled (`403`) in production.

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
