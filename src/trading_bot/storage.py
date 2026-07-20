"""Durable SQLite storage for the local trading bot UI."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 4


class TradingBotStorage:
    """Stores UI records while retaining their complete JSON snapshots."""

    def __init__(self, path: str | Path | None = None) -> None:
        configured_path = path or os.environ.get("TRADING_BOT_DB_PATH")
        self.path = Path(configured_path) if configured_path else Path.cwd() / "data" / "trading_bot.sqlite3"
        self.path = self.path.expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        with self._connect() as connection:
            previous_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS trade_permissions (
                    record_id TEXT PRIMARY KEY,
                    signal_date TEXT NOT NULL,
                    timestamp_iso TEXT,
                    ticker TEXT,
                    symbol TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS trade_permissions_date_ticker
                    ON trade_permissions(signal_date, ticker);
                CREATE INDEX IF NOT EXISTS trade_permissions_symbol
                    ON trade_permissions(symbol);

                CREATE TABLE IF NOT EXISTS paper_ledger (
                    record_id TEXT PRIMARY KEY,
                    trade_date TEXT NOT NULL,
                    timestamp_iso TEXT,
                    ticker TEXT,
                    symbol TEXT,
                    status TEXT,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS paper_ledger_date_ticker
                    ON paper_ledger(trade_date, ticker);
                CREATE INDEX IF NOT EXISTS paper_ledger_symbol
                    ON paper_ledger(symbol);

                CREATE TABLE IF NOT EXISTS tracked_tickers (
                    tracking_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (tracking_date, ticker)
                );

                CREATE TABLE IF NOT EXISTS historical_option_bars (
                    provider TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (provider, session_date, symbol)
                );
                CREATE INDEX IF NOT EXISTS historical_option_bars_date
                    ON historical_option_bars(session_date, symbol);

                CREATE TABLE IF NOT EXISTS historical_stock_bars (
                    provider TEXT NOT NULL,
                    session_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (provider, session_date, symbol, timeframe)
                );

                CREATE TABLE IF NOT EXISTS historical_gex_rows (
                    session_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    period TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_date, ticker, period, mode)
                );

                CREATE TABLE IF NOT EXISTS historical_cache_status (
                    session_date TEXT NOT NULL,
                    ticker TEXT NOT NULL,
                    period TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    option_contract_count INTEGER NOT NULL DEFAULT 0,
                    detail_json TEXT NOT NULL DEFAULT '{}',
                    completed_at TEXT,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (session_date, ticker, period, provider)
                );
                CREATE INDEX IF NOT EXISTS historical_cache_status_date
                    ON historical_cache_status(session_date, ticker);
                """
            )
            if previous_version < 3:
                # Version 3 resolves legacy parent-root index symbols to their
                # Databento weekly series. Remove older ambiguous cached bars
                # once so they can be fetched again with the corrected mapping.
                connection.execute(
                    """
                    DELETE FROM historical_option_bars
                    WHERE provider = 'DATABENTO'
                      AND (
                        symbol GLOB 'SPX[0-9]*' OR
                        symbol GLOB 'NDX[0-9]*' OR
                        symbol GLOB 'RUT[0-9]*'
                      )
                    """
                )
            connection.execute(
                "INSERT INTO metadata(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def snapshot(self) -> dict[str, Any]:
        with self._connect() as connection:
            history = self._payloads(connection, "trade_permissions", "timestamp_iso DESC, record_id")
            ledger = self._payloads(connection, "paper_ledger", "timestamp_iso DESC, record_id")
            tracking: dict[str, list[str]] = {}
            for row in connection.execute(
                "SELECT tracking_date, ticker FROM tracked_tickers ORDER BY tracking_date DESC, ticker"
            ):
                tracking.setdefault(row["tracking_date"], []).append(row["ticker"])
        return {
            "trade_history": history,
            "paper_ledger": ledger,
            "tracked_tickers": tracking,
            "database_path": str(self.path),
            "schema_version": SCHEMA_VERSION,
        }

    def history_for_day(self, day: str) -> dict[str, Any]:
        """Return complete persisted records for one trading day."""
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        with self._connect() as connection:
            history = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    """
                    SELECT payload_json
                    FROM trade_permissions
                    WHERE signal_date = ?
                    ORDER BY timestamp_iso DESC, record_id
                    """,
                    (day,),
                )
            ]
            ledger = [
                json.loads(row["payload_json"])
                for row in connection.execute(
                    """
                    SELECT payload_json
                    FROM paper_ledger
                    WHERE trade_date = ?
                    ORDER BY timestamp_iso DESC, record_id
                    """,
                    (day,),
                )
            ]
            tickers = [
                row["ticker"]
                for row in connection.execute(
                    "SELECT ticker FROM tracked_tickers WHERE tracking_date = ? ORDER BY ticker",
                    (day,),
                )
            ]
        return {
            "date": day,
            "trade_history": history,
            "paper_ledger": ledger,
            "tracked_tickers": tickers,
        }

    def sync(
        self,
        *,
        trade_history: Iterable[dict[str, Any]] = (),
        paper_ledger: Iterable[dict[str, Any]] = (),
        tracked_tickers: dict[str, list[str]] | None = None,
    ) -> dict[str, int]:
        history_rows = [row for row in trade_history if isinstance(row, dict)]
        ledger_rows = [row for row in paper_ledger if isinstance(row, dict)]
        tracking_rows = tracked_tickers if isinstance(tracked_tickers, dict) else {}
        with self._connect() as connection:
            for row in history_rows:
                self._upsert_trade_permission(connection, row)
            for row in ledger_rows:
                self._upsert_paper_trade(connection, row)
            tracked_count = self._upsert_tracking(connection, tracking_rows)
        return {
            "trade_history": len(history_rows),
            "paper_ledger": len(ledger_rows),
            "tracked_tickers": tracked_count,
        }

    def delete_day(self, record_type: str, day: str) -> int:
        table_and_column = {
            "trade_history": ("trade_permissions", "signal_date"),
            "paper_ledger": ("paper_ledger", "trade_date"),
            "tracked_tickers": ("tracked_tickers", "tracking_date"),
        }.get(record_type)
        if table_and_column is None:
            raise ValueError("record_type must be trade_history, paper_ledger, or tracked_tickers.")
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        table, column = table_and_column
        with self._connect() as connection:
            cursor = connection.execute(f"DELETE FROM {table} WHERE {column} = ?", (day,))
            return cursor.rowcount

    def option_bars(
        self,
        provider: str,
        day: str,
        symbols: Iterable[str],
    ) -> dict[str, list[dict[str, Any]]]:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        clean_symbols = sorted({_upper(symbol) for symbol in symbols} - {""})
        if not clean_symbols:
            return {}
        placeholders = ",".join("?" for _ in clean_symbols)
        params = [_upper(provider), day, *clean_symbols]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT symbol, payload_json
                FROM historical_option_bars
                WHERE provider = ? AND session_date = ? AND symbol IN ({placeholders})
                """,
                params,
            )
            return {row["symbol"]: json.loads(row["payload_json"]) for row in rows}

    def save_option_bars(
        self,
        provider: str,
        day: str,
        bars_by_symbol: dict[str, list[dict[str, Any]]],
    ) -> int:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        clean_provider = _upper(provider)
        saved = 0
        with self._connect() as connection:
            for symbol, bars in bars_by_symbol.items():
                if not isinstance(bars, list):
                    continue
                connection.execute(
                    """
                    INSERT INTO historical_option_bars(provider, session_date, symbol, payload_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(provider, session_date, symbol) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        fetched_at = CURRENT_TIMESTAMP
                    """,
                    (clean_provider, day, _upper(symbol), json.dumps(bars, separators=(",", ":"))),
                )
                saved += 1
        return saved

    def stock_bars(self, provider: str, day: str, symbol: str, timeframe: str) -> list[dict[str, Any]] | None:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM historical_stock_bars
                WHERE provider = ? AND session_date = ? AND symbol = ? AND timeframe = ?
                """,
                (_upper(provider), day, _upper(symbol), timeframe),
            ).fetchone()
        return json.loads(row["payload_json"]) if row is not None else None

    def save_stock_bars(
        self,
        provider: str,
        day: str,
        symbol: str,
        timeframe: str,
        bars: list[dict[str, Any]],
    ) -> None:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO historical_stock_bars(provider, session_date, symbol, timeframe, payload_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(provider, session_date, symbol, timeframe) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    fetched_at = CURRENT_TIMESTAMP
                """,
                (_upper(provider), day, _upper(symbol), timeframe, json.dumps(bars, separators=(",", ":"))),
            )

    def gex_rows(self, day: str, ticker: str, period: str) -> dict[str, list[dict[str, Any]]]:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT mode, payload_json FROM historical_gex_rows
                WHERE session_date = ? AND ticker = ? AND period = ?
                """,
                (day, _upper(ticker), period.lower()),
            )
        return {row["mode"]: json.loads(row["payload_json"]) for row in rows}

    def gex_spot_rows(self, day: str, ticker: str) -> list[dict[str, Any]]:
        """Return one cached classic GEX stream for historical index spot lookup."""
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT payload_json FROM historical_gex_rows
                WHERE session_date = ? AND ticker = ? AND mode = 'classic'
                ORDER BY CASE period WHEN 'zero' THEN 0 WHEN 'one' THEN 1 ELSE 2 END
                LIMIT 1
                """,
                (day, _upper(ticker)),
            ).fetchone()
        if row is None:
            return []
        payload = json.loads(row["payload_json"])
        return payload if isinstance(payload, list) else []

    def save_gex_rows(
        self,
        day: str,
        ticker: str,
        period: str,
        rows_by_mode: dict[str, list[dict[str, Any]]],
    ) -> None:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        with self._connect() as connection:
            for mode, rows in rows_by_mode.items():
                if mode not in {"classic", "state"} or not isinstance(rows, list):
                    continue
                connection.execute(
                    """
                    INSERT INTO historical_gex_rows(session_date, ticker, period, mode, payload_json)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(session_date, ticker, period, mode) DO UPDATE SET
                        payload_json = excluded.payload_json,
                        fetched_at = CURRENT_TIMESTAMP
                    """,
                    (day, _upper(ticker), period.lower(), mode, json.dumps(rows, separators=(",", ":"))),
                )

    def cache_status(
        self,
        day: str,
        *,
        period: str | None = None,
        provider: str | None = None,
    ) -> list[dict[str, Any]]:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        clauses = ["session_date = ?"]
        params: list[Any] = [day]
        if period:
            clauses.append("period = ?")
            params.append(period.lower())
        if provider:
            clauses.append("provider = ?")
            params.append(_upper(provider))
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT session_date, ticker, period, provider, status,
                       option_contract_count, detail_json, completed_at, updated_at
                FROM historical_cache_status
                WHERE {' AND '.join(clauses)}
                ORDER BY ticker
                """,
                params,
            )
            return [
                {
                    "date": row["session_date"],
                    "ticker": row["ticker"],
                    "period": row["period"],
                    "provider": row["provider"],
                    "status": row["status"],
                    "option_contract_count": row["option_contract_count"],
                    "detail": json.loads(row["detail_json"]),
                    "completed_at": row["completed_at"],
                    "updated_at": row["updated_at"],
                }
                for row in rows
            ]

    def save_cache_status(
        self,
        day: str,
        ticker: str,
        period: str,
        provider: str,
        *,
        status: str,
        option_contract_count: int,
        detail: dict[str, Any],
    ) -> None:
        if not _valid_day(day):
            raise ValueError("day must use YYYY-MM-DD format.")
        completed = "CURRENT_TIMESTAMP" if status == "complete" else "NULL"
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO historical_cache_status(
                    session_date, ticker, period, provider, status,
                    option_contract_count, detail_json, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, {completed})
                ON CONFLICT(session_date, ticker, period, provider) DO UPDATE SET
                    status = excluded.status,
                    option_contract_count = excluded.option_contract_count,
                    detail_json = excluded.detail_json,
                    completed_at = excluded.completed_at,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    day, _upper(ticker), period.lower(), _upper(provider), status,
                    max(0, int(option_contract_count)), json.dumps(detail, separators=(",", ":")),
                ),
            )

    @staticmethod
    def _payloads(connection: sqlite3.Connection, table: str, order_by: str) -> list[dict[str, Any]]:
        return [
            json.loads(row["payload_json"])
            for row in connection.execute(f"SELECT payload_json FROM {table} ORDER BY {order_by}")
        ]

    def _upsert_trade_permission(self, connection: sqlite3.Connection, row: dict[str, Any]) -> None:
        signal_date = _history_day(row)
        if not signal_date:
            return
        record_id = _record_id(row, "permission")
        connection.execute(
            """
            INSERT INTO trade_permissions(
                record_id, signal_date, timestamp_iso, ticker, symbol, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                signal_date = excluded.signal_date,
                timestamp_iso = excluded.timestamp_iso,
                ticker = excluded.ticker,
                symbol = excluded.symbol,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                record_id,
                signal_date,
                _timestamp_iso(row),
                _ticker(row),
                _upper(row.get("symbol")),
                _json(row),
            ),
        )

    def _upsert_paper_trade(self, connection: sqlite3.Connection, row: dict[str, Any]) -> None:
        trade_date = _ledger_day(row)
        if not trade_date:
            return
        record_id = _record_id(row, "ledger")
        connection.execute(
            """
            INSERT INTO paper_ledger(
                record_id, trade_date, timestamp_iso, ticker, symbol, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                trade_date = excluded.trade_date,
                timestamp_iso = excluded.timestamp_iso,
                ticker = excluded.ticker,
                symbol = excluded.symbol,
                status = excluded.status,
                payload_json = excluded.payload_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                record_id,
                trade_date,
                _timestamp_iso(row),
                _ticker(row),
                _upper(row.get("symbol")),
                str(row.get("status") or ""),
                _json(row),
            ),
        )

    @staticmethod
    def _upsert_tracking(connection: sqlite3.Connection, tracking: dict[str, list[str]]) -> int:
        count = 0
        for day, tickers in tracking.items():
            if not _valid_day(day) or not isinstance(tickers, list):
                continue
            for ticker in {_upper(value) for value in tickers} - {""}:
                connection.execute(
                    """
                    INSERT INTO tracked_tickers(tracking_date, ticker) VALUES (?, ?)
                    ON CONFLICT(tracking_date, ticker) DO UPDATE SET last_seen_at = CURRENT_TIMESTAMP
                    """,
                    (day, ticker),
                )
                count += 1
        return count


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def _record_id(row: dict[str, Any], prefix: str) -> str:
    supplied = str(row.get("id") or "").strip()
    if supplied:
        return supplied
    digest = hashlib.sha256(_json(row).encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


def _timestamp_iso(row: dict[str, Any]) -> str | None:
    timestamp = row.get("timestamp")
    if isinstance(timestamp, dict) and timestamp.get("iso"):
        return str(timestamp["iso"])
    value = row.get("timestamp_iso") or row.get("exitTimestamp")
    return str(value) if value else None


def _history_day(row: dict[str, Any]) -> str:
    timestamp = row.get("timestamp")
    values = [
        row.get("replayDate"),
        timestamp.get("day") if isinstance(timestamp, dict) else None,
        (_timestamp_iso(row) or "")[:10],
    ]
    return next((str(value) for value in values if _valid_day(value)), "")


def _ledger_day(row: dict[str, Any]) -> str:
    timestamp = row.get("timestamp")
    values = [
        row.get("day"),
        timestamp.get("day") if isinstance(timestamp, dict) else None,
        (_timestamp_iso(row) or "")[:10],
    ]
    return next((str(value) for value in values if _valid_day(value)), "")


def _ticker(row: dict[str, Any]) -> str:
    return _upper(row.get("ticker") or row.get("underlying"))


def _upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _valid_day(value: Any) -> bool:
    text = str(value or "")
    if len(text) != 10 or text[4] != "-" or text[7] != "-":
        return False
    try:
        from datetime import date

        date.fromisoformat(text)
    except ValueError:
        return False
    return True
