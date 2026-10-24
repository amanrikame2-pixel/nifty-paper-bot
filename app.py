import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path

st.set_page_config(page_title="NIFTY Options Paper Bot", page_icon="🤖", layout="wide")
st.title("🤖 NIFTY Options Paper-Trading Robot")
st.caption("PAPER MODE ONLY — no broker connection, no real orders, no live trading.")

st.warning(
    "This is an educational simulator. The included data is synthetic and does not represent actual market prices. "
    "Do not use its results to judge profitability. This app cannot place orders."
)

DATA_PATH = Path(__file__).parent / "data" / "demo_nifty_options.csv"

def load_data(uploaded_file):
    if uploaded_file is None:
        df = pd.read_csv(DATA_PATH)
        source = "Bundled synthetic demo data"
    else:
        df = pd.read_csv(uploaded_file)
        source = "Uploaded CSV"
    required = {"datetime", "nifty_close", "call_ltp", "put_ltp"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError("CSV is missing required columns: " + ", ".join(sorted(missing)))
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for col in ["nifty_close", "call_ltp", "put_ltp"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["datetime", "nifty_close", "call_ltp", "put_ltp"]).sort_values("datetime")
    df = df.drop_duplicates(subset=["datetime"], keep="last").reset_index(drop=True)
    if len(df) < 30:
        raise ValueError("Please provide at least 30 valid rows.")
    if (df[["nifty_close", "call_ltp", "put_ltp"]] <= 0).any().any():
        raise ValueError("Prices must be positive.")
    return df, source

with st.sidebar:
    st.header("Strategy & risk settings")
    fast_ema = st.number_input("Fast EMA", min_value=2, max_value=30, value=9, step=1)
    slow_ema = st.number_input("Slow EMA", min_value=3, max_value=60, value=21, step=1)
    if slow_ema <= fast_ema:
        st.error("Slow EMA must be greater than Fast EMA.")
    lot_size = st.number_input(
        "Contract lot size (verify current exchange lot size)",
        min_value=1, max_value=10000, value=65, step=1
    )
    capital = st.number_input("Virtual starting capital (₹)", min_value=1000, max_value=1000000, value=10000, step=500)
    risk_pct = st.slider("Maximum planned risk per trade (% of virtual capital)", 0.25, 3.0, 1.0, 0.25)
    max_daily_loss = st.number_input("Daily loss stop (₹, includes estimated costs)", min_value=50, max_value=5000, value=200, step=50)
    max_entries = st.number_input("Maximum entries per day", min_value=1, max_value=10, value=2, step=1)
    stop_pct = st.slider("Option premium stop-loss (%)", 5, 50, 20, 5)
    target_pct = st.slider("Option premium target (%)", 5, 100, 30, 5)
    cost_per_order = st.number_input("Estimated cost per executed order (₹)", min_value=0.0, max_value=500.0, value=25.0, step=5.0)
    st.caption("Cost is a rough placeholder per order. Replace with current brokerage, taxes and charges for your broker.")

st.subheader("1) Load data")
uploaded = st.file_uploader("Upload a CSV with the required columns (or use the included demo)", type=["csv"])
st.code("datetime,nifty_close,call_ltp,put_ltp\n2026-01-05 09:15:00,26000,120,115", language="text")
st.caption("Required columns: datetime, nifty_close, call_ltp, put_ltp. call_ltp/put_ltp must be option premium prices for the same selected contract through time. Do not mix strikes or expiries.")
try:
    df, source = load_data(uploaded)
except Exception as e:
    st.error(str(e))
    st.stop()

st.info(f"Data source: {source} · Rows: {len(df)} · Period: {df['datetime'].min()} to {df['datetime'].max()}")
df["fast_ema"] = df["nifty_close"].ewm(span=int(fast_ema), adjust=False).mean()
df["slow_ema"] = df["nifty_close"].ewm(span=int(slow_ema), adjust=False).mean()
df["prev_fast"] = df["fast_ema"].shift(1)
df["prev_slow"] = df["slow_ema"].shift(1)
df["signal"] = ""
df.loc[(df["prev_fast"] <= df["prev_slow"]) & (df["fast_ema"] > df["slow_ema"]), "signal"] = "CALL"
df.loc[(df["prev_fast"] >= df["prev_slow"]) & (df["fast_ema"] < df["slow_ema"]), "signal"] = "PUT"

# Conservative deterministic simulator: signal on completed candle, entry at that row's supplied option LTP.
# A single open position at a time; daily limits; no overnight positions.
trades = []
cash = float(capital)
daily_realized = {}
entries_per_day = {}
position = None
equity_points = []
last_date = None

for i, row in df.iterrows():
    ts = row["datetime"]
    day = ts.date()
    daily_realized.setdefault(day, 0.0)
    entries_per_day.setdefault(day, 0)
    # Exit open position at end of each date before processing next date.
    if position is not None and position["day"] != day:
        prev_row = df.iloc[i-1]
        exit_price = float(prev_row["call_ltp"] if position["side"] == "CALL" else prev_row["put_ltp"])
        gross = (exit_price - position["entry_price"]) * lot_size
        net = gross - cost_per_order  # entry cost already booked below
        daily_realized[position["day"]] += net
        cash += exit_price * lot_size - cost_per_order
        trades.append({**position, "exit_time": prev_row["datetime"], "exit_price": exit_price,
                       "exit_reason": "End of day", "gross_pnl": gross,
                       "total_costs": 2*cost_per_order, "net_pnl": gross - 2*cost_per_order})
        position = None
    # Manage exits using this row's premium.
    if position is not None:
        px = float(row["call_ltp"] if position["side"] == "CALL" else row["put_ltp"])
        stop = position["entry_price"] * (1 - stop_pct/100)
        target = position["entry_price"] * (1 + target_pct/100)
        reason = None
        if px <= stop:
            reason = "Stop-loss"
        elif px >= target:
            reason = "Target"
        elif i == len(df)-1:
            reason = "End of data"
        if reason:
            # Assume fill at observed row price; real fills can be worse.
            gross = (px - position["entry_price"]) * lot_size
            total_cost = 2 * cost_per_order
            net = gross - total_cost
            cash += px * lot_size - cost_per_order
            daily_realized[position["day"]] += net
            trades.append({**position, "exit_time": ts, "exit_price": px, "exit_reason": reason,
                           "gross_pnl": gross, "total_costs": total_cost, "net_pnl": net})
            position = None
    # Entries are blocked after daily loss limit and capped at daily entry count.
    if position is None and row["signal"] in ("CALL", "PUT"):
        day_net = daily_realized[day]
        if entries_per_day[day] >= max_entries or day_net <= -abs(max_daily_loss):
            equity_points.append({"datetime": ts, "cash": cash, "daily_realized": day_net})
            continue
        px = float(row["call_ltp"] if row["signal"] == "CALL" else row["put_ltp"])
        if px * lot_size > cash:
            equity_points.append({"datetime": ts, "cash": cash, "daily_realized": day_net})
            continue
        # Risk estimate is based on the stop distance; reject if one-lot planned loss exceeds risk budget.
        planned_loss = px * (stop_pct/100) * lot_size + 2*cost_per_order
        risk_budget = capital * risk_pct/100
        if planned_loss > risk_budget:
            equity_points.append({"datetime": ts, "cash": cash, "daily_realized": day_net})
            continue
        # Reserve full premium as buying power; cash reduced on entry for simple accounting.
        cash -= px * lot_size + cost_per_order
        position = {"entry_time": ts, "day": day, "side": row["signal"], "entry_price": px,
                    "quantity": int(lot_size), "planned_loss": planned_loss}
        entries_per_day[day] += 1
    equity_points.append({"datetime": ts, "cash": cash, "daily_realized": daily_realized[day]})

# If position somehow remains, close on final row.
if position is not None:
    row = df.iloc[-1]
    px = float(row["call_ltp"] if position["side"] == "CALL" else row["put_ltp"])
    gross = (px - position["entry_price"]) * lot_size
    total_cost = 2 * cost_per_order
    net = gross - total_cost
    cash += px * lot_size - cost_per_order
    daily_realized[position["day"]] += net
    trades.append({**position, "exit_time": row["datetime"], "exit_price": px, "exit_reason": "End of data",
                   "gross_pnl": gross, "total_costs": total_cost, "net_pnl": net})

trades_df = pd.DataFrame(trades)
if not trades_df.empty:
    trades_df["entry_time"] = pd.to_datetime(trades_df["entry_time"])
    trades_df["exit_time"] = pd.to_datetime(trades_df["exit_time"])
    trades_df["hold_minutes"] = (trades_df["exit_time"] - trades_df["entry_time"]).dt.total_seconds()/60
    wins = int((trades_df["net_pnl"] > 0).sum())
    net_total = float(trades_df["net_pnl"].sum())
    win_rate = wins / len(trades_df) * 100
    profit_factor = (trades_df.loc[trades_df.net_pnl > 0, "net_pnl"].sum() /
                     abs(trades_df.loc[trades_df.net_pnl < 0, "net_pnl"].sum())
                     if (trades_df.net_pnl < 0).any() else np.nan)
else:
    wins, net_total, win_rate, profit_factor = 0, 0.0, 0.0, np.nan

st.subheader("2) Signal and price chart")
chart = df.set_index("datetime")[["nifty_close", "fast_ema", "slow_ema"]]
st.line_chart(chart)
st.caption("Signals use completed candle values. The supplied option prices are treated as simulated execution prices; this is not a tick-by-tick execution model.")

st.subheader("3) Backtest summary")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Closed trades", len(trades_df))
c2.metric("Net simulated P&L", f"₹{net_total:,.2f}")
c3.metric("Win rate", f"{win_rate:.1f}%")
c4.metric("Profit factor", "N/A" if pd.isna(profit_factor) else f"{profit_factor:.2f}")

if not trades_df.empty:
    st.dataframe(trades_df[["entry_time", "exit_time", "side", "entry_price", "exit_price", "quantity",
                            "exit_reason", "gross_pnl", "total_costs", "net_pnl", "planned_loss", "hold_minutes"]],
                 use_container_width=True, hide_index=True)
    st.download_button("Download trade log CSV", trades_df.to_csv(index=False).encode("utf-8"),
                       file_name="paper_trade_log.csv", mime="text/csv")
else:
    st.info("No trades passed all filters. This is possible and is not an error. Review affordability, risk budget, data, and EMA settings.")

st.subheader("4) Safety checks")
st.markdown("""
- **Paper only:** there is no broker API, API key field, or live order function in this application.
- **Affordability:** the simulator rejects a trade if one lot's premium cost exceeds available simulated cash.
- **Risk budget:** rejects a trade if estimated stop-loss risk plus estimated costs exceeds the selected risk budget.
- **Daily guardrails:** limits entries per day and blocks new entries after the configured realized daily loss threshold.
- **No overnight positions:** open positions are closed at the end of each date in the dataset.
- **Important limitation:** this starter version is a teaching prototype, not production-grade trading software. Daily loss checks and P&L accounting are simplified; verify results independently before relying on them.
""")
st.caption("Never add broker credentials to this app. Live trading is intentionally not implemented.")
