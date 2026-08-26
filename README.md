# SofaScore-Stake Automated Betting Bot

A complete, production-ready bot that monitors live football match stats and attack momentum from **SofaScore** (zero API cost) and automatically prepares and places bets on **Stake.com** using **Playwright browser automation**.

---

## 🚀 Quick Start Guide

### 1. Initial One-Time Stake Login
Stake requires logging in once so the bot can save your session cookies (which safely bypasses Cloudflare and 2FA):

```powershell
python bot.py --login
```
* A Chrome browser window will open to `stake.com/sports`.
* Log in with your Stake credentials and complete any 2FA/Captcha.
* Once logged in, press <kbd>Enter</kbd> in your terminal to save your authenticated profile locally in `browser_data/stake_profile`.

---

### 2. Verify SofaScore Live Match Feed
Test the real-time match data feed from SofaScore (zero cost):

```powershell
python bot.py --test-sofascore
```

---

### 3. Telegram Notifications Setup (Optional)
Receive real-time bet signals, slip screenshots, PnL updates, and circuit breaker alerts directly on Telegram:

1. Open Telegram and search for [@BotFather](https://t.me/BotFather) to create a new bot and copy your **Bot Token**.
2. Start a chat with your bot, then message [@userinfobot](https://t.me/userinfobot) to get your numerical **Chat ID**.
3. Add them to your `.env` file:
   ```env
   TELEGRAM_ENABLED=true
   TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ
   TELEGRAM_CHAT_ID=987654321
   ```
4. Test the connection:
   ```powershell
   python bot.py --test-telegram
   ```

---

### 4. Run the Bot (Simulation / Paper Trading Mode)
By default, the bot runs in **Simulation Mode** (`SIMULATION_MODE=true` in `.env`). It will detect live triggers, calculate dynamic stake amounts, navigate on Stake, prepare the bet slip, take a screenshot, and dispatch a Telegram alert without risking real money:

```powershell
python bot.py --run
```

---

### 5. Switching to Live Bets
When you are ready to place real bets:
1. Open [`.env`](.env)
2. Set `SIMULATION_MODE=false`
3. Configure your risk settings (`BASE_BANKROLL_PERCENT=0.02`, `MAX_BET_CAP=10.00`)
4. Run `python bot.py --run`

---

## ⚙️ Configuration (`.env`)

| Variable | Description | Default |
| :--- | :--- | :--- |
| `TELEGRAM_ENABLED` | Toggle Telegram notifications | `true` |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token from @BotFather | `""` |
| `TELEGRAM_CHAT_ID` | Telegram numerical Chat ID | `""` |
| `PAYOUT_WALLET_ADDRESS` | User payout crypto wallet | `""` |
| `PAYOUT_CURRENCY` | Payout network / currency token | `USDT_BSC` |
| `SIMULATION_MODE` | `true` for paper trading; `false` for live betting | `true` |
| `ENABLE_DYNAMIC_SIZING` | Auto-calculates stakes using bankroll & confidence | `true` |
| `BASE_BANKROLL_PERCENT` | Base percentage of bankroll per wager | `0.02` (2%) |
| `MIN_STAKE` / `MAX_BET_CAP` | Minimum floor and maximum ceiling per bet | `$0.50` / `$10.00` |
| `MIN_CONFIDENCE_THRESHOLD`| Conviction threshold required to place a bet | `0.75` (75%) |
| `MIN_ODDS` / `MAX_ODDS` | Acceptable decimal odds range | `1.40` – `4.50` |
| `MAX_DAILY_BETS` / `MAX_WEEKLY_BETS` | Trade caps to prevent overtrading | `4` / `25` |
| `POLL_INTERVAL_SECONDS` | Match polling frequency in seconds | `15` |

---

## 📁 Project Structure

* [`config.py`](config.py) — Environment loader with safety limits and validation.
* [`sofascore_client.py`](sofascore_client.py) — Zero-cost real-time SofaScore engine for live scores, xG, momentum graphs, and stats.
* [`BETTING_STRATEGY.md`](BETTING_STRATEGY.md) — Quantitative in-play strategy breakdown, trigger patterns, and Kelly dynamic sizing rules.
* [`strategy.py`](strategy.py) — Autonomous live decision engine, disqualification filters, and dynamic sizing.
* [`stake_browser.py`](stake_browser.py) — Playwright persistent browser controller for Stake.com with automatic TOTP 2FA.
* [`financial_manager.py`](financial_manager.py) — SQLite ledger tracking bankroll, expenses, and wage distributions.
* [`telegram_notifier.py`](telegram_notifier.py) — Real-time alerts, slip photos, and reports on Telegram.
* [`bot.py`](bot.py) — CLI runner and orchestration loop.
