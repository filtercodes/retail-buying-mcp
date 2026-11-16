"""Async HTTP client for ERPNext /api/resource endpoints."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

import httpx


class ERPNextClient:
    """Lightweight async wrapper around ERPNext REST resource endpoints."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = (
            base_url or os.environ.get("ERPNEXT_BASE_URL") or "http://127.0.0.1:8000"
        ).rstrip("/")
        self.token = token or os.environ.get("ERPNEXT_TOKEN")
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        return headers

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=10.0,
            transport=self._transport,
        )

    async def list_docs(
        self,
        doctype: str,
        fields: list[str] | None = None,
        filters: list[Any] | dict[str, Any] | None = None,
        limit_page_length: int = 200,
    ) -> list[dict[str, Any]]:
        """Call GET /api/resource/{DocType}."""
        params: dict[str, Any] = {"limit_page_length": limit_page_length}
        if fields is not None:
            params["fields"] = json.dumps(fields)
        if filters is not None:
            params["filters"] = json.dumps(filters)

        async with self._client() as client:
            resp = await client.get(f"/api/resource/{quote(doctype)}", params=params)
            resp.raise_for_status()
            return resp.json().get("data", [])

    async def get_doc(self, doctype: str, name: str) -> dict[str, Any]:
        """Call GET /api/resource/{DocType}/{name}."""
        async with self._client() as client:
            resp = await client.get(f"/api/resource/{quote(doctype)}/{quote(name)}")
            resp.raise_for_status()
            return resp.json()["data"]

    async def create_doc(self, doctype: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Call POST /api/resource/{DocType}."""
        async with self._client() as client:
            resp = await client.post(f"/api/resource/{quote(doctype)}", json=payload)
            resp.raise_for_status()
            return resp.json()["data"]

    async def update_doc(
        self, doctype: str, name: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Call PUT /api/resource/{DocType}/{name}."""
        async with self._client() as client:
            resp = await client.put(
                f"/api/resource/{quote(doctype)}/{quote(name)}", json=payload
            )
            resp.raise_for_status()
            return resp.json()["data"]
