# trading_bot

A fresh Python foundation for a trading bot powered by the GEX API.

The first supported API call is:

- `GET https://api.gexbot.com/tickers`

This endpoint returns the stock, index, and futures symbols that can be used by the rest of the GEX API.

## Setup

```bash
cd trading_bot
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Create a `.env` file in this folder:

```env
GEX_API_KEY=your-api-key
```

Optional settings:

```env
GEX_BASE_URL=https://api.gexbot.com
GEX_USER_AGENT=trading_bot/0.1.0
GEX_TIMEOUT_SECONDS=20
```

To connect an Alpaca paper trading account, add your paper API keys:

```env
APCA_API_KEY_ID=your-alpaca-paper-key-id
APCA_API_SECRET_KEY=your-alpaca-paper-secret-key
ALPACA_PAPER_BASE_URL=https://paper-api.alpaca.markets
ALPACA_DATA_BASE_URL=https://data.alpaca.markets
```

Alpaca remains the paper broker even when another market-data provider is selected.

### Databento market data

The app can use Databento for option chains, OPRA quotes, stock and option bars,
historical replay, technical indicators, and trade-outcome tracking. Alpaca is
still used for paper account and order endpoints.

After activating Databento OPRA and U.S. equities access, add:

```env
MARKET_DATA_PROVIDER=databento
DATABENTO_API_KEY=your-databento-api-key
DATABENTO_OPTIONS_DATASET=OPRA.PILLAR
DATABENTO_EQUITIES_DATASET=EQUS.MINI
DATABENTO_EQUITIES_FALLBACK=alpaca
DATABENTO_LIVE_REPLAY_SECONDS=30
DATABENTO_LIVE_TIMEOUT_SECONDS=2
```

Restart the web application after changing providers. To return to Alpaca data,
change only:

```env
MARKET_DATA_PROVIDER=alpaca
```

Databento timestamps are normalized to the same UTC bar format the app already
uses. OCC option symbols are translated automatically. Greeks are estimated
locally from the Databento NBBO mid when the feed does not provide them.
`DATABENTO_LIVE_REPLAY_MINUTES` remains supported for older configurations, but
`DATABENTO_LIVE_REPLAY_SECONDS` takes precedence when both are present.

Live `EQUS.MINI` access requires a Databento U.S. Equities subscription. With
`DATABENTO_EQUITIES_FALLBACK=alpaca`, missing Databento equity entitlement falls
back to Alpaca IEX bars for underlying technicals while option quotes and option
bars continue to use Databento OPRA. Set the fallback to `none` to require
Databento for both asset classes.

The current underlying or index spot used for GEX distances, native SPX/NDX
strike filtering, and locally estimated option Greeks always comes from the GEX
response. Alpaca proxy bars are used only for indicators that require price
history, such as VWAP and the 50-day/200-day moving averages.

Environment variables from your shell override values in `.env`.

## Usage

Print all supported ticker groups:

```bash
trading-bot tickers
```

Print one group:

```bash
trading-bot tickers --group stocks
trading-bot tickers --group indexes
trading-bot tickers --group futures
```

Raw JSON output:

```bash
trading-bot tickers --json
```

Fetch classic GEX chain data:

```bash
trading-bot gex-chain SPX --period zero
```

Aggregation periods are `full`, `zero`, and `one`.

Limit the number of strike rows printed:

```bash
trading-bot gex-chain SPX --period zero --limit 20
```

Raw JSON output:

```bash
trading-bot gex-chain SPX --period zero --json
```

Fetch state GEX imbalance profile:

```bash
trading-bot state-profile SPX --period zero
```

Limit the number of strike rows printed:

```bash
trading-bot state-profile SPX --period zero --limit 20
```

Raw JSON output:

```bash
trading-bot state-profile SPX --period zero --json
```

Fetch slim state GEX major imbalance levels:

```bash
trading-bot state-majors SPX --period full
```

Raw JSON output:

```bash
trading-bot state-majors SPX --period full --json
```

Fetch state GEX max imbalance changes:

```bash
trading-bot state-maxchange SPX --period full
```

Raw JSON output:

```bash
trading-bot state-maxchange SPX --period full --json
```

Fetch state orderflow Greek profile:

```bash
trading-bot state-greeks SPX delta_zero
```

Supported Greek profile values are `delta_zero`, `gamma_zero`, `delta_one`, `gamma_one`, `charm_zero`, `vanna_zero`, `charm_one`, and `vanna_one`.

Limit the number of mini-contract rows printed:

```bash
trading-bot state-greeks SPX delta_zero --limit 20
```

Raw JSON output:

```bash
trading-bot state-greeks SPX delta_zero --json
```

Analyze classic GEX and state imbalance together:

```bash
trading-bot analyze SPX --period zero
```

The analysis report includes market regime, bias, confidence, trade permission, setup, entry trigger, invalidation, target zone, avoid zone, score breakdown, and no-trade reasons.

Raw JSON output:

```bash
trading-bot analyze SPX --period zero --json
```

Show Alpaca paper account details:

```bash
trading-bot alpaca-account
```

Show current paper positions and orders:

```bash
trading-bot alpaca-positions
trading-bot alpaca-orders --status open
```

Fetch Alpaca stock market data:

```bash
trading-bot alpaca-latest-bar SPY
```

Submit an Alpaca paper order:

```bash
trading-bot paper-order SPY buy --qty 1
```

Start the local web interface:

```bash
trading-bot-web
```

Then open:

```text
http://127.0.0.1:8765
```

The web UI includes a strike map, call/put watch-zone pointers, and optional auto-refresh.
When Alpaca paper keys are configured, the web UI also shows paper account state, positions, latest stock bar lookup, and a manual paper order ticket.

Fetch slim classic GEX major levels:

```bash
trading-bot gex-majors SPX --period full
```

Raw JSON output:

```bash
trading-bot gex-majors SPX --period full --json
```

Fetch max GEX changes, also known as max priors:

```bash
trading-bot gex-maxchange SPX --period full
```

Raw JSON output:

```bash
trading-bot gex-maxchange SPX --period full --json
```

## Tests

```bash
PYTHONPATH=src python -m unittest discover -s tests
```

## Notes

This project reads GEX levels and market data for analysis. Databento supplies
data only; it does not execute orders. Keep paper and live execution controls
separate, and validate subscriptions and feed behavior before relying on a live
session.
