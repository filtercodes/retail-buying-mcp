"""Deterministic graph-archetype retail dataset seeder for the ERPNext mock DB.

Organizes SKUs, Suppliers, Purchase Orders, and Purchase Invoices into 4 clear
archetypes so a voice agent can query high-level rollups and anomalies without
reciting hundreds of individual SKUs:
  1. Rebate-Threshold Supplier (Oatly UK Ltd) -> 4,720 Q4 cases vs 5,000-case tier
  2. Margin-Leakage Supplier (GreenLeaf Foods) -> Purchase Invoices overcharge vs POs
  3. Multi-Category Supplier (Artisan Drinks Co) -> Spans 2 categories across Q3/Q4
  4. Long-Tail Supplier (Peak Snacks Ltd) -> 24 low-volume SKUs, no anomalies
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from erpnext_mock.db import (
    create_document,
    get_connection,
    init_db,
)


def _build_seed_payload() -> dict[str, list[dict[str, Any]]]:
    """Construct the deterministic graph-archetype retail dataset."""
    suppliers = [
        {
            "name": "Oatly UK Ltd",
            "supplier_name": "Oatly UK Ltd",
            "supplier_group": "Dairy & Alternatives",
            "country": "United Kingdom",
            "default_currency": "GBP",
            "archetype": "Rebate-Threshold",
        },
        {
            "name": "GreenLeaf Foods",
            "supplier_name": "GreenLeaf Foods",
            "supplier_group": "Health & Nutrition",
            "country": "United Kingdom",
            "default_currency": "GBP",
            "archetype": "Margin-Leakage",
        },
        {
            "name": "Artisan Drinks Co",
            "supplier_name": "Artisan Drinks Co",
            "supplier_group": "Beverages",
            "country": "United Kingdom",
            "default_currency": "GBP",
            "archetype": "Multi-Category",
        },
        {
            "name": "Peak Snacks Ltd",
            "supplier_name": "Peak Snacks Ltd",
            "supplier_group": "Snacks & Confectionery",
            "country": "United Kingdom",
            "default_currency": "GBP",
            "archetype": "Long-Tail",
        },
    ]

    items: list[dict[str, Any]] = [
        # --- Dairy Alternatives (Oatly UK Ltd) ---
        {"item_code": "OAT-BAR-1L", "item_name": "Oatly Barista Edition Oat Milk 1L (6x1L Case)", "item_group": "Dairy Alternatives", "stock_uom": "Case", "standard_rate": 11.40, "brand": "Oatly"},
        {"item_code": "OAT-ORG-1L", "item_name": "Oatly Organic Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "stock_uom": "Case", "standard_rate": 10.80, "brand": "Oatly"},
        {"item_code": "OAT-SKM-1L", "item_name": "Oatly Skinny Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "stock_uom": "Case", "standard_rate": 10.50, "brand": "Oatly"},
        {"item_code": "OAT-CHC-1L", "item_name": "Oatly Chocolate Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "stock_uom": "Case", "standard_rate": 12.00, "brand": "Oatly"},
        {"item_code": "OAT-WHP-250", "item_name": "Oatly Whippable Creamy Oat 250ml (12x250ml Case)", "item_group": "Dairy Alternatives", "stock_uom": "Case", "standard_rate": 13.20, "brand": "Oatly"},
        {"item_code": "OAT-CRM-250", "item_name": "Oatly Cooking Cream 250ml (12x250ml Case)", "item_group": "Dairy Alternatives", "stock_uom": "Case", "standard_rate": 11.90, "brand": "Oatly"},
        # --- Protein & Healthy Snacks (GreenLeaf Foods) ---
        {"item_code": "GLF-PRO-CHOC", "item_name": "GreenLeaf Plant Protein Bar Dark Choc (12x50g Case)", "item_group": "Protein & Healthy Snacks", "stock_uom": "Case", "standard_rate": 16.50, "brand": "GreenLeaf"},
        {"item_code": "GLF-PRO-PB", "item_name": "GreenLeaf Plant Protein Bar Peanut Butter (12x50g Case)", "item_group": "Protein & Healthy Snacks", "stock_uom": "Case", "standard_rate": 16.50, "brand": "GreenLeaf"},
        {"item_code": "GLF-PRO-BERRY", "item_name": "GreenLeaf Plant Protein Bar Berry Crunch (12x50g Case)", "item_group": "Protein & Healthy Snacks", "stock_uom": "Case", "standard_rate": 16.80, "brand": "GreenLeaf"},
        {"item_code": "GLF-GRAN-ALM", "item_name": "GreenLeaf Almond Chia Granola 400g (8x400g Case)", "item_group": "Protein & Healthy Snacks", "stock_uom": "Case", "standard_rate": 21.00, "brand": "GreenLeaf"},
        {"item_code": "GLF-BALL-CAC", "item_name": "GreenLeaf Cacao Energy Balls (18x40g Case)", "item_group": "Protein & Healthy Snacks", "stock_uom": "Case", "standard_rate": 14.40, "brand": "GreenLeaf"},
        # --- Cold Brew & Coffee + Sparkling & Kombucha (Artisan Drinks Co) ---
        {"item_code": "ART-CB-ORIG", "item_name": "Artisan Cold Brew Black 250ml (12x250ml Case)", "item_group": "Cold Brew & Coffee", "stock_uom": "Case", "standard_rate": 18.00, "brand": "Artisan"},
        {"item_code": "ART-CB-OAT", "item_name": "Artisan Cold Brew Oat Latte 250ml (12x250ml Case)", "item_group": "Cold Brew & Coffee", "stock_uom": "Case", "standard_rate": 19.50, "brand": "Artisan"},
        {"item_code": "ART-CB-VAN", "item_name": "Artisan Cold Brew Vanilla 250ml (12x250ml Case)", "item_group": "Cold Brew & Coffee", "stock_uom": "Case", "standard_rate": 19.50, "brand": "Artisan"},
        {"item_code": "ART-KMB-GNG", "item_name": "Artisan Ginger & Lemon Kombucha 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "stock_uom": "Case", "standard_rate": 15.60, "brand": "Artisan"},
        {"item_code": "ART-KMB-RSP", "item_name": "Artisan Raspberry Hibiscus Kombucha 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "stock_uom": "Case", "standard_rate": 15.60, "brand": "Artisan"},
        {"item_code": "ART-SPK-YUZ", "item_name": "Artisan Yuzu Botanical Sparkling 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "stock_uom": "Case", "standard_rate": 14.20, "brand": "Artisan"},
    ]

    # Add 24 Long-Tail SKUs for Peak Snacks Ltd so noise-filtering is realistic
    flavours = [
        "Sea Salt", "Cheddar & Onion", "Sweet Chilli", "Salt & Vinegar",
        "Smoked Paprika", "Rosemary & Thyme", "Truffle & Salt", "Lime & Pepper",
        "Roasted Garlic", "Aged Balsamic", "Jalapeno", "Maple Bacon",
    ]
    for idx, flavour in enumerate(flavours, start=1):
        items.append({
            "item_code": f"PEAK-CRP-{idx:02d}",
            "item_name": f"Peak Hand-Cooked Crisps {flavour} (24x40g Case)",
            "item_group": "Artisan Crisps & Savoury",
            "stock_uom": "Case",
            "standard_rate": 13.50 + (idx % 3) * 0.50,
            "brand": "Peak",
        })
        items.append({
            "item_code": f"PEAK-NUT-{idx:02d}",
            "item_name": f"Peak Roasted Nuts {flavour} (16x45g Case)",
            "item_group": "Artisan Crisps & Savoury",
            "stock_uom": "Case",
            "standard_rate": 17.00 + (idx % 4) * 0.60,
            "brand": "Peak",
        })

    purchase_orders = [
        # --- Oatly UK Ltd: Q3 baseline + Q4 2026 orders totaling 4,720 cases ---
        {
            "name": "PUR-ORD-2026-00001",
            "supplier": "Oatly UK Ltd",
            "transaction_date": "2026-08-14",
            "schedule_date": "2026-08-21",
            "status": "Completed",
            "items": [
                {"item_code": "OAT-BAR-1L", "item_name": "Oatly Barista Edition Oat Milk 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 1800, "uom": "Case", "rate": 11.40},
                {"item_code": "OAT-ORG-1L", "item_name": "Oatly Organic Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 700, "uom": "Case", "rate": 10.80},
            ],
        },
        {
            "name": "PUR-ORD-2026-00002",
            "supplier": "Oatly UK Ltd",
            "transaction_date": "2026-10-05",
            "schedule_date": "2026-10-12",
            "status": "Completed",
            "items": [
                {"item_code": "OAT-BAR-1L", "item_name": "Oatly Barista Edition Oat Milk 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 1600, "uom": "Case", "rate": 11.40},
                {"item_code": "OAT-ORG-1L", "item_name": "Oatly Organic Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 620, "uom": "Case", "rate": 10.80},
                {"item_code": "OAT-SKM-1L", "item_name": "Oatly Skinny Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 300, "uom": "Case", "rate": 10.50},
            ],
        },
        {
            "name": "PUR-ORD-2026-00003",
            "supplier": "Oatly UK Ltd",
            "transaction_date": "2026-11-03",
            "schedule_date": "2026-11-10",
            "status": "To Bill",
            "items": [
                {"item_code": "OAT-BAR-1L", "item_name": "Oatly Barista Edition Oat Milk 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 1500, "uom": "Case", "rate": 11.40},
                {"item_code": "OAT-CHC-1L", "item_name": "Oatly Chocolate Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 450, "uom": "Case", "rate": 12.00},
                {"item_code": "OAT-WHP-250", "item_name": "Oatly Whippable Creamy Oat 250ml (12x250ml Case)", "item_group": "Dairy Alternatives", "qty": 250, "uom": "Case", "rate": 13.20},
            ],
        },
        # --- GreenLeaf Foods: Q4 POs where later invoices overcharge ---
        {
            "name": "PUR-ORD-2026-00004",
            "supplier": "GreenLeaf Foods",
            "transaction_date": "2026-10-12",
            "schedule_date": "2026-10-18",
            "status": "Completed",
            "items": [
                {"item_code": "GLF-PRO-CHOC", "item_name": "GreenLeaf Plant Protein Bar Dark Choc (12x50g Case)", "item_group": "Protein & Healthy Snacks", "qty": 400, "uom": "Case", "rate": 16.50},
                {"item_code": "GLF-PRO-PB", "item_name": "GreenLeaf Plant Protein Bar Peanut Butter (12x50g Case)", "item_group": "Protein & Healthy Snacks", "qty": 300, "uom": "Case", "rate": 16.50},
            ],
        },
        {
            "name": "PUR-ORD-2026-00005",
            "supplier": "GreenLeaf Foods",
            "transaction_date": "2026-11-01",
            "schedule_date": "2026-11-08",
            "status": "Completed",
            "items": [
                {"item_code": "GLF-GRAN-ALM", "item_name": "GreenLeaf Almond Chia Granola 400g (8x400g Case)", "item_group": "Protein & Healthy Snacks", "qty": 250, "uom": "Case", "rate": 21.00},
                {"item_code": "GLF-BALL-CAC", "item_name": "GreenLeaf Cacao Energy Balls (18x40g Case)", "item_group": "Protein & Healthy Snacks", "qty": 200, "uom": "Case", "rate": 14.40},
            ],
        },
        # --- Artisan Drinks Co: Multi-category Q3 & Q4 POs ---
        {
            "name": "PUR-ORD-2026-00006",
            "supplier": "Artisan Drinks Co",
            "transaction_date": "2026-09-10",
            "schedule_date": "2026-09-17",
            "status": "Completed",
            "items": [
                {"item_code": "ART-CB-ORIG", "item_name": "Artisan Cold Brew Black 250ml (12x250ml Case)", "item_group": "Cold Brew & Coffee", "qty": 500, "uom": "Case", "rate": 18.00},
                {"item_code": "ART-KMB-GNG", "item_name": "Artisan Ginger & Lemon Kombucha 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "qty": 450, "uom": "Case", "rate": 15.60},
            ],
        },
        {
            "name": "PUR-ORD-2026-00007",
            "supplier": "Artisan Drinks Co",
            "transaction_date": "2026-10-20",
            "schedule_date": "2026-10-27",
            "status": "Completed",
            "items": [
                {"item_code": "ART-CB-OAT", "item_name": "Artisan Cold Brew Oat Latte 250ml (12x250ml Case)", "item_group": "Cold Brew & Coffee", "qty": 650, "uom": "Case", "rate": 19.50},
                {"item_code": "ART-KMB-RSP", "item_name": "Artisan Raspberry Hibiscus Kombucha 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "qty": 550, "uom": "Case", "rate": 15.60},
                {"item_code": "ART-SPK-YUZ", "item_name": "Artisan Yuzu Botanical Sparkling 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "qty": 400, "uom": "Case", "rate": 14.20},
            ],
        },
        # --- Peak Snacks Ltd: Long-tail low volume ---
        {
            "name": "PUR-ORD-2026-00008",
            "supplier": "Peak Snacks Ltd",
            "transaction_date": "2026-10-28",
            "schedule_date": "2026-11-04",
            "status": "Completed",
            "items": [
                {"item_code": "PEAK-CRP-01", "item_name": "Peak Hand-Cooked Crisps Sea Salt (24x40g Case)", "item_group": "Artisan Crisps & Savoury", "qty": 80, "uom": "Case", "rate": 14.00},
                {"item_code": "PEAK-CRP-02", "item_name": "Peak Hand-Cooked Crisps Cheddar & Onion (24x40g Case)", "item_group": "Artisan Crisps & Savoury", "qty": 60, "uom": "Case", "rate": 14.50},
                {"item_code": "PEAK-NUT-01", "item_name": "Peak Roasted Nuts Sea Salt (16x45g Case)", "item_group": "Artisan Crisps & Savoury", "qty": 50, "uom": "Case", "rate": 17.60},
            ],
        },
    ]

    purchase_invoices = [
        # --- Oatly UK Ltd: Clean invoice matching PO ---
        {
            "name": "ACC-PINV-2026-00001",
            "supplier": "Oatly UK Ltd",
            "posting_date": "2026-10-14",
            "due_date": "2026-11-13",
            "status": "Paid",
            "purchase_order": "PUR-ORD-2026-00002",
            "items": [
                {"item_code": "OAT-BAR-1L", "item_name": "Oatly Barista Edition Oat Milk 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 1600, "uom": "Case", "rate": 11.40, "purchase_order": "PUR-ORD-2026-00002"},
                {"item_code": "OAT-ORG-1L", "item_name": "Oatly Organic Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 620, "uom": "Case", "rate": 10.80, "purchase_order": "PUR-ORD-2026-00002"},
                {"item_code": "OAT-SKM-1L", "item_name": "Oatly Skinny Oat Drink 1L (6x1L Case)", "item_group": "Dairy Alternatives", "qty": 300, "uom": "Case", "rate": 10.50, "purchase_order": "PUR-ORD-2026-00002"},
            ],
        },
        # --- GreenLeaf Foods: Overcharged on GLF-PRO-CHOC (+£1.50/case * 400 = £600) and GLF-PRO-PB (+£1.20/case * 300 = £360) ---
        {
            "name": "ACC-PINV-2026-00002",
            "supplier": "GreenLeaf Foods",
            "posting_date": "2026-10-20",
            "due_date": "2026-11-19",
            "status": "Unpaid",
            "purchase_order": "PUR-ORD-2026-00004",
            "items": [
                {"item_code": "GLF-PRO-CHOC", "item_name": "GreenLeaf Plant Protein Bar Dark Choc (12x50g Case)", "item_group": "Protein & Healthy Snacks", "qty": 400, "uom": "Case", "rate": 18.00, "purchase_order": "PUR-ORD-2026-00004"},
                {"item_code": "GLF-PRO-PB", "item_name": "GreenLeaf Plant Protein Bar Peanut Butter (12x50g Case)", "item_group": "Protein & Healthy Snacks", "qty": 300, "uom": "Case", "rate": 17.70, "purchase_order": "PUR-ORD-2026-00004"},
            ],
        },
        # --- GreenLeaf Foods: Overcharged on GLF-GRAN-ALM (+£2.00/case * 250 = £500) -> Total leakage = £1,460 ---
        {
            "name": "ACC-PINV-2026-00003",
            "supplier": "GreenLeaf Foods",
            "posting_date": "2026-11-09",
            "due_date": "2026-12-09",
            "status": "Unpaid",
            "purchase_order": "PUR-ORD-2026-00005",
            "items": [
                {"item_code": "GLF-GRAN-ALM", "item_name": "GreenLeaf Almond Chia Granola 400g (8x400g Case)", "item_group": "Protein & Healthy Snacks", "qty": 250, "uom": "Case", "rate": 23.00, "purchase_order": "PUR-ORD-2026-00005"},
                {"item_code": "GLF-BALL-CAC", "item_name": "GreenLeaf Cacao Energy Balls (18x40g Case)", "item_group": "Protein & Healthy Snacks", "qty": 200, "uom": "Case", "rate": 14.40, "purchase_order": "PUR-ORD-2026-00005"},
            ],
        },
        # --- Artisan Drinks Co: Clean invoice ---
        {
            "name": "ACC-PINV-2026-00004",
            "supplier": "Artisan Drinks Co",
            "posting_date": "2026-10-29",
            "due_date": "2026-11-28",
            "status": "Unpaid",
            "purchase_order": "PUR-ORD-2026-00007",
            "items": [
                {"item_code": "ART-CB-OAT", "item_name": "Artisan Cold Brew Oat Latte 250ml (12x250ml Case)", "item_group": "Cold Brew & Coffee", "qty": 650, "uom": "Case", "rate": 19.50, "purchase_order": "PUR-ORD-2026-00007"},
                {"item_code": "ART-KMB-RSP", "item_name": "Artisan Raspberry Hibiscus Kombucha 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "qty": 550, "uom": "Case", "rate": 15.60, "purchase_order": "PUR-ORD-2026-00007"},
                {"item_code": "ART-SPK-YUZ", "item_name": "Artisan Yuzu Botanical Sparkling 330ml (12x330ml Case)", "item_group": "Sparkling & Kombucha", "qty": 400, "uom": "Case", "rate": 14.20, "purchase_order": "PUR-ORD-2026-00007"},
            ],
        },
    ]

    return {
        "Supplier": suppliers,
        "Item": items,
        "Purchase Order": purchase_orders,
        "Purchase Invoice": purchase_invoices,
    }


def reset_and_seed(
    db_path: Path | None = None, payload: dict[str, list[dict[str, Any]]] | None = None
) -> dict[str, int]:
    """Clear existing tables and populate the database with seed or imported JSON data."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        for table in (
            "tabPurchaseInvoiceItem",
            "tabPurchaseInvoice",
            "tabPurchaseOrderItem",
            "tabPurchaseOrder",
            "tabItem",
            "tabSupplier",
        ):
            conn.execute(f"DELETE FROM {table}")

    data = payload or _build_seed_payload()
    counts: dict[str, int] = {}
    for doctype in ("Supplier", "Item", "Purchase Order", "Purchase Invoice"):
        docs = data.get(doctype, [])
        for doc in docs:
            create_document(doctype, doc, db_path)
        counts[doctype] = len(docs)
    return counts


def seed_if_empty(db_path: Path | None = None) -> dict[str, int] | None:
    """Seed the database only if tabSupplier is currently empty."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT COUNT(*) AS cnt FROM tabSupplier").fetchone()
        if int(row["cnt"]) > 0:
            return None
    return reset_and_seed(db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or export/import ERPNext mock data.")
    parser.add_argument("--export-json", type=Path, help="Export the seed dataset to a JSON file.")
    parser.add_argument("--import-json", type=Path, help="Import a JSON dataset into SQLite.")
    args = parser.parse_args()

    if args.export_json:
        payload = _build_seed_payload()
        args.export_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Exported mock dataset to {args.export_json}")
        return

    if args.import_json:
        payload = json.loads(args.import_json.read_text(encoding="utf-8"))
        counts = reset_and_seed(payload=payload)
        print(f"Imported dataset: {counts}")
        return

    counts = reset_and_seed()
    print(f"Seeded ERPNext mock database: {counts}")


if __name__ == "__main__":
    main()
