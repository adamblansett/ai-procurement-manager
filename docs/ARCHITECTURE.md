# AI Procurement & Vendor Manager — Architecture Blueprint

## Overview

Open-source, self-hosted AI procurement and vendor management platform for supplier contract comparison, pricing benchmarks, PO validation, and renewal tracking.

## Domain Modules (`backend/app/`)

- `core/` — Typed Pydantic settings (`config.py`), async SQLAlchemy 2.0 engine/session factory (`database.py`), outbound cloud PII scrubber (`pii.py`), local-first fallback LLM router (`llm.py`), shared models (`Vendor`, `ApprovalRequest`, `AuditLog`), SHA-256 hash-chained governance primitives (`governance.py`), and idempotent demo seeder (`seed.py`).
- `contracts/` — Vendor MSA/DPA/Order Form ingestion, `PlaybookRule` management, 8-family clause extraction & deviation scoring, side-by-side contract pair comparison, and HITL approval requests.
- `benchmarks/` — Normalized `PricingBenchmark` store, per-SKU percentile summaries (`min`, `p25`, `median`, `p75`, `max`), and quote variance / uplift / savings analysis.
- `purchasing/` — `BudgetAccount`, `VendorQuote`, and `PurchaseOrder` validation engine verifying line arithmetic, quote reconciliation, cost-center budget headroom, benchmark outlier checks, and tiered approval escalation.
- `renewals/` — `RenewalItem` calendar tracking notice deadlines relative to renewal dates, urgency classification, cross-module renegotiation dossier synthesis, and HITL approval requests for outbound notices.

## API v1 Endpoint Inventory (`/api/v1`)

- **Health & Overview:** `GET /health`, `GET /health/live`, `GET /health/ready`, `GET /dashboard/summary`, `POST /seed` (disabled in production)
- **Vendors:** `GET /vendors`, `POST /vendors`, `GET /vendors/{vendor_id}`, `PATCH /vendors/{vendor_id}`
- **Contracts:** `GET /contracts/playbooks`, `POST /contracts/playbooks`, `GET /contracts`, `POST /contracts`, `GET /contracts/{contract_id}`, `POST /contracts/{contract_id}/compare`, `POST /contracts/compare-pair`, `POST /contracts/{contract_id}/request-approval`
- **Benchmarks:** `GET /benchmarks`, `POST /benchmarks`, `GET /benchmarks/summary`, `POST /benchmarks/analyze`
- **Purchasing:** `GET /purchasing/budgets`, `POST /purchasing/budgets`, `GET /purchasing/quotes`, `POST /purchasing/quotes`, `GET /purchasing/orders`, `POST /purchasing/orders`, `GET /purchasing/orders/{po_id}`, `POST /purchasing/orders/{po_id}/validate`, `POST /purchasing/orders/{po_id}/submit`
- **Renewals:** `GET /renewals`, `POST /renewals`, `GET /renewals/{renewal_id}`, `PATCH /renewals/{renewal_id}`, `POST /renewals/{renewal_id}/generate-brief`, `POST /renewals/{renewal_id}/request-action`
- **Governance:** `GET /governance/approvals`, `POST /governance/approvals/{approval_id}/decide`, `GET /governance/audit-logs`, `GET /governance/audit-logs/verify`

## Security & Operational Invariants

1. **Fail-Fast Production Validation:** `validate_production_security()` refuses startup in `APP_ENV=production` if default dev secrets or wildcard CORS origins remain active.
2. **Cloud PII Redaction:** Outbound cloud LLM adapters (`gemini`) run deterministic PII scrubbing (`redact_pii`) on system and user prompts when `LLM_REDACT_PII_FOR_CLOUD=true`.
3. **Human-in-the-Loop Approvals:** High-impact actions (PO approvals committing budget, contract sign-off waivers, outbound non-renewal notices) create `ApprovalRequest` records and require explicit `approved` / `rejected` decisions before mutating target state.
4. **Tamper-Evident Audit Trail:** Every state change appends an `AuditLog` record linked via SHA-256 `prev_hash` -> `entry_hash`; integrity can be verified anytime via `GET /api/v1/governance/audit-logs/verify`.
5. **Non-Root Containers:** Both the FastAPI API image and Nginx frontend image run as non-root users with `/api/v1/health/live` and `/api/v1/health/ready` probes.
