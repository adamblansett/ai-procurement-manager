import io
import zipfile
from typing import Any

import httpx
import pytest
from httpx import AsyncClient


def _build_minimal_pdf(text: str) -> bytes:
    """Create a valid single-page PDF 1.4 document with extractable text."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        ),
        (b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"),
        (
            f"5 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii")
            + stream
            + b"\nendstream\nendobj\n"
        ),
    ]
    buffer = io.BytesIO()
    buffer.write(b"%PDF-1.4\n")
    offsets: list[int] = []
    for obj in objects:
        offsets.append(buffer.tell())
        buffer.write(obj)
    xref_pos = buffer.tell()
    buffer.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
    for off in offsets:
        buffer.write(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    buffer.write(trailer.encode("ascii"))
    return buffer.getvalue()


def _build_minimal_docx(paragraphs: list[str]) -> bytes:
    """Create an in-memory .docx ZIP archive containing word/document.xml."""
    para_xml = "".join(f"<w:p><w:r><w:t>{p}</w:t></w:r></w:p>" for p in paragraphs)
    doc_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{para_xml}</w:body></w:document>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("word/document.xml", doc_xml.encode("utf-8"))
    return buf.getvalue()


@pytest.mark.asyncio
async def test_pdf_and_docx_contract_upload_csv_imports_and_exports(
    seeded_client: AsyncClient,
) -> None:
    vendors = (await seeded_client.get("/api/v1/vendors")).json()
    vendor_id = vendors[0]["id"]

    # 1. Upload .docx contract
    docx_bytes = _build_minimal_docx(
        [
            "This Agreement shall automatically renew unless 90 days notice is given.",
            "Fees shall increase by 8% annually. Payment terms are Net 15.",
            "Aggregate liability is capped at 3 months of fees paid.",
        ]
    )
    docx_resp = await seeded_client.post(
        "/api/v1/contracts/upload",
        data={
            "vendor_id": vendor_id,
            "title": "Uploaded DOCX MSA",
            "contract_type": "MSA",
            "annual_value": "95000",
        },
        files={
            "file": (
                "vendor_msa.docx",
                docx_bytes,
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert docx_resp.status_code == 201
    docx_data = docx_resp.json()
    assert docx_data["risk_level"] in {"high", "critical"}
    assert "90 days notice" in docx_data["raw_text"]

    # 2. Upload .pdf contract
    pdf_bytes = _build_minimal_pdf(
        "No automatic renewal applies. Payment terms are Net 45. "
        "Mutual liability cap of 12 months fees. Uptime SLA 99.95%."
    )
    pdf_resp = await seeded_client.post(
        "/api/v1/contracts/upload",
        data={
            "vendor_id": vendor_id,
            "title": "Uploaded PDF MSA",
            "contract_type": "MSA",
            "annual_value": "75000",
        },
        files={"file": ("clean_msa.pdf", pdf_bytes, "application/pdf")},
    )
    assert pdf_resp.status_code == 201
    assert "Net 45" in pdf_resp.json()["raw_text"]

    # 3. Bulk CSV import for benchmarks and budgets
    bm_csv = (
        "sku_code,sku_name,category,unit_type,volume_tier,quoted_unit_price,"
        "annual_uplift_pct,discount_pct,source,effective_year,notes\n"
        "AI-COPILOT-SEAT,AI Procurement Seat,SaaS Applications,seat/month,"
        "51-250,45.0,3.0,15.0,market_index,2026,CSV test\n"
        "AI-COPILOT-SEAT,AI Procurement Seat,SaaS Applications,seat/month,"
        "251-1000,39.0,2.5,22.0,executed_contract,2026,CSV test 2\n"
    )
    bm_import = await seeded_client.post(
        "/api/v1/benchmarks/import-csv",
        files={"file": ("benchmarks.csv", bm_csv.encode("utf-8"), "text/csv")},
    )
    assert bm_import.status_code == 200
    assert bm_import.json()["imported_count"] == 2

    budget_csv = (
        "cost_center_code,department,fiscal_year,annual_budget,committed_amount,owner_name\n"
        "CC-AI-777,AI Operations,2026,300000,25000,Morgan Blake\n"
    )
    budget_import = await seeded_client.post(
        "/api/v1/purchasing/budgets/import-csv",
        files={"file": ("budgets.csv", budget_csv.encode("utf-8"), "text/csv")},
    )
    assert budget_import.status_code == 200
    assert budget_import.json()["imported_count"] == 1

    # 4. Export renewal brief (.md) & audit ledger (csv + signed json)
    renewals = (await seeded_client.get("/api/v1/renewals")).json()
    md_export = await seeded_client.get(f"/api/v1/renewals/{renewals[0]['id']}/export")
    assert md_export.status_code == 200
    assert "text/markdown" in md_export.headers["content-type"]
    assert "Renegotiation Dossier" in md_export.text

    csv_export = await seeded_client.get("/api/v1/governance/audit-logs/export?export_format=csv")
    assert csv_export.status_code == 200
    assert "sequence_num,created_at,actor,action" in csv_export.text

    json_export = await seeded_client.get("/api/v1/governance/audit-logs/export?export_format=json")
    assert json_export.status_code == 200
    bundle = json_export.json()
    assert bundle["chain_verification"]["valid"] is True
    assert len(bundle["entries"]) >= 10


@pytest.mark.asyncio
async def test_renewal_alert_deduplication_webhook_and_telemetry(
    seeded_client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seeded data already swept initial alerts; a 2nd run dispatches 0 duplicates
    second_sweep = await seeded_client.post("/api/v1/renewals/alerts/run")
    assert second_sweep.status_code == 200
    assert second_sweep.json()["dispatched_count"] == 0

    alerts = (await seeded_client.get("/api/v1/renewals/alerts")).json()
    assert len(alerts) >= 2

    # Webhook delivery check on a fresh renewal when alert_webhook_url is configured
    posted_payloads: list[dict[str, Any]] = []
    orig_post = httpx.AsyncClient.post

    async def fake_post(self: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
        if str(url).startswith("https://hooks.internal.example"):
            posted_payloads.append({"url": url, "json": kwargs.get("json")})
            return httpx.Response(status_code=200, request=httpx.Request("POST", url))
        return await orig_post(self, url, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    seeded_client._transport.app.state.settings.alert_webhook_url = (  # type: ignore[attr-defined]
        "https://hooks.internal.example/procurement"
    )

    vendors = (await seeded_client.get("/api/v1/vendors")).json()
    from datetime import date, timedelta

    await seeded_client.post(
        "/api/v1/renewals",
        json={
            "vendor_id": vendors[0]["id"],
            "contract_title": "Webhook Triggered Renewal",
            "renewal_date": (date.today() + timedelta(days=35)).isoformat(),
            "notice_period_days": 30,
            "auto_renew": True,
            "current_annual_value": 55000.0,
            "proposed_uplift_pct": 6.0,
            "owner_name": "Samira Chen",
        },
    )
    sweep_with_hook = await seeded_client.post("/api/v1/renewals/alerts/run")
    assert sweep_with_hook.status_code == 200
    assert sweep_with_hook.json()["dispatched_count"] == 1
    assert sweep_with_hook.json()["dispatches"][0]["delivery_status"] == "sent"
    assert len(posted_payloads) == 1

    # Prometheus metrics & JSON telemetry endpoints
    metrics_resp = await seeded_client.get("/api/v1/health/metrics")
    assert metrics_resp.status_code == 200
    assert "procurement_http_requests_total" in metrics_resp.text

    tel_resp = await seeded_client.get("/api/v1/health/telemetry")
    assert tel_resp.status_code == 200
    assert tel_resp.json()["total_requests"] >= 1
