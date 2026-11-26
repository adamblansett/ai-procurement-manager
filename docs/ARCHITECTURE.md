# AI Procurement & Vendor Manager — Architecture Blueprint

## Overview

Open-source, self-hosted AI procurement and vendor management platform for supplier contract comparison, pricing benchmarks, PO validation, and renewal tracking.

## Domain Modules (`backend/app/`)

- `core/` — Typed Pydantic settings (`config.py`), async SQLAlchemy 2.0 engine/session factory (`database.py`), PBKDF2 + HS256 JWT/RBAC (`auth.py`), document extraction for PDF/DOCX/TXT (`documents.py`), deterministic semantic embeddings (`embeddings.py`), outbound cloud PII scrubber (`pii.py`), local-first fallback LLM router (`llm.py`), ASGI security/rate-limit/observability/auth middlewares (`middleware.py`, `observability.py`), shared models (`User`, `Vendor`, `ApprovalRequest`, `AuditLog`), SHA-256 hash-chained governance primitives (`governance.py`), and idempotent demo seeder (`seed.py`).
- `contracts/` — Vendor MSA/DPA/Order Form ingestion & `.pdf`/`.docx` upload, `PlaybookRule` management, 8-family clause extraction & deviation scoring, `ContractClauseEmbedding` semantic precedent search, side-by-side comparison, and HITL approval requests.
- `benchmarks/` — Normalized `PricingBenchmark` store, CSV bulk import, per-SKU percentile summaries (`min`, `p25`, `median`, `p75`, `max`), and quote variance / uplift / savings analysis.
- `purchasing/` — `BudgetAccount` (+ CSV upsert), `VendorQuote`, and `PurchaseOrder` validation engine verifying line arithmetic, quote reconciliation, cost-center budget headroom, benchmark outlier checks, and tiered approval escalation.
- `renewals/` — `RenewalItem` calendar tracking notice deadlines, urgency classification, cross-module renegotiation dossier synthesis, Markdown export, deduplicated `RenewalAlertDispatch` threshold sweeps (`0/7/30/60/90` days + webhook delivery), and HITL approval requests for outbound notices.

## API v1 Endpoint Inventory (`/api/v1`)

- **Health & Telemetry:** `GET /health`, `GET /health/live`, `GET /health/ready`, `GET /health/metrics`, `GET /health/telemetry`, `GET /dashboard/summary`, `POST /seed` (disabled in production)
- **Auth & RBAC:** `POST /auth/register` (admin-only in production), `POST /auth/login`, `GET /auth/me`, `GET /auth/users`
- **Vendors:** `GET /vendors`, `POST /vendors`, `GET /vendors/{vendor_id}`, `PATCH /vendors/{vendor_id}`
- **Contracts:** `GET /contracts/playbooks`, `POST /contracts/playbooks`, `GET /contracts`, `POST /contracts`, `POST /contracts/upload`, `POST /contracts/search`, `POST /contracts/compare-pair`, `GET /contracts/{contract_id}`, `POST /contracts/{contract_id}/compare`, `POST /contracts/{contract_id}/request-approval`
- **Benchmarks:** `GET /benchmarks`, `POST /benchmarks`, `POST /benchmarks/import-csv`, `GET /benchmarks/summary`, `POST /benchmarks/analyze`
- **Purchasing:** `GET /purchasing/budgets`, `POST /purchasing/budgets`, `POST /purchasing/budgets/import-csv`, `GET /purchasing/quotes`, `POST /purchasing/quotes`, `GET /purchasing/orders`, `POST /purchasing/orders`, `GET /purchasing/orders/{po_id}`, `POST /purchasing/orders/{po_id}/validate`, `POST /purchasing/orders/{po_id}/submit`
- **Renewals:** `GET /renewals`, `POST /renewals`, `GET /renewals/alerts`, `POST /renewals/alerts/run`, `GET /renewals/{renewal_id}`, `PATCH /renewals/{renewal_id}`, `POST /renewals/{renewal_id}/generate-brief`, `GET /renewals/{renewal_id}/export`, `POST /renewals/{renewal_id}/request-action`
- **Governance:** `GET /governance/approvals`, `POST /governance/approvals/{approval_id}/decide`, `GET /governance/audit-logs`, `GET /governance/audit-logs/verify`, `GET /governance/audit-logs/export`

## Security & Operational Invariants

1. **Fail-Fast Production Validation:** `validate_production_security()` refuses startup in `APP_ENV=production` if default dev secrets, wildcard CORS origins, or `AUTH_REQUIRED=false` remain active.
2. **RBAC & Separation of Duties:** `POST /api/v1/governance/approvals/{id}/decide` enforces role scope (`vp_finance`, `finance_director`, `legal_counsel`, `procurement_manager`, `admin`) and blocks self-approval when requester equals decider.
3. **Cloud PII Redaction:** Outbound cloud LLM adapters (`gemini`) run deterministic PII scrubbing (`redact_pii`) on system and user prompts when `LLM_REDACT_PII_FOR_CLOUD=true`.
4. **Tamper-Evident Audit Trail:** Every state change appends an `AuditLog` record linked via SHA-256 `prev_hash` -> `entry_hash`; integrity can be verified anytime via `GET /api/v1/governance/audit-logs/verify` and exported via `GET /api/v1/governance/audit-logs/export`.
5. **Non-Root Containers:** Both the FastAPI API image and Nginx frontend image run as non-root users with `/api/v1/health/live` and `/api/v1/health/ready` probes.
