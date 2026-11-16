"""End-to-end tests for the ERPNext Mock REST API and MCP analytics tools."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from erpnext_mock.main import app
from erpnext_mock.seed import reset_and_seed
from mcp_server import analytics, server
from mcp_server.client import ERPNextClient


@pytest.fixture()
def seeded_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_file = tmp_path / "test_erpnext.db"
    monkeypatch.setenv("ERPNEXT_MOCK_DB", str(db_file))
    reset_and_seed(db_file)
    return db_file


def test_erpnext_rest_endpoints(seeded_db: Path) -> None:
    with TestClient(app) as client:
        # Ping
        assert client.get("/api/method/ping").json() == {"message": "pong"}

        # List Items with Frappe filters & fields
        resp = client.get(
            "/api/resource/Item",
            params={
                "fields": json.dumps(["item_code", "item_group", "standard_rate"]),
                "filters": json.dumps([["item_group", "=", "Dairy Alternatives"]]),
                "limit_page_length": 10,
            },
        )
        assert resp.status_code == 200
        items = resp.json()["data"]
        assert len(items) == 6
        assert all(i["item_group"] == "Dairy Alternatives" for i in items)

        # Get single Purchase Order with child items
        po_resp = client.get("/api/resource/Purchase Order/PUR-ORD-2026-00002")
        assert po_resp.status_code == 200
        po = po_resp.json()["data"]
        assert po["supplier"] == "Oatly UK Ltd"
        assert len(po["items"]) == 3

        # Create & Update Supplier
        create_resp = client.post(
            "/api/resource/Supplier",
            json={"supplier_name": "Test Roasters Ltd", "archetype": "Standard"},
        )
        assert create_resp.status_code == 200
        assert create_resp.json()["data"]["name"] == "Test Roasters Ltd"


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_mcp_analytics_and_write_gate(
    seeded_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = httpx.ASGITransport(app=app)
    test_client = ERPNextClient(base_url="http://testserver", transport=transport)
    monkeypatch.setattr(server, "_client", test_client)

    # 1. Buying overview
    overview = await analytics.get_buying_overview(test_client, period="Q4")
    assert overview["total_spend_gbp"] > 0
    assert len(overview["alerts"]) >= 2
    assert "voice_summary" in overview

    # 2. Supplier graph summary (Oatly UK Ltd -> 4,720 Q4 cases + top_skus capped at 3)
    sup_summary = await analytics.get_supplier_graph_summary(
        test_client, supplier_query="Oatly", period="Q4"
    )
    assert sup_summary["total_cases"] == 4720
    assert sup_summary["categories"][0]["item_group"] == "Dairy Alternatives"
    assert len(sup_summary["top_skus"]) == 3

    # 3. Drill-down SKUs capped at limit
    skus = await analytics.drill_down_skus(
        test_client, supplier_query="Peak Snacks", limit=3
    )
    assert skus["returned_count"] == 3

    # 4. Rebate evaluation (4,720 cases vs 5,000 threshold -> gap 280 + Q4 ambiguity)
    rebate = await analytics.evaluate_rebate_deal(
        test_client,
        supplier_query="Oatly",
        item_group_or_sku="Dairy Alternatives",
        min_cases=5000,
        rebate_pct=4.0,
        fixed_promo_gbp=2000.0,
        period="Q4",
    )
    assert rebate["current_cases"] == 4720
    assert rebate["gap_cases"] == 280
    assert rebate["threshold_met"] is False
    assert len(rebate["ambiguities"]) == 1

    # 5. Invoice leakage detection (GreenLeaf Foods -> £1,460 overcharge)
    leakage = await analytics.detect_invoice_leakage(test_client, supplier_query="GreenLeaf")
    assert leakage["total_leakage_gbp"] == pytest.approx(1460.0)
    assert len(leakage["discrepancies"]) == 3

    # 6. Staging-time validation rejects malformed payloads before Inspector/confirm
    bad_dispute = await server.propose_erp_action(
        action_type="flag_invoice_dispute",
        supplier="GreenLeaf Foods",
        summary="Hold invoice",
        payload={},
    )
    assert "error" in bad_dispute

    bad_po = await server.propose_erp_action(
        action_type="create_purchase_order",
        supplier="Oatly UK Ltd",
        summary="Order 280 cases",
        payload={"items": []},
    )
    assert "error" in bad_po

    # 7. Two-step human-in-the-loop write gate: stage + confirm invoice dispute & PO
    staged = await server.propose_erp_action(
        action_type="flag_invoice_dispute",
        supplier="GreenLeaf Foods",
        summary="Hold ACC-PINV-2026-00002 due to £960 overcharge",
        payload={"invoice_name": "ACC-PINV-2026-00002", "notes": "Disputed £960 price drift"},
    )
    assert staged["status"] == "PENDING"
    confirmed = await server.confirm_erp_action(staged["proposal_id"])
    assert confirmed["status"] == "CONFIRMED"
    assert confirmed["new_status"] == "On Hold"

    staged_po = await server.propose_erp_action(
        action_type="create_purchase_order",
        supplier="Oatly UK Ltd",
        summary="Order 280 cases of Oatly Barista to hit Q4 rebate tier",
        payload={"items": [{"item_code": "OAT-BAR-1L", "qty": 280, "rate": 11.40}]},
    )
    assert staged_po["status"] == "PENDING"
    confirmed_po = await server.confirm_erp_action(staged_po["proposal_id"])
    assert confirmed_po["status"] == "CONFIRMED"
    assert confirmed_po["created_document"].startswith("PUR-ORD-2026-")
