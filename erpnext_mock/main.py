"""FastAPI mock server mimicking ERPNext REST endpoints (/api/resource/...)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from erpnext_mock.db import (
    DOCTYPE_CONFIG,
    create_document,
    delete_document,
    get_document,
    list_documents,
    update_document,
)
from erpnext_mock.seed import seed_if_empty


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize SQLite schema and seed sample graph-archetype data if empty."""
    seed_if_empty()
    yield


app = FastAPI(
    title="ERPNext Lightweight Mock API",
    version="0.1.0",
    description="SQLite-backed FastAPI mock of ERPNext /api/resource endpoints.",
    lifespan=lifespan,
)


def _validate_doctype(doctype: str) -> None:
    if doctype not in DOCTYPE_CONFIG:
        raise HTTPException(
            status_code=404,
            detail={
                "exc_type": "DoesNotExistError",
                "exception": f"DocType {doctype} not found",
            },
        )


@app.get("/api/method/ping")
async def ping() -> dict[str, str]:
    """Frappe-compatible health check endpoint."""
    return {"message": "pong"}


@app.get("/api/resource/{doctype}")
async def list_resource(
    doctype: str,
    fields: str | None = Query(default=None, description="JSON list of fields"),
    filters: str | None = Query(default=None, description="JSON list/dict of filters"),
    order_by: str | None = Query(default=None, description="e.g. 'creation desc'"),
    limit_start: int = Query(default=0, ge=0),
    limit_page_length: int = Query(default=20, ge=0),
) -> dict[str, list[dict[str, Any]]]:
    """List documents for a DocType matching optional Frappe filters and fields."""
    _validate_doctype(doctype)
    try:
        rows = list_documents(
            doctype=doctype,
            fields=fields,
            filters=filters,
            order_by=order_by,
            limit_start=limit_start,
            limit_page_length=limit_page_length,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"data": rows}


@app.get("/api/resource/{doctype}/{name}")
async def get_resource(doctype: str, name: str) -> dict[str, dict[str, Any]]:
    """Fetch a single document by name, including child items."""
    _validate_doctype(doctype)
    doc = get_document(doctype, name)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={
                "exc_type": "DoesNotExistError",
                "exception": f"{doctype} {name} not found",
            },
        )
    return {"data": doc}


@app.post("/api/resource/{doctype}")
async def create_resource(doctype: str, request: Request) -> dict[str, dict[str, Any]]:
    """Create a new document in SQLite."""
    _validate_doctype(doctype)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    try:
        created = create_document(doctype, payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"data": created}


@app.put("/api/resource/{doctype}/{name}")
async def update_resource(
    doctype: str, name: str, request: Request
) -> dict[str, dict[str, Any]]:
    """Update an existing document by name."""
    _validate_doctype(doctype)
    payload = await request.json()
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")
    updated = update_document(doctype, name, payload)
    if not updated:
        raise HTTPException(
            status_code=404,
            detail={
                "exc_type": "DoesNotExistError",
                "exception": f"{doctype} {name} not found",
            },
        )
    return {"data": updated}


@app.delete("/api/resource/{doctype}/{name}")
async def delete_resource(doctype: str, name: str) -> JSONResponse:
    """Delete a document by name."""
    _validate_doctype(doctype)
    deleted = delete_document(doctype, name)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "exc_type": "DoesNotExistError",
                "exception": f"{doctype} {name} not found",
            },
        )
    return JSONResponse(content={"message": "ok"})
