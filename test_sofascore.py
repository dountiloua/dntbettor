"""
Comprehensive SofaScore Engine & Strategy Verification Suite.
Validates live match retrieval, in-depth xG parsing, Attack Momentum graph calculation,
and strategy evaluation on live active matches.
"""

import sys
import asyncio
from sofascore_client import SofaScoreClient
from strategy import StrategyEngine
from financial_manager import FinancialManager

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


async def main():
    print("==========================================================")
    print("  🧪 Running SofaScore Live Engine Verification Suite")
    print("==========================================================")

    client = SofaScoreClient(headless=True)
    strategy = StrategyEngine()
    fm = FinancialManager()
    bankroll = fm.get_status()["current_bankroll"]

    await client.start()
    try:
        print("[1/4] Fetching all live matches worldwide...")
        matches = await client.get_live_matches()
        print(f"      -> Retrieved {len(matches)} active matches.")

        if not matches:
            print("⚠️ No live matches currently active to test. Testing complete.")
            return

        print(f"\n[2/4] Testing deep stats & momentum parsing on sample matches...")
        evaluated_count = 0
        signals_triggered = 0

        for match in matches[:8]:
            match_id = match["id"]
            minute = match["minute"]
            home = match["home_team"]
            away = match["away_team"]
            score = f"{match['home_score']} - {match['away_score']}"

            print(f"\n   ⚽ Match: {home} {score} {away} (Min: {minute}') [ID: {match_id}]")
            print(f"      League: {match['league']} | Status: {match['status']}")

            # Fetch stats
            stats = await client.get_match_stats(match_id)
            if stats:
                print(f"      🎯 xG: Home {stats['home_xg']:.2f} | Away {stats['away_xg']:.2f} (Total xG: {stats['home_xg'] + stats['away_xg']:.2f})")
                print(f"      📦 Shots Inside Box: Home {stats['home_shots_inside_box']} | Away {stats['away_shots_inside_box']}")
                print(f"      🚩 Corners: Home {stats['home_corners']} | Away {stats['away_corners']}")
                print(f"      🧤 Saves: Home {stats['home_goalkeeper_saves']} | Away {stats['away_goalkeeper_saves']}")

            # Fetch momentum
            momentum = await client.get_attack_momentum(match_id)
            if momentum:
                print(f"      🔥 Attack Momentum: Home {momentum['last_10m_home_momentum']} | Away {momentum['last_10m_away_momentum']} (Dominant: {momentum['dominant_side']})")

            # Strategy evaluation
            signal = strategy.evaluate_live_match(
                match=match,
                stats=stats,
                momentum=momentum,
                bankroll=bankroll
            )

            evaluated_count += 1
            if signal:
                signals_triggered += 1
                print(f"      🟢 [SIGNAL TRIGGERED] Market: {signal.target_market}")
                print(f"         Confidence: {signal.confidence_score*100:.0f}% | Dynamic Stake: ${signal.stake_amount:.2f}")
                print(f"         Reason: {signal.reasoning}")
            else:
                print(f"      ⚪ [No Signal / Filtered] Waiting for optimal mathematical setup.")

        print("\n==========================================================")
        print(f"  ✅ Verification Summary:")
        print(f"     - Total Matches Evaluated: {evaluated_count}")
        print(f"     - High-Conviction Signals Found: {signals_triggered}")
        print(f"     - API Cost Incurred: $0.00 (Zero tokens)")
        print("==========================================================\n")

    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
