import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import requests

BASE = {
    "demo": "https://cdn-ind.testnet.deltaex.org",
    "live": "https://api.india.delta.exchange",
}

RESOLUTION_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "6h": 21600,
    "12h": 43200,
    "1d": 86400,
    "1w": 604800,
}


class DeltaAPIError(RuntimeError):
    pass


class DeltaClient:
    def __init__(self, key=None, secret=None, env="demo"):
        if env not in BASE:
            raise ValueError("Invalid Delta environment; use demo or live")
        self.base = BASE[env]
        self.environment = env
        self.key = key
        self.secret = secret
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "delta-ai-platform/2.2",
            "Accept": "application/json",
        })

    def _headers(self, method, path, query="", body=""):
        if not self.key or not self.secret:
            raise ValueError("Delta API credentials are missing")
        timestamp = str(int(time.time()))
        prehash = method.upper() + timestamp + path + query + body
        signature = hmac.new(
            self.secret.encode("utf-8"),
            prehash.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "api-key": self.key,
            "timestamp": timestamp,
            "signature": signature,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _parse(response):
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            body = response.text[:500]
            raise DeltaAPIError(
                f"Delta API HTTP {response.status_code}: {body}"
            ) from exc

        try:
            payload = response.json()
        except ValueError as exc:
            raise DeltaAPIError("Delta API returned invalid JSON") from exc

        if isinstance(payload, dict):
            if payload.get("success") is False:
                raise DeltaAPIError(str(payload.get("error") or payload))
            if "result" in payload:
                return payload["result"]
        return payload

    def public(self, path, params=None):
        try:
            response = self.session.get(
                self.base + path,
                params=params or {},
                timeout=(5, 25),
            )
            return self._parse(response)
        except requests.RequestException as exc:
            raise DeltaAPIError(f"Could not reach Delta Exchange: {exc}") from exc

    def private(self, method, path, params=None, body=None):
        params = params or {}
        query = "?" + urlencode(params) if params else ""
        body_text = (
            json.dumps(body, separators=(",", ":"), ensure_ascii=False)
            if body is not None else ""
        )
        headers = self._headers(method, path, query, body_text)
        try:
            response = self.session.request(
                method.upper(),
                self.base + path + query,
                headers=headers,
                data=body_text if body is not None else None,
                timeout=(5, 25),
            )
            return self._parse(response)
        except requests.RequestException as exc:
            raise DeltaAPIError(f"Delta private API request failed: {exc}") from exc

    def products(self):
        return self.public("/v2/products", {"page_size": 100})

    def tickers(self):
        return self.public("/v2/tickers")

    def candles(self, symbol, resolution="15m", limit=250):
        if resolution not in RESOLUTION_SECONDS:
            raise ValueError(f"Unsupported resolution: {resolution}")
        symbol = str(symbol).strip().upper()
        if not symbol:
            raise ValueError("Symbol is required")
        limit = min(max(int(limit), 60), 500)
        end = int(time.time())
        start = end - RESOLUTION_SECONDS[resolution] * limit
        return self.public(
            "/v2/history/candles",
            {
                "symbol": symbol,
                "resolution": resolution,
                "start": start,
                "end": end,
            },
        )

    def wallet(self):
        return self.private("GET", "/v2/wallet/balances")

    def positions(self):
        return self.private("GET", "/v2/positions")
