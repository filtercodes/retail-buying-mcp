"""FastMCP server exposing voice-optimized retail buying tools over ERPNext REST APIs."""

from __future__ import annotations

import argparse
from datetime import date, timedelta
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

from mcp_server import analytics
from mcp_server.analytics import ProposalStore
from mcp_server.client import ERPNextClient

mcp = FastMCP("retail-buying-erp")
_client = ERPNextClient()
_proposals = ProposalStore()


@mcp.tool()
async def get_buying_overview(period: str = "Q4") -> dict[str, Any]:
    """Get a voice-friendly portfolio overview of spend, top suppliers, and alerts.

    Args:
        period: Optional period filter such as 'Q3', 'Q4', 'calendar Q4', or '2026-10-01:2026-12-31'.
    """
    return await analytics.get_buying_overview(_client, period=period)


@mcp.tool()
async def get_supplier_graph_summary(
    supplier_query: str, period: str = "Q4"
) -> dict[str, Any]:
    """Get a supplier's volume and spend aggregated by Item Group (category), not raw SKUs.

    Args:
        supplier_query: Supplier name or partial name (e.g. 'Oatly', 'GreenLeaf', 'Artisan').
        period: Optional period filter such as 'Q3', 'Q4', or '2026-10-01:2026-12-31'.
    """
    return await analytics.get_supplier_graph_summary(
        _client, supplier_query=supplier_query, period=period
    )


@mcp.tool()
async def drill_down_skus(
    supplier_query: str | None = None,
    item_group: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Drill down into specific SKUs for a supplier or Item Group (capped for voice).

    Args:
        supplier_query: Optional supplier name filter.
        item_group: Optional category / Item Group filter (e.g. 'Dairy Alternatives').
        limit: Maximum number of SKUs to return (1 to 10, default 5).
    """
    return await analytics.drill_down_skus(
        _client, supplier_query=supplier_query, item_group=item_group, limit=limit
    )


@mcp.tool()
async def evaluate_rebate_deal(
    supplier_query: str,
    item_group_or_sku: str,
    min_cases: int,
    rebate_pct: float,
    fixed_promo_gbp: float = 0.0,
    period: str = "Q4",
) -> dict[str, Any]:
    """Evaluate a supplier rebate deal against ERPNext Purchase Orders and flag ambiguities.

    Args:
        supplier_query: Supplier name (e.g. 'Oatly').
        item_group_or_sku: Category or SKU name/code (e.g. 'Dairy Alternatives' or 'Oat').
        min_cases: Minimum case volume threshold required to earn the rebate.
        rebate_pct: Retroactive rebate percentage (e.g. 4.0 for 4%).
        fixed_promo_gbp: Optional fixed promotional payment in GBP.
        period: Period string (e.g. 'Q4', 'calendar Q4', 'fiscal Q4').
    """
    return await analytics.evaluate_rebate_deal(
        _client,
        supplier_query=supplier_query,
        item_group_or_sku=item_group_or_sku,
        min_cases=min_cases,
        rebate_pct=rebate_pct,
        fixed_promo_gbp=fixed_promo_gbp,
        period=period,
    )


@mcp.tool()
async def detect_invoice_leakage(supplier_query: str | None = None) -> dict[str, Any]:
    """Detect unit-price overcharges by comparing Purchase Invoices against Purchase Orders.

    Args:
        supplier_query: Optional supplier name filter; omit to scan all suppliers.
    """
    return await analytics.detect_invoice_leakage(_client, supplier_query=supplier_query)


async def _validate_proposal_payload(
    action_type: str, payload: dict[str, Any]
) -> str | None:
    """Validate payload structure and referenced ERPNext documents before staging."""
    if not isinstance(payload, dict):
        return "payload must be a JSON object."

    if action_type == "flag_invoice_dispute":
        invoice_name = payload.get("invoice_name")
        if not invoice_name or not isinstance(invoice_name, str):
            return (
                "flag_invoice_dispute requires payload={'invoice_name': '<ACC-PINV-...>', "
                "'notes': '<reason>'}."
            )
        try:
            await _client.get_doc("Purchase Invoice", invoice_name)
        except httpx.HTTPStatusError:
            return f"Purchase Invoice '{invoice_name}' does not exist in ERPNext."
        return None

    if action_type == "create_purchase_order":
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            return (
                "create_purchase_order requires payload={'items': [{'item_code': '<SKU>', "
                "'qty': <number>, 'rate': <number>}]}."
            )
        for idx, line in enumerate(items, start=1):
            if not isinstance(line, dict) or not line.get("item_code"):
                return f"items[{idx - 1}] must be an object with 'item_code', 'qty', and 'rate'."
            if "qty" not in line or float(line["qty"]) <= 0:
                return f"items[{idx - 1}] must have a positive 'qty'."
            if "rate" not in line or float(line["rate"]) < 0:
                return f"items[{idx - 1}] must have a non-negative 'rate'."
            try:
                item_doc = await _client.get_doc("Item", str(line["item_code"]))
            except httpx.HTTPStatusError:
                return f"Item '{line['item_code']}' does not exist in ERPNext."
            line.setdefault("item_name", item_doc["item_name"])
            line.setdefault("item_group", item_doc["item_group"])
            line.setdefault("uom", item_doc.get("stock_uom", "Case"))
        return None

    return f"Unsupported action_type '{action_type}'."


@mcp.tool()
async def propose_erp_action(
    action_type: str,
    supplier: str,
    summary: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Stage an ERP write action for human voice confirmation before committing.

    Args:
        action_type: Must be 'flag_invoice_dispute' or 'create_purchase_order'.
        supplier: Exact or partial supplier name.
        summary: Short human-readable summary to read aloud for confirmation.
        payload: Required fields depend on action_type:
            - For 'flag_invoice_dispute': {"invoice_name": "ACC-PINV-2026-00002", "notes": "Overcharge reason"}
            - For 'create_purchase_order': {"items": [{"item_code": "OAT-BAR-1L", "qty": 280, "rate": 11.40}], "transaction_date": "2026-11-16", "schedule_date": "2026-11-23"} (dates optional)
    """
    allowed = {"create_purchase_order", "flag_invoice_dispute"}
    if action_type not in allowed:
        return {
            "error": f"Unsupported action_type '{action_type}'. Use one of {sorted(allowed)}.",
            "voice_summary": f"Action type {action_type} is not supported.",
        }

    validation_error = await _validate_proposal_payload(action_type, payload)
    if validation_error:
        return {
            "error": validation_error,
            "voice_summary": f"Cannot stage action: {validation_error}",
        }

    prop = _proposals.create(action_type, supplier, summary, payload)
    return {
        "proposal_id": prop.proposal_id,
        "status": prop.status,
        "summary": prop.summary,
        "voice_summary": f"Staged proposal {prop.proposal_id}: {summary}. Say confirm to execute.",
    }


@mcp.tool()
async def confirm_erp_action(proposal_id: str) -> dict[str, Any]:
    """Execute a previously staged proposal against the ERPNext REST API.

    Args:
        proposal_id: The proposal ID returned by propose_erp_action.
    """
    prop = _proposals.get(proposal_id)
    if not prop:
        return {
            "error": f"Proposal {proposal_id} not found.",
            "voice_summary": f"Proposal {proposal_id} was not found.",
        }
    if prop.status != "PENDING":
        return {
            "error": f"Proposal {proposal_id} is already {prop.status}.",
            "voice_summary": f"Proposal {proposal_id} has already been processed.",
        }

    if prop.action_type == "create_purchase_order":
        doc_payload = dict(prop.payload)
        today = date.today()
        doc_payload.setdefault("supplier", prop.supplier)
        doc_payload.setdefault("transaction_date", today.isoformat())
        doc_payload.setdefault("schedule_date", (today + timedelta(days=7)).isoformat())
        created = await _client.create_doc("Purchase Order", doc_payload)
        prop.status = "CONFIRMED"
        return {
            "proposal_id": prop.proposal_id,
            "status": prop.status,
            "created_document": created["name"],
            "grand_total_gbp": created["grand_total"],
            "voice_summary": (
                f"Confirmed. Created Purchase Order {created['name']} for {prop.supplier} "
                f"totaling £{created['grand_total']:,.2f}."
            ),
        }

    # flag_invoice_dispute
    invoice_name = prop.payload.get("invoice_name")
    if not invoice_name:
        return {
            "error": "payload.invoice_name is required for flag_invoice_dispute.",
            "voice_summary": "Missing invoice name in dispute payload.",
        }
    updated = await _client.update_doc(
        "Purchase Invoice",
        str(invoice_name),
        {
            "status": "On Hold",
            "notes": prop.payload.get("notes") or prop.summary,
        },
    )
    prop.status = "CONFIRMED"
    return {
        "proposal_id": prop.proposal_id,
        "status": prop.status,
        "updated_document": updated["name"],
        "new_status": updated["status"],
        "voice_summary": f"Confirmed. Invoice {updated['name']} is now On Hold with dispute notes.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Retail Buying MCP Server.")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http", "sse"],
        default="stdio",
        help="MCP transport protocol (default: stdio).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host for HTTP/SSE transports.")
    parser.add_argument("--port", type=int, default=8001, help="Port for HTTP/SSE transports.")
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.settings.host = args.host
        mcp.settings.port = args.port
        mcp.run(transport=args.transport)


if __name__ == "__main__":
    main()
