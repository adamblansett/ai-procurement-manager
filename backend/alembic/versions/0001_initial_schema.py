"""Initial full procurement schema across all domain modules.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-11-26 07:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=180), nullable=False),
        sa.Column("full_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=48), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_index("ix_users_role", "users", ["role"], unique=False)

    op.create_table(
        "vendors",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("primary_contact_name", sa.String(length=120), nullable=False),
        sa.Column("primary_contact_email", sa.String(length=180), nullable=False),
        sa.Column("annual_spend", sa.Float(), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("payment_terms_days", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_vendors_category", "vendors", ["category"], unique=False)
    op.create_index("ix_vendors_name", "vendors", ["name"], unique=True)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=48), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=220), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("required_role", sa.String(length=48), nullable=False),
        sa.Column("amount_impact", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("requested_by", sa.String(length=120), nullable=False),
        sa.Column("decided_by", sa.String(length=120), nullable=True),
        sa.Column("decision_notes", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_approval_requests_entity_id", "approval_requests", ["entity_id"])
    op.create_index("ix_approval_requests_entity_type", "approval_requests", ["entity_type"])
    op.create_index("ix_approval_requests_required_role", "approval_requests", ["required_role"])
    op.create_index("ix_approval_requests_status", "approval_requests", ["status"])

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("sequence_num", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=48), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entry_hash"),
        sa.UniqueConstraint("sequence_num"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_sequence_num", "audit_logs", ["sequence_num"], unique=True)

    op.create_table(
        "playbook_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("clause_type", sa.String(length=64), nullable=False),
        sa.Column("preferred_position", sa.Text(), nullable=False),
        sa.Column("fallback_position", sa.Text(), nullable=False),
        sa.Column("max_acceptable_value", sa.Float(), nullable=True),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("guidance", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_playbook_rules_clause_type", "playbook_rules", ["clause_type"])

    op.create_table(
        "contracts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("contract_type", sa.String(length=32), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("annual_value", sa.Float(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("risk_score", sa.Integer(), nullable=False),
        sa.Column("risk_level", sa.String(length=24), nullable=False),
        sa.Column("comparison_summary", sa.Text(), nullable=False),
        sa.Column("llm_provider_used", sa.String(length=32), nullable=False),
        sa.Column("pii_redacted", sa.Boolean(), nullable=False),
        sa.Column("last_compared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_contracts_status", "contracts", ["status"])
    op.create_index("ix_contracts_vendor_id", "contracts", ["vendor_id"])

    op.create_table(
        "contract_clause_findings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("clause_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("vendor_excerpt", sa.Text(), nullable=False),
        sa.Column("playbook_position", sa.Text(), nullable=False),
        sa.Column("redline_suggestion", sa.Text(), nullable=False),
        sa.Column("deviation_score", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contract_clause_findings_clause_type", "contract_clause_findings", ["clause_type"]
    )
    op.create_index(
        "ix_contract_clause_findings_contract_id", "contract_clause_findings", ["contract_id"]
    )

    op.create_table(
        "contract_clause_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=False),
        sa.Column("clause_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contract_clause_embeddings_clause_type", "contract_clause_embeddings", ["clause_type"]
    )
    op.create_index(
        "ix_contract_clause_embeddings_contract_id", "contract_clause_embeddings", ["contract_id"]
    )
    op.create_index(
        "ix_contract_clause_embeddings_vendor_id", "contract_clause_embeddings", ["vendor_id"]
    )

    op.create_table(
        "pricing_benchmarks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=True),
        sa.Column("sku_code", sa.String(length=80), nullable=False),
        sa.Column("sku_name", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("unit_type", sa.String(length=48), nullable=False),
        sa.Column("volume_tier", sa.String(length=24), nullable=False),
        sa.Column("quoted_unit_price", sa.Float(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("annual_uplift_pct", sa.Float(), nullable=False),
        sa.Column("discount_pct", sa.Float(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("effective_year", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pricing_benchmarks_category", "pricing_benchmarks", ["category"])
    op.create_index("ix_pricing_benchmarks_sku_code", "pricing_benchmarks", ["sku_code"])
    op.create_index("ix_pricing_benchmarks_vendor_id", "pricing_benchmarks", ["vendor_id"])

    op.create_table(
        "budget_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("cost_center_code", sa.String(length=48), nullable=False),
        sa.Column("department", sa.String(length=120), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("annual_budget", sa.Float(), nullable=False),
        sa.Column("committed_amount", sa.Float(), nullable=False),
        sa.Column("owner_name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cost_center_code"),
    )
    op.create_index(
        "ix_budget_accounts_cost_center_code",
        "budget_accounts",
        ["cost_center_code"],
        unique=True,
    )

    op.create_table(
        "vendor_quotes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=False),
        sa.Column("quote_number", sa.String(length=80), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("line_items_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("quote_number"),
    )
    op.create_index("ix_vendor_quotes_quote_number", "vendor_quotes", ["quote_number"], unique=True)
    op.create_index("ix_vendor_quotes_vendor_id", "vendor_quotes", ["vendor_id"])

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("po_number", sa.String(length=80), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=False),
        sa.Column("quote_id", sa.String(length=36), nullable=True),
        sa.Column("cost_center_code", sa.String(length=48), nullable=False),
        sa.Column("requester_name", sa.String(length=120), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("total_amount", sa.Float(), nullable=False),
        sa.Column("line_items_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("validation_status", sa.String(length=24), nullable=False),
        sa.Column("validation_issues_json", sa.JSON(), nullable=False),
        sa.Column("required_approver_role", sa.String(length=48), nullable=False),
        sa.Column("approval_request_id", sa.String(length=36), nullable=True),
        sa.Column("ai_risk_summary", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["quote_id"], ["vendor_quotes.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_number"),
    )
    op.create_index("ix_purchase_orders_cost_center_code", "purchase_orders", ["cost_center_code"])
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"], unique=True)
    op.create_index("ix_purchase_orders_quote_id", "purchase_orders", ["quote_id"])
    op.create_index("ix_purchase_orders_status", "purchase_orders", ["status"])
    op.create_index("ix_purchase_orders_vendor_id", "purchase_orders", ["vendor_id"])

    op.create_table(
        "renewal_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("vendor_id", sa.String(length=36), nullable=False),
        sa.Column("contract_id", sa.String(length=36), nullable=True),
        sa.Column("contract_title", sa.String(length=200), nullable=False),
        sa.Column("renewal_date", sa.Date(), nullable=False),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column("notice_deadline", sa.Date(), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=False),
        sa.Column("current_annual_value", sa.Float(), nullable=False),
        sa.Column("proposed_uplift_pct", sa.Float(), nullable=False),
        sa.Column("owner_name", sa.String(length=120), nullable=False),
        sa.Column("decision_status", sa.String(length=32), nullable=False),
        sa.Column("brief_markdown", sa.Text(), nullable=False),
        sa.Column("brief_data_json", sa.JSON(), nullable=False),
        sa.Column("brief_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"]),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_renewal_items_contract_id", "renewal_items", ["contract_id"])
    op.create_index("ix_renewal_items_decision_status", "renewal_items", ["decision_status"])
    op.create_index("ix_renewal_items_notice_deadline", "renewal_items", ["notice_deadline"])
    op.create_index("ix_renewal_items_renewal_date", "renewal_items", ["renewal_date"])
    op.create_index("ix_renewal_items_vendor_id", "renewal_items", ["vendor_id"])

    op.create_table(
        "renewal_alert_dispatches",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("renewal_id", sa.String(length=36), nullable=False),
        sa.Column("threshold_days", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("delivery_status", sa.String(length=24), nullable=False),
        sa.Column("recipient_target", sa.String(length=240), nullable=False),
        sa.Column("message_summary", sa.Text(), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["renewal_id"], ["renewal_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_renewal_alert_dispatches_renewal_id", "renewal_alert_dispatches", ["renewal_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_renewal_alert_dispatches_renewal_id", table_name="renewal_alert_dispatches")
    op.drop_table("renewal_alert_dispatches")
    op.drop_index("ix_renewal_items_vendor_id", table_name="renewal_items")
    op.drop_index("ix_renewal_items_renewal_date", table_name="renewal_items")
    op.drop_index("ix_renewal_items_notice_deadline", table_name="renewal_items")
    op.drop_index("ix_renewal_items_decision_status", table_name="renewal_items")
    op.drop_index("ix_renewal_items_contract_id", table_name="renewal_items")
    op.drop_table("renewal_items")
    op.drop_index("ix_purchase_orders_vendor_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_status", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_quote_id", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_po_number", table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_cost_center_code", table_name="purchase_orders")
    op.drop_table("purchase_orders")
    op.drop_index("ix_vendor_quotes_vendor_id", table_name="vendor_quotes")
    op.drop_index("ix_vendor_quotes_quote_number", table_name="vendor_quotes")
    op.drop_table("vendor_quotes")
    op.drop_index("ix_budget_accounts_cost_center_code", table_name="budget_accounts")
    op.drop_table("budget_accounts")
    op.drop_index("ix_pricing_benchmarks_vendor_id", table_name="pricing_benchmarks")
    op.drop_index("ix_pricing_benchmarks_sku_code", table_name="pricing_benchmarks")
    op.drop_index("ix_pricing_benchmarks_category", table_name="pricing_benchmarks")
    op.drop_table("pricing_benchmarks")
    op.drop_index(
        "ix_contract_clause_embeddings_vendor_id", table_name="contract_clause_embeddings"
    )
    op.drop_index(
        "ix_contract_clause_embeddings_contract_id", table_name="contract_clause_embeddings"
    )
    op.drop_index(
        "ix_contract_clause_embeddings_clause_type", table_name="contract_clause_embeddings"
    )
    op.drop_table("contract_clause_embeddings")
    op.drop_index("ix_contract_clause_findings_contract_id", table_name="contract_clause_findings")
    op.drop_index("ix_contract_clause_findings_clause_type", table_name="contract_clause_findings")
    op.drop_table("contract_clause_findings")
    op.drop_index("ix_contracts_vendor_id", table_name="contracts")
    op.drop_index("ix_contracts_status", table_name="contracts")
    op.drop_table("contracts")
    op.drop_index("ix_playbook_rules_clause_type", table_name="playbook_rules")
    op.drop_table("playbook_rules")
    op.drop_index("ix_audit_logs_sequence_num", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_type", table_name="audit_logs")
    op.drop_index("ix_audit_logs_entity_id", table_name="audit_logs")
    op.drop_index("ix_audit_logs_action", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_index("ix_approval_requests_status", table_name="approval_requests")
    op.drop_index("ix_approval_requests_required_role", table_name="approval_requests")
    op.drop_index("ix_approval_requests_entity_type", table_name="approval_requests")
    op.drop_index("ix_approval_requests_entity_id", table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index("ix_vendors_name", table_name="vendors")
    op.drop_index("ix_vendors_category", table_name="vendors")
    op.drop_table("vendors")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
