from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from .const import DEFAULT_TIMEOUT_SECONDS

PROTECT_EVENTS_REQUEST_LIMIT = 100


class ProtectApiError(Exception):
    """Generic Protect API failure."""


class ProtectAuthError(ProtectApiError):
    """Protect authentication failure."""


class ProtectApiClient:
    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        verify_ssl: bool,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = _normalize_base_url(host)
        self._username = username
        self._password = password
        self._verify_ssl = verify_ssl
        self._timeout_seconds = timeout_seconds
        self._session: aiohttp.ClientSession | None = None
        self._csrf_token: str | None = None

    async def async_setup(self) -> None:
        await self._async_ensure_session()
        await self.async_login()

    async def async_close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._csrf_token = None

    async def async_login(self) -> None:
        await self._async_ensure_session()
        assert self._session is not None

        async with self._session.post(
            f"{self._base_url}/api/auth/login",
            json={
                "username": self._username,
                "password": self._password,
            },
        ) as response:
            if response.status in {401, 403}:
                raise ProtectAuthError(f"Protect authentication failed with {response.status}")
            if response.status >= 400:
                text = await response.text()
                raise ProtectApiError(
                    f"Protect login failed: {response.status} {text[:200]}"
                )
            self._csrf_token = response.headers.get("X-Csrf-Token")
            await response.text()

    async def async_get_bootstrap(self) -> dict[str, Any]:
        response = await self._async_request("GET", "/proxy/protect/api/bootstrap")
        return response if isinstance(response, dict) else {}

    async def async_get_automations(self) -> list[dict[str, Any]]:
        response = await self._async_request("GET", "/proxy/protect/api/automations")
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        return []

    async def async_get_events(
        self,
        *,
        limit: int = PROTECT_EVENTS_REQUEST_LIMIT,
        offset: int | None = None,
        types: list[str] | None = None,
        sorting: str = "desc",
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "limit": max(1, min(int(limit), PROTECT_EVENTS_REQUEST_LIMIT)),
            "orderDirection": sorting.upper(),
            "withoutDescriptions": "true",
        }
        if offset is not None:
            params["offset"] = max(0, int(offset))
        if types:
            params["types"] = types

        response = await self._async_request(
            "GET",
            "/proxy/protect/api/events",
            params=params,
        )
        if isinstance(response, list):
            return [item for item in response if isinstance(item, dict)]
        return []

    async def async_create_automation(self, payload: dict[str, Any]) -> dict[str, Any]:
        response = await self._async_request(
            "POST",
            "/proxy/protect/api/automations",
            payload=payload,
        )
        return response if isinstance(response, dict) else {}

    async def async_delete_automation(self, automation_id: str) -> None:
        await self._async_request("DELETE", f"/proxy/protect/api/automations/{automation_id}")

    async def _async_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        params: Mapping[str, Any] | None = None,
        allow_reauth: bool = True,
    ) -> Any:
        await self._async_ensure_session()
        assert self._session is not None

        headers = {}
        if method.upper() not in {"GET", "HEAD", "OPTIONS"} and self._csrf_token:
            headers["X-Csrf-Token"] = self._csrf_token

        async with self._session.request(
            method,
            f"{self._base_url}{path}",
            json=payload,
            params=params,
            headers=headers,
        ) as response:
            if response.status in {401, 403}:
                if allow_reauth:
                    await self.async_login()
                    return await self._async_request(
                        method,
                        path,
                        payload=payload,
                        params=params,
                        allow_reauth=False,
                    )
                raise ProtectAuthError(f"Protect authentication failed with {response.status}")

            if response.status >= 400:
                text = await response.text()
                raise ProtectApiError(
                    f"Protect API request failed: {response.status} {text[:200]}"
                )

            if response.status == 204:
                return None

            text = await response.text()
            if not text.strip():
                return None

            try:
                return json.loads(text)
            except json.JSONDecodeError as err:
                raise ProtectApiError(
                    f"Protect API returned invalid JSON for {path}"
                ) from err

    async def _async_ensure_session(self) -> None:
        if self._session is not None:
            return
        connector = (
            aiohttp.TCPConnector()
            if self._verify_ssl
            else aiohttp.TCPConnector(ssl=False)
        )
        self._session = aiohttp.ClientSession(
            connector=connector,
            cookie_jar=aiohttp.CookieJar(unsafe=True),
            timeout=aiohttp.ClientTimeout(total=self._timeout_seconds),
        )


def _normalize_base_url(host: str) -> str:
    text = host.strip()
    if "://" not in text:
        text = f"https://{text}"
    parsed = urlsplit(text)
    if not parsed.scheme or not parsed.netloc:
        raise ProtectApiError(f"Invalid Protect host: {host}")
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
