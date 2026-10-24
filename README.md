# NIFTY Options Paper Bot — Web Deployment Starter

This project is a **paper-only** educational simulator. It has no broker integration and cannot place live orders.
The bundled CSV is synthetic demo data, not actual historical market data.

## Run locally in a browser
1. Install Python 3.11+.
2. Open a terminal in this folder.
3. Run:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

python -m pip install -r requirements.txt
python -m streamlit run app.py
```

The dashboard opens in your browser. Local use is private to your computer unless you intentionally expose it.

## Host it online
A simple route is Streamlit Community Cloud or another Python app host that supports Streamlit.

Typical steps:
1. Create a GitHub repository.
2. Upload `app.py`, `requirements.txt`, and the `data/` folder.
3. Deploy the repository using your hosting provider's Streamlit instructions.
4. Keep the app in paper-only mode. Do not add broker credentials or live-order code.

Cloud hosting is not guaranteed to be free forever; providers can change quotas and policies. Public hosting may make the app accessible to others, so check access controls and don't upload private trade history or credentials. This starter has no login system or persistent user database, so it is not suitable for confidential multi-user use as-is.

## Data CSV format
Required columns:
- `datetime`
- `nifty_close`
- `call_ltp`
- `put_ltp`

`call_ltp` and `put_ltp` must be the premium history for consistent, identified option contracts. Do not mix strikes or expiries. Use data you are permitted to access.

## Safety limitations
- No broker connection or live orders exist in this app.
- The demo data is synthetic.
- The simulator is an educational prototype; option fill assumptions, cost model, contract selection, and risk/accounting logic need more validation before its output can inform decisions.
- Never put API keys, passwords, or private account information into a public repository.
