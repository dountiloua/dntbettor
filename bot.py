"""
Main Entry Point & Orchestrator for the Autonomous Betting Bot.
Powered by Zero-Cost SofaScore Live Engine, Real-Time xG & Momentum Analytics,
Dynamic Bankroll Allocation Waterfall, Stake Browser Automation, and Telegram Alerts.
"""

import sys
import asyncio
import argparse
from pathlib import Path
from datetime import datetime, timezone
from config import Config
from sofascore_client import SofaScoreClient
from strategy import StrategyEngine
from stake_browser import StakeBrowser
from financial_manager import FinancialManager
from telegram_notifier import TelegramNotifier
from gemini_agent import GeminiAgent

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def show_financials():
    fm = FinancialManager()
    status = fm.get_status()
    wallet = Config.PAYOUT_WALLET_ADDRESS or "NOT CONFIGURED (Edit .env to link wallet)"
    print("\n==========================================================")
    print("  📊 BOT FINANCIAL HEALTH & EXPENSES LEDGER")
    print("==========================================================")
    print(f"  💰 Active Bankroll:          ${status['current_bankroll']:.2f}")
    print(f"  💼 User Monthly Wage Pool:    ${status['user_wage_pool']:.2f} (Available for payout)")
    print(f"  💵 Bot Bills Reserve Pool:    ${status['bills_reserve_pool']:.2f}")
    print(f"  🛡️ Emergency Buffer:          ${status['emergency_pool']:.2f}")
    print("----------------------------------------------------------")
    print(f"  📈 Total Net Profit Made:     ${status['total_profit_generated']:.2f}")
    print(f"  🧾 Total Bills Paid:          ${status['total_bills_paid']:.2f}")
    print(f"  ⚡ Estimated Monthly Bills:   ${status['estimated_monthly_bills']:.2f}/mo (VPS + Proxies | $0 API Cost)")
    print(f"  ⏳ Bills Coverage:            {status['bills_coverage_months']} months prepaid")
    print(f"  🚨 Circuit Breaker Tripped:   {'YES (Trading Halted)' if status['circuit_breaker_tripped'] else 'NO (Healthy)'}")
    print("----------------------------------------------------------")
    print(f"  🏦 Linked Payout Wallet:     {wallet}")
    print(f"  🪙 Payout Currency:          {Config.PAYOUT_CURRENCY}")
    print(f"  🎯 Minimum Payout Threshold: ${Config.PAYOUT_MIN_THRESHOLD:.2f}")
    print("==========================================================\n")


def execute_payout():
    if not Config.PAYOUT_WALLET_ADDRESS or Config.PAYOUT_WALLET_ADDRESS == "your_public_wallet_address_here":
        print("\n❌ Error: No payout wallet address configured in .env!")
        print("   Please open .env and set PAYOUT_WALLET_ADDRESS=your_wallet_address\n")
        return

    fm = FinancialManager()
    status = fm.get_status()
    wage_pool = status["user_wage_pool"]
    
    print(f"\n--- Requesting Wage Payout ---")
    print(f"Available Wage Pool: ${wage_pool:.2f}")
    print(f"Destination: {Config.PAYOUT_WALLET_ADDRESS} ({Config.PAYOUT_CURRENCY})")

    if wage_pool < Config.PAYOUT_MIN_THRESHOLD:
        print(f"⚠️ Minimum threshold (${Config.PAYOUT_MIN_THRESHOLD:.2f}) not yet reached. Current: ${wage_pool:.2f}\n")
        return

    res = fm.process_user_wage_payout(
        destination_address=Config.PAYOUT_WALLET_ADDRESS,
        currency=Config.PAYOUT_CURRENCY
    )
    if res.get("success"):
        print(f"✅ Payout Processed Successfully!")
        print(f"   Transferred: ${res['amount']:.2f} {res['currency']}")
        print(f"   Sent to: {res['destination_address']}")
        print(f"   Remaining Wage Pool: ${res['remaining_wage_pool']:.2f}\n")
    else:
        print(f"❌ Payout Failed: {res.get('error')}\n")


async def test_sofascore():
    print("\n--- Testing SofaScore Zero-Cost Live Engine ---")
    client = SofaScoreClient(headless=True)
    await client.start()
    try:
        matches = await client.get_live_matches()
        print(f"✅ Successfully connected to SofaScore! Found {len(matches)} active live matches worldwide.")
        
        if matches:
            sample = matches[0]
            print(f"\n[*] Sample Live Match: {sample['home_team']} {sample['home_score']} - {sample['away_score']} {sample['away_team']}")
            print(f"    League: {sample['league']} | Minute: {sample['minute']}' | Status: {sample['status']}")
            
            # Fetch stats
            stats = await client.get_match_stats(sample["id"])
            if stats:
                print(f"    🎯 xG: Home {stats.get('home_xg', 0):.2f} - Away {stats.get('away_xg', 0):.2f}")
                print(f"    📦 Shots Inside Box: Home {stats.get('home_shots_inside_box', 0)} - Away {stats.get('away_shots_inside_box', 0)}")
                print(f"    🚩 Corners: Home {stats.get('home_corners', 0)} - Away {stats.get('away_corners', 0)}")

            # Fetch momentum
            momentum = await client.get_attack_momentum(sample["id"])
            if momentum:
                print(f"    🔥 10m Momentum: Home {momentum.get('last_10m_home_momentum', 0)} | Away {momentum.get('last_10m_away_momentum', 0)} (Dominant: {momentum.get('dominant_side')})")
    finally:
        await client.close()
    print("--- SofaScore Test Completed Successfully ---\n")


async def test_stake():
    print("\n--- Testing Stake Browser (Simulation Mode) ---")
    browser = StakeBrowser(headless=False)
    await browser.start()
    print("Navigating to Stake Sportsbook...")
    await browser.page.goto(f"{Config.STAKE_BASE_URL}/sports", wait_until="domcontentloaded")
    title = await browser.page.title()
    print(f"Page loaded: {title}")
    
    # Test 2FA generator
    two_fa = StakeBrowser.get_2fa_code()
    if two_fa:
        print(f"🔑 Live 2FA TOTP Generator Active: {two_fa} (Synced with Google Authenticator)")
    
    await asyncio.sleep(3)
    await browser.close()
    print("Stake connection test passed!")


async def test_telegram():
    print("\n--- Testing Telegram Connection ---")
    telegram = TelegramNotifier()
    if not telegram.enabled:
        print("Telegram notifications are disabled in .env (TELEGRAM_ENABLED=false).")
        return
    
    msg = (
        "🤖 <b>Autonomous Betting Bot Online!</b>\n\n"
        "• Data Engine: <b>SofaScore Live (Zero API Cost)</b>\n"
        "• Telegram Alert Channel: <b>Connected</b>\n"
        f"• Simulation Mode: <b>{'ENABLED' if Config.SIMULATION_MODE else 'DISABLED (LIVE)'}</b>\n"
        f"• Active Bankroll: <b>${FinancialManager().get_status()['current_bankroll']:.2f}</b>\n"
        f"• Sizing Engine: <b>{'Kelly Dynamic Sizing' if Config.ENABLE_DYNAMIC_SIZING else 'Fixed'}</b>"
    )
    success = await telegram.send_message(msg)
    if success:
        print("✅ Telegram test message sent successfully! Check your Telegram chat.")
    else:
        print("❌ Failed to send Telegram test message. Check your bot token and chat ID.")


async def test_gemini():
    """Tests the Gemini AI Agent connection and runs a sample match evaluation."""
    print("\n--- Testing Gemini AI Agent ---")
    
    if not Config.GEMINI_API_KEY or Config.GEMINI_API_KEY == "your_gemini_api_key_here":
        print("❌ GEMINI_API_KEY is not configured in .env!")
        print("   Add: GEMINI_API_KEY=your_key  (get one free at https://aistudio.google.com/)")
        return

    agent = GeminiAgent()
    print(f"🤖 Model:      {Config.GEMINI_MODEL}")
    print(f"⚙️  Mode:       {Config.GEMINI_AI_MODE.upper()}")
    print("🔗 Connecting to Gemini API...")
    
    result = await agent.test_connection()

    if result.get("success"):
        print(f"✅ Gemini connection successful! Model: {result['model']}")
        decision = result.get("sample_decision", {})
        if decision.get("decision") == "BET":
            print(f"\n[🎯 SAMPLE MATCH: Man City vs Arsenal — 67' (1-1)]")
            print(f"   Decision:    {decision['decision']}")
            print(f"   Market:      {decision.get('market', 'N/A')}")
            print(f"   Confidence:  {decision.get('confidence', 0) * 100:.0f}%")
            print(f"   Risk:        {decision.get('risk_rating', 'N/A')}")
            print(f"   Odds Est:    {decision.get('odds_estimate', 'N/A')}")
            print(f"   Reasoning:   {decision.get('reasoning', 'N/A')}")
        else:
            print(f"\n[Sample Match] Gemini decision: NO_BET")
            print(f"   Reasoning: {decision.get('reasoning', 'N/A')}")
    else:
        print(f"❌ Gemini connection failed: {result.get('error')}")

    print("--- Gemini AI Agent Test Complete ---\n")


async def run_bot(single_cycle: bool = False, headless: bool = False):
    fm = FinancialManager()
    status = fm.get_status()
    telegram = TelegramNotifier()

    if status["circuit_breaker_tripped"]:
        alert = (
            "🚨 <b>CIRCUIT BREAKER ACTIVE!</b>\n"
            "Live betting is paused to preserve capital due to max drawdown limit.\n"
            f"Current Bankroll: ${status['current_bankroll']:.2f}"
        )
        print(f"\n{alert}\n")
        await telegram.send_message(alert)
        return

    print("==========================================================")
    print("  Starting SofaScore -> Stake Autonomous Betting Bot")
    print(f"  Data Source:     SofaScore Real-Time Engine ($0 API Cost)")
    print(f"  AI Agent:        {'Gemini ' + Config.GEMINI_MODEL if Config.GEMINI_API_KEY else 'Rule-Based Fallback'}")
    print(f"  AI Mode:         {Config.GEMINI_AI_MODE.upper()}")
    print(f"  Simulation Mode: {'ENABLED (Paper Trading)' if Config.SIMULATION_MODE else 'DISABLED (LIVE BETS!)'}")
    print(f"  Active Bankroll: ${status['current_bankroll']:.2f}")
    print(f"  User Wage Pool:  ${status['user_wage_pool']:.2f}")
    print(f"  Sizing Mode:     {'Dynamic Kelly-Scaled' if Config.ENABLE_DYNAMIC_SIZING else 'Fixed'}")
    print(f"  Min Confidence:  {Config.MIN_CONFIDENCE_THRESHOLD * 100:.0f}%")
    print(f"  Telegram Alerts: {'ENABLED' if telegram.enabled else 'DISABLED'}")
    print(f"  Poll Interval:   {Config.POLL_INTERVAL_SECONDS}s")
    print("==========================================================\n")

    sofascore = SofaScoreClient(headless=True)
    strategy = StrategyEngine()
    browser = StakeBrowser(headless=headless)
    telegram_task = asyncio.create_task(telegram_command_loop(telegram)) if telegram.is_configured else None
    
    await sofascore.start()
    await browser.start()

    placed_signals = set()

    try:
        while True:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            print(f"[{now_str}] Polling live matches from SofaScore...")
            
            try:
                live_matches = await sofascore.get_live_matches()
                print(f"[*] Found {len(live_matches)} active in-play matches worldwide.")
                
                signals_processed = 0
                for match in live_matches:
                    match_id = match.get("id")
                    if match_id in placed_signals:
                        continue

                    minute = match.get("minute", 0)
                    # Candidate filter: check games between 15' and 86'
                    if 15 <= minute <= 86:
                        # Fetch in-depth stats & momentum
                        stats = await sofascore.get_match_stats(match_id)
                        momentum = await sofascore.get_attack_momentum(match_id)
                        
                        current_bankroll = fm.get_status()["current_bankroll"]
                        signal = await strategy.evaluate_live_match(
                            match=match,
                            stats=stats,
                            momentum=momentum,
                            bankroll=current_bankroll
                        )

                        if signal:
                            # Verify trade caps (Min 0, Max 4/day, Max 25/week)
                            can_place, reason = fm.can_place_new_bet(
                                max_daily=Config.MAX_DAILY_BETS,
                                max_weekly=Config.MAX_WEEKLY_BETS
                            )
                            if not can_place:
                                print(f"\n[⏸️ TRADE CAP] Skipping signal for {signal.home_team} vs {signal.away_team}: {reason}")
                                continue

                            signals_processed += 1
                            print(f"\n[🎯 HIGH-CONVICTION SIGNAL] {signal.home_team} vs {signal.away_team} -> {signal.target_market}")
                            print(f"   Minute: {signal.current_minute}' ({signal.current_score}) | Conviction: {signal.confidence_score*100:.0f}%")
                            print(f"   Calculated Dynamic Stake: ${signal.stake_amount:.2f}")
                            print(f"   Reasoning: {signal.reasoning}")
                            
                            # Execute bet on Stake
                            success = await browser.execute_bet_flow(signal)
                            if success:
                                placed_signals.add(match_id)
                                # Record bet in financial ledger
                                fm.record_bet_placement(
                                    match_id=match_id,
                                    match_name=f"{signal.home_team} vs {signal.away_team}",
                                    market=signal.target_market,
                                    stake_amount=signal.stake_amount,
                                    odds=signal.odds_estimate
                                )

                                # Send Telegram notification
                                screenshot_path = Config.BASE_DIR / "browser_data" / f"sim_bet_{signal.match_id}.png"
                                await telegram.notify_bet_placed(
                                    signal=signal,
                                    is_simulation=Config.SIMULATION_MODE,
                                    screenshot_path=screenshot_path if screenshot_path.exists() else None
                                )

                            if single_cycle and signals_processed >= 1:
                                break

            except Exception as e:
                print(f"[Bot] Polling loop error: {e}")

            if single_cycle:
                print("[Bot] Single cycle complete.")
                break

            await asyncio.sleep(Config.POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("\n[Bot] Shutting down gracefully...")
    finally:
        if telegram_task:
            telegram_task.cancel()
        await sofascore.close()
        await browser.close()


async def telegram_command_loop(telegram: TelegramNotifier):
    """Answers authorized Telegram questions while the worker is running."""
    agent = GeminiAgent()
    offset = 0
    while True:
        updates = await telegram.get_updates(offset)
        for update in updates:
            offset = update.get("update_id", offset) + 1
            message = update.get("message", {})
            chat_id = str(message.get("chat", {}).get("id", ""))
            text = message.get("text", "").strip()
            if chat_id != str(Config.TELEGRAM_CHAT_ID) or not text:
                continue
            if text.lower() in ("/strategy", "what is your strategy", "what's your strategy"):
                answer = await agent.answer_question("Explain your current live football betting strategy concisely.")
                await telegram.send_message(answer or "Gemini is unavailable right now.", parse_mode="")
            elif text.lower() == "/status":
                await telegram.send_message("The betting worker is online and monitoring matches.")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Football Betting Bot")
    parser.add_argument("--login", action="store_true", help="Launch interactive browser to log into Stake.com")
    parser.add_argument("--test-sofascore", action="store_true", help="Test SofaScore live client and real-time stats")
    parser.add_argument("--test-stake", action="store_true", help="Test Stake browser automation")
    parser.add_argument("--test-telegram", action="store_true", help="Test Telegram bot token and chat connection")
    parser.add_argument("--test-gemini", action="store_true", help="Test Gemini AI agent connection and run a sample match evaluation")
    parser.add_argument("--financials", action="store_true", help="Display bankroll health, bills reserve, and user wage pool")
    parser.add_argument("--withdraw", action="store_true", help="Execute payout of available wage pool to your linked wallet")
    parser.add_argument("--run", action="store_true", help="Run the live monitoring and auto-betting loop")
    parser.add_argument("--single-cycle", action="store_true", help="Run a single live scanning cycle and exit")
    parser.add_argument("--headless", action="store_true", help="Run Stake browser in headless mode")

    args = parser.parse_args()

    if args.login:
        browser = StakeBrowser(headless=False)
        asyncio.run(browser.login_interactive())
    elif args.test_sofascore:
        asyncio.run(test_sofascore())
    elif args.test_stake:
        asyncio.run(test_stake())
    elif args.test_telegram:
        asyncio.run(test_telegram())
    elif args.test_gemini:
        asyncio.run(test_gemini())
    elif args.financials:
        show_financials()
    elif args.withdraw:
        execute_payout()
    elif args.run or args.single_cycle:
        is_headless = args.headless or args.single_cycle
        asyncio.run(run_bot(single_cycle=args.single_cycle, headless=is_headless))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
