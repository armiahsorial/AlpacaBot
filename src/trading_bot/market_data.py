"""Common market-data provider contract and provider factory."""

from __future__ import annotations

from typing import Any, Protocol

from trading_bot.config import AlpacaSettings, DatabentoSettings, MarketDataSettings


class MarketDataError(RuntimeError):
    """Raised when the selected market-data provider cannot serve a request."""


class MarketDataClient(Protocol):
    provider_name: str

    def get_latest_bar(self, symbol: str, *, feed: str | None = None) -> dict[str, Any]: ...

    def get_stock_bars(
        self,
        symbol: str,
        *,
        start: str,
        end: str,
        timeframe: str = "1Min",
        feed: str | None = None,
        limit: int = 10000,
    ) -> list[dict[str, Any]]: ...

    def get_option_contracts(
        self,
        underlying_symbol: str,
        *,
        expiration_date_gte: str | None = None,
        expiration_date_lte: str | None = None,
        status: str = "active",
        limit: int = 1000,
    ) -> list[dict[str, Any]]: ...

    def get_option_snapshots(self, symbols: list[str], *, feed: str | None = None) -> dict[str, Any]: ...

    def get_option_bars(
        self,
        symbols: list[str],
        *,
        start: str,
        end: str,
        timeframe: str = "1Min",
        feed: str | None = None,
        limit: int = 10000,
        prefer_historical: bool = False,
    ) -> dict[str, Any]: ...


def create_market_data_client() -> MarketDataClient:
    provider = MarketDataSettings.from_env().provider
    if provider == "databento":
        from trading_bot.databento_client import DatabentoClient

        settings = DatabentoSettings.from_env()
        equities_fallback = None
        if settings.equities_fallback == "alpaca":
            try:
                from trading_bot.alpaca_client import AlpacaClient

                equities_fallback = AlpacaClient(AlpacaSettings.from_env())
            except ValueError:
                equities_fallback = None
        return DatabentoClient(settings, equities_fallback=equities_fallback)

    from trading_bot.alpaca_client import AlpacaClient

    return AlpacaClient(AlpacaSettings.from_env())
