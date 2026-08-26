"""
Test Suite for StrategyEngine: Autonomous Decision Logic & Dynamic Stake Sizing
"""

import sys
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from strategy import StrategyEngine, BetSignal
from config import Config


def test_dynamic_stake_calculation():
    print("\n--- Testing Dynamic Stake Sizing Calculations ---")
    engine = StrategyEngine(
        min_confidence=0.75,
        base_bankroll_pct=0.02, # 2%
        min_stake=0.50,
        max_bet_cap=10.00
    )

    # Test 1: Standard bankroll ($100), base confidence (75%)
    stake1 = engine.calculate_dynamic_stake(bankroll=100.0, confidence_score=0.75, odds_estimate=1.80)
    print(f"Bankroll $100 | Confidence 75% | Odds 1.80 -> Stake: ${stake1:.2f} (Expected ~$2.00)")
    assert 1.90 <= stake1 <= 2.10, f"Expected ~$2.00, got {stake1}"

    # Test 2: Standard bankroll ($100), high conviction (95%)
    stake2 = engine.calculate_dynamic_stake(bankroll=100.0, confidence_score=0.95, odds_estimate=1.80)
    print(f"Bankroll $100 | Confidence 95% | Odds 1.80 -> Stake: ${stake2:.2f} (Expected ~$3.20 - $3.50)")
    assert stake2 > stake1, "High conviction stake should be greater than base stake"

    # Test 3: Large bankroll ($1000) hitting MAX_BET_CAP ($10.00)
    stake3 = engine.calculate_dynamic_stake(bankroll=1000.0, confidence_score=0.85, odds_estimate=1.80)
    print(f"Bankroll $1000 | Confidence 85% -> Stake: ${stake3:.2f} (Expected capped at $10.00)")
    assert stake3 == 10.00, f"Expected cap $10.00, got {stake3}"

    # Test 4: Small bankroll ($10) hitting MIN_STAKE ($0.50)
    stake4 = engine.calculate_dynamic_stake(bankroll=10.0, confidence_score=0.75, odds_estimate=1.80)
    print(f"Bankroll $10 | Confidence 75% -> Stake: ${stake4:.2f} (Expected floor at $0.50)")
    assert stake4 == 0.50, f"Expected min floor $0.50, got {stake4}"

    # Test 5: High odds damping (odds = 3.50)
    stake5 = engine.calculate_dynamic_stake(bankroll=100.0, confidence_score=0.85, odds_estimate=3.50)
    print(f"Bankroll $100 | Confidence 85% | Odds 3.50 (High Odds) -> Stake: ${stake5:.2f} (Risk damped)")
    assert stake5 < stake2, "Higher odds should be damped to control drawdown"

    print("✅ All Dynamic Stake tests PASSED!")


def test_autonomous_bet_decision_rules():
    print("\n--- Testing 'When to Bet vs. When NOT to Bet' Rules ---")
    engine = StrategyEngine(min_confidence=0.75)

    # 1. QUALIFIED: Minute 65, 1-1 score (Pattern 1) -> BET
    match_ok = {
        "id": "match_001",
        "home": {"name": "Arsenal", "score": 1},
        "away": {"name": "Chelsea", "score": 1},
        "leagueName": "Premier League",
        "status": {"started": True, "finished": False, "liveTime": {"minute": 65}}
    }
    signal = engine.evaluate_live_match(match_ok, bankroll=150.0)
    assert signal is not None, "Match should trigger a BetSignal"
    print(f"✅ Approved Match: {signal.target_market} | Stake: ${signal.stake_amount:.2f} | Conviction: {signal.confidence_score*100:.0f}%")

    # 2. DISQUALIFIED: Minute 8 (Too early) -> DO NOT BET
    match_early = {
        "id": "match_002",
        "home": {"name": "Bayern", "score": 0},
        "away": {"name": "Dortmund", "score": 0},
        "status": {"started": True, "finished": False, "liveTime": {"minute": 8}}
    }
    assert engine.evaluate_live_match(match_early) is None, "Early game should be rejected"
    print("✅ Disqualification (Minute < 15): Rejected as expected.")

    # 3. DISQUALIFIED: Minute 70, 4-0 Blowout -> DO NOT BET
    match_blowout = {
        "id": "match_003",
        "home": {"name": "Real Madrid", "score": 4},
        "away": {"name": "Getafe", "score": 0},
        "status": {"started": True, "finished": False, "liveTime": {"minute": 70}}
    }
    assert engine.evaluate_live_match(match_blowout) is None, "Blowout game should be rejected"
    print("✅ Disqualification (Blowout score diff >= 3): Rejected as expected.")

    # 4. DISQUALIFIED: Finished match -> DO NOT BET
    match_finished = {
        "id": "match_004",
        "home": {"name": "Liverpool", "score": 2},
        "away": {"name": "Man City", "score": 2},
        "status": {"started": True, "finished": True, "liveTime": {"minute": 90}}
    }
    assert engine.evaluate_live_match(match_finished) is None, "Finished game should be rejected"
    print("✅ Disqualification (Finished match): Rejected as expected.")

    print("✅ All Autonomous Decision tests PASSED!\n")


if __name__ == "__main__":
    test_dynamic_stake_calculation()
    test_autonomous_bet_decision_rules()
