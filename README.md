# Futures Swing Bot (Freqtrade + Docker)

Automated swing-trading bot for **Binance USDⓈ-M Futures** (isolated margin, long + short),
built on [Freqtrade](https://www.freqtrade.io) and run with Docker.

> **Safety default:** the bot runs in **dry-run (paper trading)** mode. No real orders are
> placed until `dry_run` is switched off on purpose (Phase 5, needs your explicit approval).

## Folder layout

```
futures-swing-bot/
├── docker-compose.yml        # runs the official Freqtrade image (pinned version)
├── .env.example              # template for secrets -> copy to .env (git-ignored)
├── scripts/
│   ├── download_data.ps1     # download history (Windows PowerShell)
│   └── download_data.sh      # same, for Linux / VPS
├── user_data/
│   ├── config.json           # all bot settings (no secrets in here)
│   ├── strategies/           # strategy files (Phase 2)
│   ├── tools/check_pairs.py  # checks which pairs fit a ~100 USDT account
│   ├── data/                 # downloaded market data (git-ignored)
│   └── logs/                 # bot logs (git-ignored)
└── reports/                  # backtest reports, checklists
```

## Quick start (Windows, Docker Desktop)

Open **PowerShell** in the project folder:

```powershell
Copy-Item .env.example .env          # then edit .env in Notepad (keys can stay empty for now)
docker compose pull                  # download the Freqtrade image
.\scripts\download_data.ps1          # download historical data (takes a while)
docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/tools/check_pairs.py
```

On Linux/VPS use `cp .env.example .env` and `./scripts/download_data.sh`.

## Where settings live

| What | Where |
|---|---|
| Dry-run vs live, pairs, max open trades, order types | `user_data/config.json` |
| Risk rules (leverage, max loss per trade, margin cap, ATR stop) | `user_data/config.json` → `"swing_risk"` |
| Secrets (API keys, Telegram, UI password) | `.env` only |

Any setting can also be overridden from `.env` with the pattern `FREQTRADE__SECTION__KEY`,
e.g. `FREQTRADE__SWING_RISK__LEVERAGE=3` or `FREQTRADE__MAX_OPEN_TRADES=2`.

## Creating the Binance API key

You don't need a key for backtesting or downloading data. Create it when we reach the
dry-run/live phases.

1. Log in to **binance.com** → profile icon → **API Management** → **Create API** →
   *System generated* (HMAC). Give it a label like `freqtrade-bot`.
2. Complete the security verification. Copy the **API Key** and **Secret Key**. The secret is
   shown **only once**.
3. Click **Edit restrictions** and set:
   - ✅ **Enable Reading**
   - ✅ **Enable Futures** (this is what lets the bot trade USDⓈ-M futures)
   - ✅ Enable Spot & Margin Trading: **not needed**, leave it off
   - ❌ **Enable Withdrawals: must stay OFF.** With withdrawals off, a leaked key can't move
     your money out of the account.
   - ❌ Leave everything else off (Internal Transfer, Universal Transfer, Options, etc.).
4. **IP access restriction:**
   - On your home PC your IP usually changes, so you may have to choose *Unrestricted* for now.
     Binance may then periodically disable trading permissions on unrestricted keys. If the bot
     suddenly gets permission errors, this is the reason.
   - **On the VPS (Phase 6): always choose "Restrict access to trusted IPs only"** and enter
     the VPS's public IP. Then the key is useless from any other computer.
5. Put the key into `.env` (never anywhere else):
   ```
   FREQTRADE__EXCHANGE__KEY=your_key
   FREQTRADE__EXCHANGE__SECRET=your_secret
   ```
6. Futures account settings (Binance web → Futures → ⚙ Preferences). Freqtrade requires:
   - **Position Mode: One-way** (not Hedge mode)
   - **Asset Mode: Single-Asset** (not Multi-Assets)
   - Margin mode and leverage are set **per trade by the bot** (isolated, max 5x). You don't
     need to set them manually.
7. Move your USDT from the Spot wallet to the **USDⓈ-M Futures** wallet (Wallet → Transfer).

## Access from Turkey: things to check on your account

I can't see your account or check Binance's current rules for you, so please confirm these
yourself before Phase 4/5:

1. **Right platform.** You need a **Binance.com (global)** account. **Binance TR**
   (binance.tr) is a separate company with separate API keys, and it does not offer USDⓈ-M
   perpetual futures. Keys from Binance TR won't work here.
2. **Futures actually available to you.** Turkey's crypto law (Law No. 7518, 2024) requires
   crypto platforms serving Turkish residents to be licensed by the SPK (Capital Markets
   Board). This has led platforms to restrict or change products for Turkish users. Check:
   - Can you open the USDⓈ-M Futures page and is your futures account activated (the short
     quiz done)?
   - Does **Enable Futures** appear and stay ticked when you edit the API key?
   - Look at your notifications/emails from Binance for any announcement about derivatives
     restrictions or account migration for Turkish residents.
   - If Binance limits your leverage (some regions/new accounts get a lower maximum), tell me.
     The 5x default would then need lowering.
3. **KYC level.** Futures and API trading require completed identity verification.
4. **Tax / legal.** Gains from crypto trading may be taxable in Turkey. That's your
   responsibility; I can't advise on it.

Quick technical test once you have a key (works in dry-run, places no orders):
```powershell
docker compose run --rm freqtrade list-markets --config /freqtrade/user_data/config.json --trading-mode futures --quote USDT -1 | Select-Object -First 5
```
If that works but trading later fails with an error like "not eligible", "restricted" or
"-2015 Invalid API-key, IP, or permissions", it's an account or region restriction, not a bot
problem.

## Historical data

`scripts/download_data.ps1` (or `.sh`) downloads, for every pair in `config.json`:

- candles **15m, 1h, 4h, 1d** from Sept 2019 (start of Binance perpetuals) or the pair's
  listing date until now. 1h/4h are the strategy timeframes, 1d is for the higher-timeframe
  trend filter, and 15m is used in backtests to simulate stop/trailing fills more realistically.
- **mark price** and **funding rate** history. Freqtrade downloads these automatically in
  futures mode, and backtests need them for liquidation prices and funding fees.

Re-run the script any time to add the newest candles.

## Choosing pairs

`user_data/tools/check_pairs.py` reads Binance's live order limits and compares them with what
our risk rules would actually trade on a ~100 USDT account (5% risk per trade, max 25% margin,
5x). Pairs whose minimum order is too large (BTC is the usual problem: min quantity 0.001
BTC) or whose volume is too low are marked `EXCLUDE`. Copy the suggested list into
`exchange.pair_whitelist` in `config.json`.
