"""
Autonomous Betting Strategy & Dynamic Stake Sizing Engine.
In Full Agent Mode (GEMINI_AI_MODE=agent), this module delegates live match
evaluation entirely to the GeminiAgent, which acts as the AI brain.
The original quantitative patterns serve as a fallback if Gemini is unavailable.

Analyzes live match metrics (minute, scoreline, tempo, momentum, xG, shot zones)
to autonomously determine:
1. When to bet (high-conviction quantitative patterns / AI decision).
2. When NOT to bet (disqualifications, blowout filters, low confidence).
3. The exact dynamic stake amount (bankroll percentage, Kelly-inspired conviction scaling).
"""

import asyncio
from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel
from config import Config


class BetSignal(BaseModel):
    match_id: str | int
    home_team: str
    away_team: str
    league: str
    target_market: str              # e.g., "Over 2.5 Goals", "Next Goal: Chelsea", "Double Chance: 1X"
    reasoning: str
    current_minute: Optional[int] = None
    current_score: Optional[str] = None
    confidence_score: float         # 0.0 to 1.0 (e.g. 0.84 = 84% conviction)
    risk_rating: str = "MEDIUM"     # "LOW", "MEDIUM", "HIGH"
    odds_estimate: float = 1.80     # Estimated decimal odds
    stake_amount: float = 1.00      # Dynamically calculated stake in currency units
    home_xg: Optional[float] = None
    away_xg: Optional[float] = None
    dominant_side: Optional[str] = None


class StrategyEngine:
    def __init__(
        self,
        min_confidence: Optional[float] = None,
        base_bankroll_pct: Optional[float] = None,
        min_stake: Optional[float] = None,
        max_bet_cap: Optional[float] = None,
    ):
        self.min_confidence = min_confidence or Config.MIN_CONFIDENCE_THRESHOLD
        self.base_bankroll_pct = base_bankroll_pct or Config.BASE_BANKROLL_PERCENT
        self.min_stake = min_stake or Config.MIN_STAKE
        self.max_bet_cap = max_bet_cap or Config.MAX_BET_CAP

        # Lazy-load GeminiAgent only if AI mode is enabled
        self._gemini: Optional[Any] = None
        if Config.GEMINI_AI_MODE == "agent" and Config.GEMINI_API_KEY:
            try:
                from gemini_agent import GeminiAgent
                self._gemini = GeminiAgent()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"[StrategyEngine] Could not initialise GeminiAgent: {e}. "
                    "Falling back to rule-based patterns."
                )

    def calculate_dynamic_stake(
        self,
        bankroll: float,
        confidence_score: float,
        odds_estimate: float = 1.80
    ) -> float:
        """
        Dynamically calculates the exact bet amount based on:
        - Current available bankroll
        - Strategy confidence level (0.75 - 1.0)
        - Odds variance damping (smaller stake for high-odds to manage drawdown)
        - Hard safety bounds (min_stake and max_bet_cap)
        """
        if not Config.ENABLE_DYNAMIC_SIZING or bankroll <= 0:
            return round(min(Config.BET_AMOUNT, self.max_bet_cap), 2)

        # 1. Base stake = % of current bankroll
        base_stake = bankroll * self.base_bankroll_pct

        # 2. Conviction multiplier: scales stake between 1.0x (at min_confidence) to 1.75x (at 95%+ confidence)
        conviction_span = max(0.01, 1.0 - self.min_confidence)
        excess_confidence = max(0.0, confidence_score - self.min_confidence)
        conviction_multiplier = 1.0 + (excess_confidence / conviction_span) * 0.75

        # 3. Odds Damping: Adjust for variance if odds are high (> 2.20)
        odds_damp = min(1.0, 2.0 / max(1.0, odds_estimate))

        # 4. Raw dynamic stake calculation
        raw_stake = base_stake * conviction_multiplier * odds_damp

        # 5. Enforce hard floor and hard ceiling
        final_stake = max(self.min_stake, min(raw_stake, self.max_bet_cap))
        return round(final_stake, 2)

    async def evaluate_live_match(
        self,
        match: Dict[str, Any],
        stats: Optional[Dict[str, Any]] = None,
        momentum: Optional[Dict[str, Any]] = None,
        bankroll: float = 100.0
    ) -> Optional[BetSignal]:
        """
        Autonomously analyses a live match to decide:
        1. Whether to BET or NOT TO BET.
        2. Which market offers mathematical value.
        3. The dynamic stake amount for the trade.

        In Full Agent Mode (GEMINI_AI_MODE=agent), delegates the decision
        entirely to Google Gemini, with a rule-based fallback if Gemini fails.
        """
        # ── FULL AGENT MODE: delegate to Gemini ──────────────────────────────
        if self._gemini and self._gemini.enabled:
            ai_result = await self._gemini.evaluate_match(match, stats, momentum)
            if ai_result is not None:
                return self._build_signal_from_ai(match, stats, momentum, ai_result, bankroll)
            if Config.GEMINI_AI_MODE == "agent":
                return None
            # Hybrid mode uses the deterministic strategy when Gemini is unavailable.

        # ── FALLBACK: original rule-based evaluation ──────────────────────────
        return self._evaluate_rules(match, stats, momentum, bankroll)

    def _build_signal_from_ai(
        self,
        match: Dict[str, Any],
        stats: Optional[Dict[str, Any]],
        momentum: Optional[Dict[str, Any]],
        ai_result: Dict[str, Any],
        bankroll: float,
    ) -> Optional[BetSignal]:
        """Converts a Gemini AI decision dict into a fully populated BetSignal."""
        home_team = match.get("home_team", match.get("home", {}).get("name", "Home"))
        away_team = match.get("away_team", match.get("away", {}).get("name", "Away"))
        home_score = match.get("home_score", match.get("home", {}).get("score", 0))
        away_score = match.get("away_score", match.get("away", {}).get("score", 0))
        league = match.get("league", match.get("leagueName", "General"))
        match_id = match.get("id")
        minute = match.get("minute", 0)

        confidence = float(ai_result.get("confidence", 0.0))
        if confidence < self.min_confidence:
            return None

        odds_est = float(ai_result.get("odds_estimate", 1.80))
        # Enforce configured odds bounds
        if odds_est < Config.MIN_ODDS or odds_est > Config.MAX_ODDS:
            # Clamp to range instead of rejecting
            odds_est = max(Config.MIN_ODDS, min(odds_est, Config.MAX_ODDS))

        stake = self.calculate_dynamic_stake(
            bankroll=bankroll,
            confidence_score=confidence,
            odds_estimate=odds_est
        )

        home_xg = stats.get("home_xg", None) if stats else None
        away_xg = stats.get("away_xg", None) if stats else None
        dominant_side = momentum.get("dominant_side", "NEUTRAL") if momentum else "NEUTRAL"

        # Prefix reasoning with AI badge
        reasoning = f"[🤖 Gemini AI] {ai_result.get('reasoning', '')}"

        return BetSignal(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league=league,
            target_market=ai_result.get("market", "Unknown Market"),
            reasoning=reasoning,
            current_minute=minute,
            current_score=f"{home_score} - {away_score}",
            confidence_score=round(confidence, 2),
            risk_rating=ai_result.get("risk_rating", "MEDIUM"),
            odds_estimate=odds_est,
            stake_amount=stake,
            home_xg=home_xg if home_xg and home_xg > 0 else None,
            away_xg=away_xg if away_xg and away_xg > 0 else None,
            dominant_side=dominant_side if dominant_side != "NEUTRAL" else None,
        )

    def _evaluate_rules(
        self,
        match: Dict[str, Any],
        stats: Optional[Dict[str, Any]] = None,
        momentum: Optional[Dict[str, Any]] = None,
        bankroll: float = 100.0
    ) -> Optional[BetSignal]:
        """
        Original rule-based evaluation (fallback when Gemini is unavailable).
        Autonomously analyses a live match to decide:
        1. Whether to BET or NOT TO BET.
        2. Which market offers mathematical value.
        3. The dynamic stake amount for the trade.
        """
        # Extract status & minute supporting both flat and nested match payload formats
        status_obj = match.get("status", {})
        if isinstance(status_obj, dict):
            if status_obj.get("finished") or status_obj.get("cancelled"):
                return None
            if "started" in status_obj and not status_obj.get("started"):
                return None

        minute = match.get("minute")
        if minute is None and isinstance(status_obj, dict):
            minute = status_obj.get("liveTime", {}).get("minute", 0)
        minute = minute or 0

        home_team = match.get("home_team", match.get("home", {}).get("name", "Home"))
        away_team = match.get("away_team", match.get("away", {}).get("name", "Away"))
        
        home_score = match.get("home_score")
        if home_score is None:
            home_score = match.get("home", {}).get("score", 0)
            
        away_score = match.get("away_score")
        if away_score is None:
            away_score = match.get("away", {}).get("score", 0)

        league_name = match.get("league", match.get("leagueName", "General"))
        match_id = match.get("id")
        score_diff = abs(home_score - away_score)
        total_goals = home_score + away_score

        # =========================================================================
        # 🛑 DISQUALIFICATION GATES ("When NOT to Bet")
        # =========================================================================

        # Gate 0: League Whitelist Filter (if configured)
        if Config.ALLOWED_LEAGUES:
            allowed = [l.strip().lower() for l in Config.ALLOWED_LEAGUES.split(",") if l.strip()]
            if allowed and not any(kw in league_name.lower() for kw in allowed):
                return None

        # Gate 1: Early Game or Late Injury Time Filter
        if minute < 15 or minute > 86:
            return None

        # Gate 2: Blowout Game Filter (teams reduce intensity, poor risk-reward)
        if score_diff >= 3 and minute >= 60:
            return None

        # Gate 3: Red Card Anomaly Check
        if stats:
            home_red = stats.get("home_red_cards", 0)
            away_red = stats.get("away_red_cards", 0)
            if home_red + away_red >= 2:
                # Disqualify matches with high chaos / multiple ejections
                return None

        # Extract deep SofaScore metrics if present
        home_xg = stats.get("home_xg", 0.0) if stats else 0.0
        away_xg = stats.get("away_xg", 0.0) if stats else 0.0
        total_xg = home_xg + away_xg
        home_box_shots = stats.get("home_shots_inside_box", 0) if stats else 0
        away_box_shots = stats.get("away_shots_inside_box", 0) if stats else 0
        total_box_shots = home_box_shots + away_box_shots
        total_corners = (stats.get("home_corners", 0) + stats.get("away_corners", 0)) if stats else 0
        
        last_10m_home_m = momentum.get("last_10m_home_momentum", 0.0) if momentum else 0.0
        last_10m_away_m = momentum.get("last_10m_away_momentum", 0.0) if momentum else 0.0
        dominant_side = momentum.get("dominant_side", "NEUTRAL") if momentum else "NEUTRAL"

        # =========================================================================
        # 🟢 HIGH-CONVICTION QUANTITATIVE PATTERNS ("When to Bet")
        # =========================================================================

        candidate_signal: Optional[Tuple[str, str, float, str, float]] = None
        # Format: (target_market, reasoning, confidence_score, risk_rating, odds_estimate)

        # --- Pattern 1: xG Surge & Box Pressure Over (Minutes 55 - 78) ---
        # High offensive creation (high xG or box shots) with tight scoreline
        if 55 <= minute <= 78 and total_goals in (0, 1, 2, 3) and score_diff <= 1:
            if (total_xg >= 1.4 or total_box_shots >= 7 or (last_10m_home_m > 30 or last_10m_away_m > 30)):
                next_goal_line = total_goals + 0.5
                confidence = 0.88 if (total_xg >= 1.8 or total_box_shots >= 10) else 0.82
                candidate_signal = (
                    f"Over {next_goal_line} Match Goals",
                    f"High attacking pressure at min {minute}' (xG: {total_xg:.2f}, Box Shots: {total_box_shots}, Pressure: {dominant_side}).",
                    confidence,
                    "LOW" if confidence >= 0.85 else "MEDIUM",
                    1.78
                )

        # --- Pattern 2: Trailing Dominant Team Push (Minutes 50 - 75) ---
        # Home team trailing 0-1 but having higher xG/momentum
        if not candidate_signal and 50 <= minute <= 75 and home_score == 0 and away_score == 1:
            if home_xg >= 0.8 or last_10m_home_m >= 25 or home_box_shots >= 4:
                candidate_signal = (
                    f"{home_team} or Draw (Double Chance 1X)",
                    f"Home side ({home_team}) trailing 0-1 at min {minute}' with high comeback momentum (xG: {home_xg:.2f}, Pressure: {last_10m_home_m:.0f}).",
                    0.83,
                    "MEDIUM",
                    1.85
                )

        # --- Pattern 3: Second-Half General Goal Pressure (Minutes 58 - 76) ---
        if not candidate_signal and 58 <= minute <= 76 and total_goals in (1, 2, 3) and score_diff <= 1:
            next_goal_line = total_goals + 0.5
            confidence = 0.84 if minute >= 65 else 0.79
            candidate_signal = (
                f"Over {next_goal_line} Match Goals",
                f"Second-half attacking tempo at min {minute}' with tight score ({home_score}-{away_score}).",
                confidence,
                "LOW" if total_goals >= 2 else "MEDIUM",
                1.75
            )

        # --- Pattern 4: Late Deadlock Goal Push (Minutes 77 - 85) ---
        if not candidate_signal and 77 <= minute <= 85 and home_score == away_score and total_goals <= 2:
            next_line = total_goals + 0.5
            confidence = 0.80 if (total_corners >= 7 or total_box_shots >= 6) else 0.76
            candidate_signal = (
                f"Over {next_line} Match Goals",
                f"Late deadlock ({home_score}-{away_score}) at min {minute}' with open end-to-end space (Corners: {total_corners}).",
                confidence,
                "MEDIUM",
                2.10
            )

        # --- Pattern 5: First-Half Momentum Breakout (Minutes 22 - 36) ---
        if not candidate_signal and 22 <= minute <= 36 and total_goals == 0:
            if total_box_shots >= 3 or total_xg >= 0.6 or (last_10m_home_m > 30 or last_10m_away_m > 30):
                candidate_signal = (
                    "Over 0.5 First Half Goals",
                    f"First-half deadlock at min {minute}' with high box threat (xG: {total_xg:.2f}, Box Shots: {total_box_shots}).",
                    0.80,
                    "LOW",
                    1.65
                )

        # =========================================================================
        # 🎯 DECISION & SIZING EVALUATION
        # =========================================================================

        if not candidate_signal:
            return None

        market, reasoning, confidence, risk_rating, odds_est = candidate_signal

        # Autonomous Confidence Threshold Gate
        if confidence < self.min_confidence:
            return None

        # Calculate dynamic stake tailored to active bankroll and signal confidence
        stake = self.calculate_dynamic_stake(
            bankroll=bankroll,
            confidence_score=confidence,
            odds_estimate=odds_est
        )

        return BetSignal(
            match_id=match_id,
            home_team=home_team,
            away_team=away_team,
            league=league_name,
            target_market=market,
            reasoning=reasoning,
            current_minute=minute,
            current_score=f"{home_score} - {away_score}",
            confidence_score=round(confidence, 2),
            risk_rating=risk_rating,
            odds_estimate=odds_est,
            stake_amount=stake,
            home_xg=home_xg if home_xg > 0 else None,
            away_xg=away_xg if away_xg > 0 else None,
            dominant_side=dominant_side if dominant_side != "NEUTRAL" else None
        )
