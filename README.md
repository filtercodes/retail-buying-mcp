# Retail Buying MCP & ERPNext Mock

Lightweight FastAPI + SQLite mock of ERPNext REST endpoints paired with a FastMCP tool server (`stdio`, `streamable-http`, `sse`).

## Components

- `erpnext_mock/`: FastAPI server exposing `/api/resource/{Item,Supplier,Purchase Order,Purchase Invoice}` and `/api/method/ping`. Auto-seeds `erpnext_mock.db` on startup if empty.
- `mcp_server/`: FastMCP server exposing `get_buying_overview`, `get_supplier_graph_summary`, `drill_down_skus`, `evaluate_rebate_deal`, `detect_invoice_leakage`, `propose_erp_action`, and `confirm_erp_action`.

## Setup

```bash
conda activate agentic_rpi
pip install -r requirements.txt
```

## Run

1. Start the ERPNext mock server (port 8000):

```bash
uvicorn erpnext_mock.main:app --host 127.0.0.1 --port 8000
```

2. Start the MCP server:

```bash
# Streamable HTTP (default port 8001)
python -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8001

# SSE
python -m mcp_server.server --transport sse --host 127.0.0.1 --port 8001

# Stdio
python -m mcp_server.server --transport stdio
```

Environment variables (optional): `ERPNEXT_BASE_URL` (default `http://127.0.0.1:8000`), `ERPNEXT_MOCK_DB` (SQLite path).

## Mock Data

```bash
python -m erpnext_mock.seed --export-json sample_data.json
python -m erpnext_mock.seed --import-json sample_data.json
```

## Tests

```bash
pytest -v
```
