"""Voice-optimized retail buying analytics, graph rollups, and write-gate logic."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from mcp_server.client import ERPNextClient


@dataclass
class PendingProposal:
    """Represents a human-in-the-loop staged ERP action awaiting voice confirmation."""

    proposal_id: str
    action_type: str
    supplier: str
    summary: str
    payload: dict[str, Any]
    status: str = "PENDING"


class ProposalStore:
    """In-memory store for two-step human-in-the-loop ERP write actions."""

    def __init__(self) -> None:
        self._items: dict[str, PendingProposal] = {}

    def create(
        self, action_type: str, supplier: str, summary: str, payload: dict[str, Any]
    ) -> PendingProposal:
        pid = f"PROP-{uuid.uuid4().hex[:6].upper()}"
        prop = PendingProposal(
            proposal_id=pid,
            action_type=action_type,
            supplier=supplier,
            summary=summary,
            payload=payload,
        )
        self._items[pid] = prop
        return prop

    def get(self, proposal_id: str) -> PendingProposal | None:
        return self._items.get(proposal_id)


def resolve_period(period: str | None) -> tuple[str, str, list[str]]:
    """Resolve a spoken period string into (start_date, end_date, ambiguities).

    Flags ambiguity when a quarter like 'Q4' is given without specifying
    calendar vs. UK retail fiscal year.
    """
    ambiguities: list[str] = []
    if not period:
        return "2026-01-01", "2026-12-31", ambiguities

    norm = period.strip().lower()
    if ":" in norm:
        start, end = [p.strip() for p in norm.split(":", 1)]
        return start, end, ambiguities

    if "q3" in norm:
        return "2026-07-01", "2026-09-30", ambiguities

    if "q4" in norm:
        if "fiscal" in norm:
            return "2026-11-01", "2027-01-31", ambiguities
        if "calendar" not in norm:
            ambiguities.append(
                "Period 'Q4' is ambiguous: assumed Calendar Q4 (2026-10-01 to 2026-12-31). "
                "Confirm if UK retail fiscal Q4 (Nov-Jan) is intended."
            )
        return "2026-10-01", "2026-12-31", ambiguities

    return "2026-01-01", "2026-12-31", ambiguities


async def _fetch_full_orders(
    client: ERPNextClient, supplier: str | None = None
) -> list[dict[str, Any]]:
    filters = [["supplier", "=", supplier]] if supplier else None
    summaries = await client.list_docs(
        "Purchase Order", fields=["name", "supplier", "transaction_date", "grand_total", "total_qty", "status"], filters=filters
    )
    return [await client.get_doc("Purchase Order", row["name"]) for row in summaries]


async def _fetch_full_invoices(
    client: ERPNextClient, supplier: str | None = None
) -> list[dict[str, Any]]:
    filters = [["supplier", "=", supplier]] if supplier else None
    summaries = await client.list_docs(
        "Purchase Invoice", fields=["name", "supplier", "posting_date", "grand_total", "status", "purchase_order"], filters=filters
    )
    return [await client.get_doc("Purchase Invoice", row["name"]) for row in summaries]


async def _match_supplier(client: ERPNextClient, query: str) -> dict[str, Any] | None:
    suppliers = await client.list_docs(
        "Supplier", fields=["name", "supplier_name", "supplier_group", "archetype"]
    )
    q = query.strip().lower()
    for sup in suppliers:
        if q == sup["name"].lower() or q in sup["supplier_name"].lower():
            return sup
    return None


async def detect_invoice_leakage(
    client: ERPNextClient, supplier_query: str | None = None
) -> dict[str, Any]:
    """Cross-check Purchase Invoice item rates against linked Purchase Orders."""
    target_supplier = None
    if supplier_query:
        matched = await _match_supplier(client, supplier_query)
        if not matched:
            return {
                "total_leakage_gbp": 0.0,
                "discrepancies": [],
                "voice_summary": f"No supplier matched '{supplier_query}'.",
            }
        target_supplier = matched["name"]

    orders = await _fetch_full_orders(client, target_supplier)
    invoices = await _fetch_full_invoices(client, target_supplier)

    # Map (po_name, item_code) -> PO unit rate
    po_rates: dict[tuple[str, str], float] = {}
    for po in orders:
        for line in po.get("items", []):
            po_rates[(po["name"], line["item_code"])] = float(line["rate"])

    discrepancies: list[dict[str, Any]] = []
    total_leakage = 0.0

    for inv in invoices:
        for line in inv.get("items", []):
            po_name = line.get("purchase_order") or inv.get("purchase_order") or ""
            po_rate = po_rates.get((po_name, line["item_code"]))
            if po_rate is None:
                continue
            inv_rate = float(line["rate"])
            qty = float(line["qty"])
            diff_per_unit = round(inv_rate - po_rate, 2)
            if diff_per_unit > 0.001:
                overcharge = round(diff_per_unit * qty, 2)
                total_leakage = round(total_leakage + overcharge, 2)
                discrepancies.append(
                    {
                        "invoice": inv["name"],
                        "purchase_order": po_name,
                        "supplier": inv["supplier"],
                        "item_code": line["item_code"],
                        "item_name": line["item_name"],
                        "qty": qty,
                        "po_rate": po_rate,
                        "invoice_rate": inv_rate,
                        "overcharge_gbp": overcharge,
                    }
                )

    if not discrepancies:
        summary = "No invoice price leakage detected."
    else:
        suppliers_affected = sorted({d["supplier"] for d in discrepancies})
        summary = (
            f"Detected £{total_leakage:,.2f} in invoice overcharges across "
            f"{len(discrepancies)} line items from {', '.join(suppliers_affected)}."
        )

    return {
        "total_leakage_gbp": total_leakage,
        "discrepancies": discrepancies[:10],
        "voice_summary": summary,
    }


async def get_buying_overview(
    client: ERPNextClient, period: str | None = None
) -> dict[str, Any]:
    """Return a voice-first portfolio summary grouped by supplier and anomaly."""
    start_date, end_date, ambiguities = resolve_period(period)
    suppliers = await client.list_docs(
        "Supplier", fields=["name", "supplier_name", "supplier_group", "archetype"]
    )
    orders = await _fetch_full_orders(client)

    spend_by_sup: dict[str, float] = defaultdict(float)
    cases_by_sup: dict[str, float] = defaultdict(float)

    for po in orders:
        if start_date <= po["transaction_date"] <= end_date:
            spend_by_sup[po["supplier"]] += float(po["grand_total"])
            cases_by_sup[po["supplier"]] += float(po["total_qty"])

    top_suppliers = sorted(
        [
            {
                "supplier": s["name"],
                "archetype": s["archetype"],
                "cases": int(cases_by_sup[s["name"]]),
                "spend_gbp": round(spend_by_sup[s["name"]], 2),
            }
            for s in suppliers
        ],
        key=lambda x: x["spend_gbp"],
        reverse=True,
    )

    leakage = await detect_invoice_leakage(client)
    total_spend = round(sum(spend_by_sup.values()), 2)

    alerts: list[str] = []
    if leakage["total_leakage_gbp"] > 0:
        alerts.append(leakage["voice_summary"])

    # Highlight near-threshold rebate suppliers
    for sup_row in top_suppliers:
        if sup_row["archetype"] == "Rebate-Threshold" and 4000 <= sup_row["cases"] < 5000:
            gap = 5000 - sup_row["cases"]
            alerts.append(
                f"{sup_row['supplier']} is at {sup_row['cases']:,} cases, "
                f"only {gap:,} cases below a 5,000-case rebate tier."
            )

    top_str = ", ".join(
        f"{s['supplier']} (£{s['spend_gbp']:,.0f})" for s in top_suppliers[:3]
    )
    voice_summary = (
        f"Total PO spend for the period is £{total_spend:,.2f} across {len(suppliers)} suppliers. "
        f"Top suppliers: {top_str}. "
        + ("Alerts: " + " ".join(alerts) if alerts else "No critical alerts.")
    )

    return {
        "period": {"start": start_date, "end": end_date},
        "ambiguities": ambiguities,
        "total_spend_gbp": total_spend,
        "top_suppliers": top_suppliers[:5],
        "alerts": alerts,
        "voice_summary": voice_summary,
    }


async def get_supplier_graph_summary(
    client: ERPNextClient, supplier_query: str, period: str | None = None
) -> dict[str, Any]:
    """Aggregate a supplier's PO volume and spend by Item Group (category)."""
    matched = await _match_supplier(client, supplier_query)
    if not matched:
        return {"error": f"No supplier matched '{supplier_query}'", "voice_summary": f"I could not find a supplier matching {supplier_query}."}

    start_date, end_date, ambiguities = resolve_period(period)
    orders = await _fetch_full_orders(client, matched["name"])

    by_group: dict[str, dict[str, float]] = defaultdict(lambda: {"cases": 0.0, "spend_gbp": 0.0})
    po_count = 0
    for po in orders:
        if start_date <= po["transaction_date"] <= end_date:
            po_count += 1
            for line in po.get("items", []):
                grp = line.get("item_group") or "Uncategorized"
                by_group[grp]["cases"] += float(line["qty"])
                by_group[grp]["spend_gbp"] += float(line["amount"])

    categories = [
        {
            "item_group": grp,
            "cases": int(vals["cases"]),
            "spend_gbp": round(vals["spend_gbp"], 2),
        }
        for grp, vals in sorted(by_group.items(), key=lambda kv: kv[1]["spend_gbp"], reverse=True)
    ]
    total_cases = sum(c["cases"] for c in categories)
    total_spend = round(sum(c["spend_gbp"] for c in categories), 2)

    cat_summary = ", ".join(f"{c['item_group']} ({c['cases']:,} cases)" for c in categories)
    voice_summary = (
        f"{matched['name']} has {po_count} purchase orders totaling {total_cases:,} cases "
        f"and £{total_spend:,.2f}. Categories: {cat_summary or 'none'}."
    )

    return {
        "supplier": matched["name"],
        "archetype": matched["archetype"],
        "period": {"start": start_date, "end": end_date},
        "ambiguities": ambiguities,
        "total_cases": total_cases,
        "total_spend_gbp": total_spend,
        "categories": categories,
        "voice_summary": voice_summary,
    }


async def drill_down_skus(
    client: ERPNextClient,
    supplier_query: str | None = None,
    item_group: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Return top-N SKUs matching a supplier or item group (capped for voice)."""
    safe_limit = max(1, min(limit, 10))
    filters: list[Any] = []
    if item_group:
        filters.append(["item_group", "like", f"%{item_group}%"])

    items = await client.list_docs(
        "Item",
        fields=["item_code", "item_name", "item_group", "standard_rate", "brand"],
        filters=filters or None,
        limit_page_length=100,
    )

    if supplier_query:
        matched = await _match_supplier(client, supplier_query)
        if matched:
            orders = await _fetch_full_orders(client, matched["name"])
            ordered_codes = {
                line["item_code"] for po in orders for line in po.get("items", [])
            }
            if ordered_codes:
                items = [i for i in items if i["item_code"] in ordered_codes]

    sliced = items[:safe_limit]
    names = ", ".join(f"{i['item_code']} ({i['item_name']})" for i in sliced)
    voice_summary = (
        f"Showing {len(sliced)} of {len(items)} matching SKUs: {names}."
        if sliced
        else "No matching SKUs found."
    )
    return {
        "total_matching": len(items),
        "returned_count": len(sliced),
        "items": sliced,
        "voice_summary": voice_summary,
    }


async def evaluate_rebate_deal(
    client: ERPNextClient,
    supplier_query: str,
    item_group_or_sku: str,
    min_cases: int,
    rebate_pct: float,
    fixed_promo_gbp: float = 0.0,
    period: str = "Q4",
) -> dict[str, Any]:
    """Validate SKU/category scope, check PO volume, flag ambiguities, and compute rebate."""
    matched = await _match_supplier(client, supplier_query)
    if not matched:
        return {"error": f"Supplier '{supplier_query}' not found.", "voice_summary": f"No supplier found matching {supplier_query}."}

    start_date, end_date, ambiguities = resolve_period(period)
    orders = await _fetch_full_orders(client, matched["name"])

    scope_q = item_group_or_sku.strip().lower()
    matched_cases = 0.0
    matched_spend = 0.0
    matched_skus: set[str] = set()

    for po in orders:
        if not (start_date <= po["transaction_date"] <= end_date):
            continue
        for line in po.get("items", []):
            in_scope = (
                scope_q in line["item_code"].lower()
                or scope_q in line["item_name"].lower()
                or scope_q in (line.get("item_group") or "").lower()
            )
            if in_scope:
                matched_cases += float(line["qty"])
                matched_spend += float(line["amount"])
                matched_skus.add(line["item_code"])

    if not matched_skus:
        ambiguities.append(
            f"No ordered SKUs matched '{item_group_or_sku}' for {matched['name']} in {start_date}..{end_date}."
        )

    threshold_met = matched_cases >= min_cases
    gap_cases = max(0, int(min_cases - matched_cases))
    retroactive_rebate = round(matched_spend * (rebate_pct / 100.0), 2) if threshold_met else 0.0
    projected_rebate = round(matched_spend * (rebate_pct / 100.0) + fixed_promo_gbp, 2)
    total_owed = round(retroactive_rebate + (fixed_promo_gbp if threshold_met else 0.0), 2)

    if threshold_met:
        status_msg = (
            f"Threshold met with {int(matched_cases):,} cases against {min_cases:,}. "
            f"Total rebate owed is £{total_owed:,.2f}."
        )
    else:
        status_msg = (
            f"Currently at {int(matched_cases):,} cases, {gap_cases:,} cases short of the {min_cases:,} threshold. "
            f"If hit, total value is £{projected_rebate:,.2f}."
        )

    amb_msg = f" Note: {ambiguities[0]}" if ambiguities else ""
    return {
        "supplier": matched["name"],
        "scope": item_group_or_sku,
        "matched_sku_count": len(matched_skus),
        "period": {"start": start_date, "end": end_date},
        "ambiguities": ambiguities,
        "current_cases": int(matched_cases),
        "min_cases": min_cases,
        "gap_cases": gap_cases,
        "threshold_met": threshold_met,
        "eligible_spend_gbp": round(matched_spend, 2),
        "total_rebate_owed_gbp": total_owed,
        "projected_rebate_if_hit_gbp": projected_rebate,
        "voice_summary": status_msg + amb_msg,
    }
