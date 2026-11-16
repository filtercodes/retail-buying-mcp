# Retail Buying MCP & Lightweight ERPNext Mock

A zero-MariaDB, SQLite-backed FastAPI mock of ERPNext's REST endpoints paired with a voice-optimized **FastMCP** server (`stdio` and `streamable-http` / `sse`).

## Quick Start (using `agentic_rpi` conda environment)

### 1. Start the ERPNext Mock Server (Port 8000)
```bash
cd /Users/stefm1/test/CRM_ERP_HRIS/retail-buying-mcp
/Users/stefm1/anaconda3/envs/agentic_rpi/bin/uvicorn erpnext_mock.main:app --host 127.0.0.1 --port 8000
```
On first startup, it automatically creates `erpnext_mock.db` and seeds the 4 graph-archetype suppliers, 41 SKUs, Purchase Orders, and Purchase Invoices.

### 2. Start the MCP Server (for your Voice Agent)
- **Streamable HTTP / SSE (for network/voice agent clients):**
  ```bash
  /Users/stefm1/anaconda3/envs/agentic_rpi/bin/python -m mcp_server.server --transport streamable-http --host 127.0.0.1 --port 8001
  ```
  *(Or `--transport sse` if your client uses legacy SSE.)*
- **Stdio (for local MCP hosts):**
  ```bash
  /Users/stefm1/anaconda3/envs/agentic_rpi/bin/python -m mcp_server.server --transport stdio
  ```

### 3. Export / Import Mock Data
```bash
/Users/stefm1/anaconda3/envs/agentic_rpi/bin/python -m erpnext_mock.seed --export-json sample_data.json
/Users/stefm1/anaconda3/envs/agentic_rpi/bin/python -m erpnext_mock.seed --import-json sample_data.json
```

### 4. Run Tests
```bash
/Users/stefm1/anaconda3/envs/agentic_rpi/bin/pytest -v
```
