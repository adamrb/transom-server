"""Client for Plaud's partner authentication API.

Flow (see https://docs.plaud.ai):
  1. POST /oauth/partner/access-token          (Basic client_id:secret_key)
  2. POST /oauth/partner/access-token/refresh  (Basic auth, refresh_token form field)
  3. POST /open/partner/users/access-token     (Bearer partner token) -> user token

The user token is what the Plaud Embedded SDK on the phone needs. Only the
auth handshake touches Plaud's cloud; audio never does.
"""

import asyncio
import logging
import time

import httpx

log = logging.getLogger("transom.plaud")


class PlaudAuthError(Exception):
    pass


class PlaudClient:
    def __init__(self, api_base: str, client_id: str, secret_key: str):
        self._api_base = api_base.rstrip("/")
        self._client_id = client_id
        self._secret_key = secret_key
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._expires_at: float = 0
        self._lock = asyncio.Lock()

    async def _fetch_partner_token(self, client: httpx.AsyncClient) -> None:
        auth = (self._client_id, self._secret_key)
        url = f"{self._api_base}/oauth/partner/access-token"
        data = {}
        if self._refresh_token:
            url = f"{self._api_base}/oauth/partner/access-token/refresh"
            data = {"refresh_token": self._refresh_token}
        resp = await client.post(url, auth=auth, data=data)
        if resp.status_code != 200 and self._refresh_token:
            # Refresh token expired/invalid: fall back to a fresh grant.
            log.info("partner token refresh failed (%s), re-authenticating", resp.status_code)
            self._refresh_token = None
            resp = await client.post(
                f"{self._api_base}/oauth/partner/access-token", auth=auth, data={}
            )
        if resp.status_code != 200:
            raise PlaudAuthError(f"partner token request failed: {resp.status_code} {resp.text[:300]}")
        body = resp.json()
        self._access_token = body["access_token"]
        self._refresh_token = body.get("refresh_token")
        self._expires_at = time.time() + int(body.get("expires_in", 3600))

    async def get_user_token(self, user_id: str, expires_in: int = 86400) -> dict:
        async with self._lock:
            async with httpx.AsyncClient(timeout=30) as client:
                if not self._access_token or time.time() > self._expires_at - 120:
                    await self._fetch_partner_token(client)
                resp = await client.post(
                    f"{self._api_base}/open/partner/users/access-token",
                    headers={"Authorization": f"Bearer {self._access_token}"},
                    json={"user_id": user_id, "expires_in": expires_in},
                )
                if resp.status_code == 401:
                    # Partner token revoked out from under us; retry once fresh.
                    self._access_token = None
                    await self._fetch_partner_token(client)
                    resp = await client.post(
                        f"{self._api_base}/open/partner/users/access-token",
                        headers={"Authorization": f"Bearer {self._access_token}"},
                        json={"user_id": user_id, "expires_in": expires_in},
                    )
                if resp.status_code != 200:
                    raise PlaudAuthError(
                        f"user token request failed: {resp.status_code} {resp.text[:300]}"
                    )
                return resp.json()
