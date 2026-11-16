# Toobit Futures Pump & Dump Scanner — V9 Integrated

FastAPI app for Render. Uses public Toobit market data only; it does not connect to an account or place orders.

## Render settings
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn app:app --host 0.0.0.0 --port $PORT`

## V9 changes
- Restores independent Pump/Dump discovery scoring (volume spike, OI delta, breakout, MACD momentum/crossover, RSI, Bollinger squeeze, order-book imbalance, funding).
- Adds distinct Entry scores using 1h / 15m / 5m / 1m; 1h is a soft trend filter and does not zero early alerts.
- Detects fresh EMA25/EMA50 and MACD crosses on closed candles.
- Adds simple candle-pattern and EMA25 pullback checks on 5m; 1m is only an entry trigger.
- Separates discovery scores from entry scores and displays both.
- OI change needs a previous snapshot; first run may show unavailable OI. State file may reset on ephemeral hosting.

Scores are heuristic rankings, not probabilities or financial advice. Test in paper trading before relying on them.
