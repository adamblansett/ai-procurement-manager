import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from httpx import AsyncClient

from alembic import command


def test_alembic_upgrade_and_downgrade_roundtrip(tmp_path: Path) -> None:
    backend_dir = Path(__file__).resolve().parents[1]
    db_path = tmp_path / "alembic_test.db"
    cfg = Config(str(backend_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite+aiosqlite:///{db_path.as_posix()}")

    command.upgrade(cfg, "head")
    with sqlite3.connect(db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    expected = {
        "users",
        "vendors",
        "approval_requests",
        "audit_logs",
        "playbook_rules",
        "contracts",
        "contract_clause_findings",
        "contract_clause_embeddings",
        "pricing_benchmarks",
        "budget_accounts",
        "vendor_quotes",
        "purchase_orders",
        "renewal_items",
        "renewal_alert_dispatches",
    }
    assert expected.issubset(tables)

    command.downgrade(cfg, "base")
    with sqlite3.connect(db_path) as conn:
        remaining = {
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
    assert "vendors" not in remaining
    assert "contracts" not in remaining

    command.upgrade(cfg, "head")


@pytest.mark.asyncio
async def test_semantic_clause_search_returns_relevant_precedent(
    seeded_client: AsyncClient,
) -> None:
    resp = await seeded_client.post(
        "/api/v1/contracts/search",
        json={
            "query": "aggregate liability cap 12 months super-cap data breach",
            "top_k": 5,
        },
    )
    assert resp.status_code == 200
    hits = resp.json()
    assert len(hits) >= 1
    assert hits[0]["clause_type"] == "liability_cap"
    assert hits[0]["similarity_score"] > 0.1

    filtered = await seeded_client.post(
        "/api/v1/contracts/search",
        json={
            "query": "annual price uplift increase cap",
            "clause_type": "price_uplift",
            "top_k": 3,
        },
    )
    assert filtered.status_code == 200
    filtered_hits = filtered.json()
    assert len(filtered_hits) >= 1
    assert all(h["clause_type"] == "price_uplift" for h in filtered_hits)
