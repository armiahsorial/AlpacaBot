"""Client for Alpaca paper trading and stock market data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from trading_bot.config import AlpacaSettings
from trading_bot.market_data import MarketDataError

ORDER_SIDES = ("buy", "sell")
ORDER_TYPES = ("market", "limit", "stop", "stop_limit", "trailing_stop")
TIME_IN_FORCE = ("day", "gtc", "opg", "cls", "ioc", "fok")


class AlpacaApiError(MarketDataError):
    """Raised when Alpaca returns an error or invalid response."""


@dataclass(frozen=True)
class PaperOrderRequest:
    symbol: str
    side: str
    qty: float | None = None
    notional: float | None = None
    type: str = "market"
    time_in_force: str = "day"
    limit_price: float | None = None
    stop_price: float | None = None
    client_order_id: str | None = None

    def as_payload(self) -> dict[str, Any]:
        symbol = self.symbol.strip().upper()
        side = self.side.strip().lower()
        order_type = self.type.strip().lower()
        time_in_force = self.time_in_force.strip().lower()

        if not symbol:
            raise ValueError("symbol is required.")
        if side not in ORDER_SIDES:
            raise ValueError(f"side must be one of: {', '.join(ORDER_SIDES)}.")
        if order_type not in ORDER_TYPES:
            raise ValueError(f"type must be one of: {', '.join(ORDER_TYPES)}.")
        if time_in_force not in TIME_IN_FORCE:
            raise ValueError(f"time_in_force must be one of: {', '.join(TIME_IN_FORCE)}.")
        if self.qty is None and self.notional is None:
            raise ValueError("qty or notional is required.")
        if self.qty is not None and self.notional is not None:
            raise ValueError("Use qty or notional, not both.")
        if self.qty is not None and self.qty <= 0:
            raise ValueError("qty must be greater than zero.")
        if self.notional is not None and self.notional <= 0:
            raise ValueError("notional must be greater than zero.")

        payload: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if self.qty is not None:
            payload["qty"] = self.qty
        if self.notional is not None:
            payload["notional"] = self.notional
        if self.limit_price is not None:
            payload["limit_price"] = self.limit_price
        if self.stop_price is not None:
            payload["stop_price"] = self.stop_price
        if self.client_order_id:
            payload["client_order_id"] = self.client_order_id.strip()
        return payload


class AlpacaClient:
    provider_name = "alpaca"

    def __init__(self, settings: AlpacaSettings) -> None:
        self._settings = settings

    def get_account(self) -> dict[str, Any]:
        payload = self._request("GET", self._trading_url("/v2/account"))
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca account response to be a JSON object.")
        return payload

    def get_positions(self) -> list[dict[str, Any]]:
        payload = self._request("GET", self._trading_url("/v2/positions"))
        if not isinstance(payload, list):
            raise AlpacaApiError("Expected Alpaca positions response to be a JSON array.")
        return payload

    def get_orders(self, *, status: str = "open", limit: int = 50) -> list[dict[str, Any]]:
        query = urlencode({"status": status, "limit": max(1, min(limit, 500))})
        payload = self._request("GET", self._trading_url(f"/v2/orders?{query}"))
        if not isinstance(payload, list):
            raise AlpacaApiError("Expected Alpaca orders response to be a JSON array.")
        return payload

    def submit_order(self, order: PaperOrderRequest) -> dict[str, Any]:
        payload = self._request("POST", self._trading_url("/v2/orders"), body=order.as_payload())
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca order response to be a JSON object.")
        return payload

    def get_latest_bar(self, symbol: str, *, feed: str | None = None) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required.")

        params = {"symbols": symbol}
        if feed:
            params["feed"] = feed.strip().lower()
        payload = self._request("GET", self._data_url(f"/v2/stocks/bars/latest?{urlencode(params)}"))
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca latest bar response to be a JSON object.")
        return payload

    def get_stock_bars(
        self,
        symbol: str,
        *,
        start: str,
        end: str,
        timeframe: str = "1Min",
        feed: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]:
        symbol = symbol.strip().upper()
        if not symbol:
            raise ValueError("symbol is required.")

        params: dict[str, str | int] = {
            "symbols": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": max(1, min(limit, 10000)),
        }
        if feed:
            params["feed"] = feed.strip().lower()

        payload = self._request("GET", self._data_url(f"/v2/stocks/bars?{urlencode(params)}"))
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca stock bars response to be a JSON object.")

        bars = payload.get("bars")
        if not isinstance(bars, dict):
            raise AlpacaApiError("Expected Alpaca stock bars response to include bars.")
        symbol_bars = bars.get(symbol, [])
        if not isinstance(symbol_bars, list):
            raise AlpacaApiError("Expected Alpaca stock bars for symbol to be a JSON array.")
        return symbol_bars

    def get_option_contracts(
        self,
        underlying_symbol: str,
        *,
        expiration_date_gte: str | None = None,
        expiration_date_lte: str | None = None,
        status: str = "active",
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        underlying_symbol = underlying_symbol.strip().upper()
        if not underlying_symbol:
            raise ValueError("underlying_symbol is required.")

        params: dict[str, str | int] = {
            "underlying_symbols": underlying_symbol,
            "status": status,
            "limit": max(1, min(limit, 10000)),
        }
        if expiration_date_gte:
            params["expiration_date_gte"] = expiration_date_gte
        if expiration_date_lte:
            params["expiration_date_lte"] = expiration_date_lte

        payload = self._request("GET", self._trading_url(f"/v2/options/contracts?{urlencode(params)}"))
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca option contracts response to be a JSON object.")

        contracts = payload.get("option_contracts")
        if not isinstance(contracts, list):
            raise AlpacaApiError("Expected Alpaca option contracts response to include option_contracts.")
        return contracts

    def get_option_snapshots(self, symbols: list[str], *, feed: str | None = None) -> dict[str, Any]:
        clean_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            raise ValueError("symbols are required.")
        if len(clean_symbols) > 100:
            raise ValueError("Alpaca option snapshots accepts at most 100 symbols per request.")

        params = {"symbols": ",".join(clean_symbols)}
        if feed:
            params["feed"] = feed.strip().lower()
        payload = self._request("GET", self._data_url(f"/v1beta1/options/snapshots?{urlencode(params)}"))
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca option snapshots response to be a JSON object.")

        snapshots = payload.get("snapshots")
        if not isinstance(snapshots, dict):
            raise AlpacaApiError("Expected Alpaca option snapshots response to include snapshots.")
        return snapshots

    def get_option_chain(self, underlying_symbol: str, *, feed: str | None = None, limit: int = 1000) -> dict[str, Any]:
        underlying_symbol = underlying_symbol.strip().upper()
        if not underlying_symbol:
            raise ValueError("underlying_symbol is required.")

        params: dict[str, str | int] = {"limit": max(1, min(limit, 1000))}
        if feed:
            params["feed"] = feed.strip().lower()
        payload = self._request(
            "GET",
            self._data_url(f"/v1beta1/options/snapshots/{underlying_symbol}?{urlencode(params)}"),
        )
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca option chain response to be a JSON object.")
        return payload

    def get_option_bars(
        self,
        symbols: list[str],
        *,
        start: str,
        end: str,
        timeframe: str = "1Min",
        feed: str | None = None,
        limit: int = 10000,
    ) -> dict[str, Any]:
        clean_symbols = [symbol.strip().upper() for symbol in symbols if symbol.strip()]
        if not clean_symbols:
            raise ValueError("symbols are required.")
        if len(clean_symbols) > 100:
            raise ValueError("Alpaca option bars accepts at most 100 symbols per request.")

        params: dict[str, str | int] = {
            "symbols": ",".join(clean_symbols),
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": max(1, min(limit, 10000)),
        }
        if feed:
            params["feed"] = feed.strip().lower()
        payload = self._request("GET", self._data_url(f"/v1beta1/options/bars?{urlencode(params)}"))
        if not isinstance(payload, dict):
            raise AlpacaApiError("Expected Alpaca option bars response to be a JSON object.")

        bars = payload.get("bars")
        if not isinstance(bars, dict):
            raise AlpacaApiError("Expected Alpaca option bars response to include bars.")
        return bars

    def _trading_url(self, path: str) -> str:
        return f"{self._settings.paper_base_url}{path}"

    def _data_url(self, path: str) -> str:
        return f"{self._settings.data_base_url}{path}"

    def _request(self, method: str, url: str, body: dict[str, Any] | None = None) -> Any:
        data = None
        headers = {
            "APCA-API-KEY-ID": self._settings.api_key_id,
            "APCA-API-SECRET-KEY": self._settings.api_secret_key,
            "User-Agent": self._settings.user_agent,
            "Accept": "application/json",
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"

        request = Request(url=url, method=method, headers=headers, data=data)

        try:
            with urlopen(request, timeout=self._settings.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise AlpacaApiError(f"Alpaca API request failed with HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise AlpacaApiError(f"Alpaca API request failed: {exc.reason}") from exc
        except TimeoutError as exc:
            raise AlpacaApiError("Alpaca API request timed out.") from exc

        if not raw_body:
            return None

        try:
            return json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise AlpacaApiError("Alpaca API returned invalid JSON.") from exc
