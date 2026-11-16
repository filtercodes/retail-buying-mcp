# Project Plan: Retail Buying MCP & Lightweight ERPNext Mock

## 1. Objective
Build a lightweight, zero-MariaDB backend and **Model Context Protocol (MCP)** tool server tailored for an **existing voice agent** front end. The system mimics ERPNext's exact REST resource APIs using **FastAPI + SQLite** and exposes **voice-optimized, graph-aggregated buying tools** over MCP (`stdio` and `streamable-http` / `sse`).

---

## 2. Prototype Assessment & Unified Direction
We evaluated three retail-buying prototype concepts and unified them into a single voice-first MCP architecture:

1. **Email / Voice-to-ERP Rebate Engine**
   - Evaluates supplier rebate terms (e.g., *"5,000 cases of Oat Milk in Q4 for a 4% retroactive rebate + £2,000 promo"*).
   - Validates SKUs/categories against ERPNext Item Master, flags ambiguous terms (e.g., Calendar Q4 vs. Fiscal Q4), and calculates exact £ rebate owed and gap-to-threshold from Purchase Orders.
2. **Contract Drift & Invoice Leakage Detector**
   - Cross-checks `Purchase Invoice` line-item unit rates against `Purchase Order` unit rates.
   - Surfaces exact £ overcharges per supplier and SKU for dispute resolution.
3. **Retail Buying MCP Server (Primary Integration Layer)**
   - Wraps ERPNext reads and human-in-the-loop gated writes as typed MCP tools so the existing voice agent's LLM can call them with minimal friction.

---

## 3. System Architecture

```text
+-----------------------+        MCP (stdio or HTTP/SSE)        +-------------------------+
|  Existing Voice Agent | <-----------------------------------> |  mcp_server/server.py   |
|  (STT / LLM / TTS)    |                                       |  (FastMCP Tool Layer)   |
+-----------------------+                                       +------------+------------+
                                                                             |
                                                                HTTP REST (/api/resource/...)
                                                                             |
                                                                             v
                                                                +-------------------------+
                                                                |  erpnext_mock/main.py   |
                                                                |  (FastAPI + SQLite)     |
                                                                +-------------------------+
```

### Layer A: ERPNext Mock REST Server (`erpnext_mock/`)
- **Endpoints:**
  - `GET /api/resource/{DocType}` (supports `fields`, `filters`, `order_by`, `limit_start`, `limit_page_length`, returning `{"data": [...]}`)
  - `GET /api/resource/{DocType}/{name}` (returns full document + child `items` table)
  - `POST /api/resource/{DocType}`
  - `PUT /api/resource/{DocType}/{name}`
  - `DELETE /api/resource/{DocType}/{name}`
  - `GET /api/method/ping`
- **Supported DocTypes:** `Item`, `Supplier`, `Purchase Order`, `Purchase Invoice`.

### Layer B: Voice-Ready MCP Server (`mcp_server/`)
- **Transports:** Supports both `stdio` and `streamable-http` / `sse` via CLI flags (`--transport`).
- **Voice-First Design Rules:**
  - Every tool returns concise structured data plus a `voice_summary` string so the LLM does not read raw JSON arrays aloud.
  - Lists are capped (top-N) and aggregated by default; SKU-level detail is only returned on explicit drill-down.
  - Write actions use a two-step human-in-the-loop gate: `propose_erp_action` -> `confirm_erp_action`.

---

## 4. Graph Archetypes & Voice-First Data Grouping
A voice chatbot cannot recite 500 individual SKUs. The dataset (`erpnext_mock/seed.py`) models a **3-level hierarchy + anomaly edges** (`Supplier -> Item Group -> SKU -> Purchase Order -> Purchase Invoice`) grouped into **4 realistic supplier archetypes**:

1. **Rebate-Threshold (`Oatly UK Ltd`)**
   - Category: `Dairy Alternatives`
   - Q4 2026 PO volume: 4,720 cases (280 cases shy of a 5,000-case 4% retroactive rebate tier).
2. **Margin-Leakage (`GreenLeaf Foods`)**
   - Category: `Protein & Healthy Snacks`
   - Unpaid `Purchase Invoice` lines bill above `Purchase Order` unit prices (exact £1,460 overcharge across 3 SKUs).
3. **Multi-Category (`Artisan Drinks Co`)**
   - Categories: `Cold Brew & Coffee` and `Sparkling & Kombucha` across Q3 & Q4 2026.
   - Demonstrates category-level voice rollups.
4. **Long-Tail (`Peak Snacks Ltd`)**
   - Category: `Artisan Crisps & Savoury` (24 low-volume SKUs, no anomalies).
   - Demonstrates noise filtering in voice summaries.

`erpnext_mock/seed.py` also supports `--export-json` and `--import-json` for downloading/swapping mock datasets.

---

## 5. Planned MCP Tools
1. `get_buying_overview(period?)` — Portfolio pulse: total spend, top suppliers, and flagged anomalies (leakage + near-threshold rebates).
2. `get_supplier_graph_summary(supplier_query, period?)` — Aggregates a supplier's volume and spend by `Item Group`.
3. `drill_down_skus(supplier_query?, item_group?, limit=5)` — Top-N SKU lookup when the user asks for SKU-level detail.
4. `evaluate_rebate_deal(supplier_query, item_group_or_sku, min_cases, rebate_pct, fixed_promo_gbp, period)` — Validates scope, flags ambiguous periods (e.g., `"Q4"` calendar vs. fiscal), and calculates exact £ rebate and gap-to-threshold.
5. `detect_invoice_leakage(supplier_query?)` — Compares `Purchase Invoice` unit rates vs. `Purchase Order` rates and returns exact £ overcharges.
6. `propose_erp_action(action_type, supplier, summary, payload)` — Stages a write action and returns a `proposal_id` + confirmation prompt.
7. `confirm_erp_action(proposal_id)` — Commits the approved action to the ERPNext mock server.

---

## 6. Environment & Dependencies
- **Conda Environment:** `agentic_rpi` (`/Users/stefm1/anaconda3/envs/agentic_rpi`)
- **Pinned Compatible Versions:**
  - `fastapi==0.118.0`
  - `starlette==0.48.0`
  - `pydantic==2.11.9`
  - `mcp==1.30.0` (pinned `<2.0.0` to preserve `starlette<0.49` and `pydantic<2.12` compatibility)
  - `httpx==0.28.1`, `uvicorn==0.37.0`

---

## 7. Implementation Checklist
- [x] `requirements.txt`
- [x] `pyproject.toml`
- [x] `erpnext_mock/db.py` (SQLite schema + Frappe REST query parser)
- [x] `erpnext_mock/seed.py` (4 graph archetypes + JSON export/import)
- [x] `erpnext_mock/main.py` (FastAPI REST server)
- [x] `mcp_server/client.py` (Async ERPNext REST client)
- [x] `mcp_server/analytics.py` (Graph rollups, rebate math, invoice leakage, proposal gate)
- [x] `mcp_server/server.py` (FastMCP server with `stdio` & `streamable-http` / `sse`)
- [x] `tests/test_end_to_end.py` & `README.md` (Verified: `2 passed in 0.37s` in `agentic_rpi`)

---

## 8. Current Status & Next Steps
- **Completed:** Mock ERPNext REST API, graph-archetype seed data, voice-optimized MCP tool server, and end-to-end tests are implemented and passing.
- **Next:** Start the FastAPI server (`port 8000`) and MCP server (`stdio` or `streamable-http` on `port 8001`), then connect your existing voice agent to test live voice queries.
