"""
Gemini AI Agent for Autonomous Betting Decision-Making.

Replaces the static rule-based StrategyEngine with a live Google Gemini
model that receives full match context (xG, momentum, scoreline, minute,
stats) and autonomously decides:
  1. Whether to bet (BET / NO_BET).
  2. Which market offers mathematical value.
  3. Its confidence level and risk rating.
  4. A clear, natural-language reasoning for the decision.

The agent is given the full quantitative betting strategy as its system
prompt so it operates within the established risk framework.
"""

import json
import asyncio
import logging
from typing import Optional, Dict, Any
from config import Config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# System Prompt — embedded betting strategy & risk framework
# ──────────────────────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are an elite autonomous sports-betting AI agent specialising in live
in-play football (soccer) on Stake.com.

Your job is to analyse a real-time live match data packet and decide
whether a high-conviction bet exists. You must follow the strict
quantitative framework below. Never deviate from it.

═══════════════════════════════════════════════════════════════
CORE PHILOSOPHY
═══════════════════════════════════════════════════════════════
1. Patience Over Volume — reject ~95% of matches. Only bet when mathematical
   conviction is genuinely high (≥ 75%).
2. Dynamic Kelly-Scaled Sizing — let the caller handle stake sizing.
   Focus only on the quality of the decision.
3. Strict Disqualification Filters — NEVER chase blowouts, early chaos,
   or high red-card matches.
4. Capital Protection — volume caps and circuit breaker are enforced
   externally. Your job is signal quality only.

═══════════════════════════════════════════════════════════════
DISQUALIFICATION GATES — return NO_BET for ANY of these
═══════════════════════════════════════════════════════════════
• Gate 1 (Time): Match minute < 15 or > 86
• Gate 2 (Blowout): |home_score - away_score| >= 3 AND minute >= 60
• Gate 3 (Chaos): total red cards >= 2
• Gate 4 (League): If league not in allowed leagues (Premier League,
  Champions League, LaLiga, Serie A, Bundesliga, MLS) — NO_BET.
  If league data is missing, use your judgement.

═══════════════════════════════════════════════════════════════
HIGH-CONVICTION PATTERNS — only bet when a pattern fires
═══════════════════════════════════════════════════════════════

Pattern 1: xG Surge & Box Pressure Over (55'–78')
• Conditions: total_goals ≤ 3, |score_diff| ≤ 1,
  AND (total_xG ≥ 1.4 OR total_box_shots ≥ 7 OR 10m_momentum > 30)
• Market: "Over {total_goals + 0.5} Match Goals"
• Confidence: 82%–88%

Pattern 2: Trailing Dominant Team Push (50'–75')
• Conditions: home=0, away=1 (or home=1, away=2)
  AND (home_xG ≥ 0.8 OR 10m_home_momentum ≥ 25 OR home_box_shots ≥ 4)
• Market: "{trailing_team} or Draw (Double Chance)"
• Confidence: 83%

Pattern 3: Second-Half Goal Pressure (58'–76')
• Conditions: total_goals in [1,2,3], |score_diff| ≤ 1
• Market: "Over {total_goals + 0.5} Match Goals"
• Confidence: 79%–84%

Pattern 4: Late Deadlock Push (77'–85')
• Conditions: home_score == away_score, total_goals ≤ 2
  AND (total_corners ≥ 7 OR total_box_shots ≥ 6)
• Market: "Over {total_goals + 0.5} Match Goals"
• Confidence: 76%–80%

Pattern 5: First-Half Momentum Breakout (22'–36')
• Conditions: total_goals == 0
  AND (total_box_shots ≥ 3 OR total_xG ≥ 0.6 OR 10m_momentum > 30)
• Market: "Over 0.5 First Half Goals"
• Confidence: 80%

═══════════════════════════════════════════════════════════════
ODDS CONSTRAINTS
═══════════════════════════════════════════════════════════════
• Minimum odds: 1.40  |  Maximum odds: 4.50
• Prefer markets with estimated odds in the 1.65 – 2.20 range.

═══════════════════════════════════════════════════════════════
RESPONSE FORMAT (strict JSON only — no markdown, no prose)
═══════════════════════════════════════════════════════════════
{
  "decision": "BET" | "NO_BET",
  "market": "<string — the exact bet market, e.g. Over 2.5 Match Goals>",
  "confidence": <float 0.0–1.0>,
  "risk_rating": "LOW" | "MEDIUM" | "HIGH",
  "odds_estimate": <float>,
  "reasoning": "<concise 1–3 sentence explanation of why you are betting or not betting>"
}

If decision is "NO_BET", set market to "" and odds_estimate to 0.0.
Output ONLY the JSON object. No other text.
""".strip()


class GeminiAgent:
    """
    Wraps the Google Gemini API to act as a live betting decision agent.
    Replaces the static StrategyEngine in Full Agent Mode.
    """

    def __init__(self):
        self.api_key: str = Config.GEMINI_API_KEY
        self.model: str = Config.GEMINI_MODEL
        self._client = None
        self._last_response_valid = False
        self._enabled: bool = bool(self.api_key and self.api_key != "your_gemini_api_key_here")

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_client(self):
        """Lazily initialise the Gemini client (avoids import-time errors)."""
        if self._client is None:
            try:
                from google import genai
                from google.genai import types
                self._client = genai.Client(api_key=self.api_key)
                self._types = types
            except ImportError:
                raise RuntimeError(
                    "google-genai package is not installed. "
                    "Run: pip install google-genai"
                )
        return self._client

    def _build_match_prompt(
        self,
        match: Dict[str, Any],
        stats: Optional[Dict[str, Any]],
        momentum: Optional[Dict[str, Any]],
    ) -> str:
        """Serialise the live match data packet into a structured prompt."""
        # Normalise match fields (support both flat and nested SofaScore payloads)
        home_team = match.get("home_team", match.get("home", {}).get("name", "Home"))
        away_team = match.get("away_team", match.get("away", {}).get("name", "Away"))
        home_score = match.get("home_score", match.get("home", {}).get("score", 0))
        away_score = match.get("away_score", match.get("away", {}).get("score", 0))
        league = match.get("league", match.get("leagueName", "Unknown"))
        minute = match.get("minute", 0)

        # Stats
        home_xg = stats.get("home_xg", 0.0) if stats else 0.0
        away_xg = stats.get("away_xg", 0.0) if stats else 0.0
        home_box_shots = stats.get("home_shots_inside_box", 0) if stats else 0
        away_box_shots = stats.get("away_shots_inside_box", 0) if stats else 0
        home_corners = stats.get("home_corners", 0) if stats else 0
        away_corners = stats.get("away_corners", 0) if stats else 0
        home_red = stats.get("home_red_cards", 0) if stats else 0
        away_red = stats.get("away_red_cards", 0) if stats else 0
        home_yellow = stats.get("home_yellow_cards", 0) if stats else 0
        away_yellow = stats.get("away_yellow_cards", 0) if stats else 0

        # Momentum
        home_momentum_10m = momentum.get("last_10m_home_momentum", 0.0) if momentum else 0.0
        away_momentum_10m = momentum.get("last_10m_away_momentum", 0.0) if momentum else 0.0
        dominant_side = momentum.get("dominant_side", "NEUTRAL") if momentum else "NEUTRAL"

        data = {
            "match": {
                "home_team": home_team,
                "away_team": away_team,
                "league": league,
                "minute": minute,
                "home_score": home_score,
                "away_score": away_score,
                "total_goals": home_score + away_score,
                "score_difference": abs(home_score - away_score),
            },
            "statistics": {
                "home_xg": round(home_xg, 2),
                "away_xg": round(away_xg, 2),
                "total_xg": round(home_xg + away_xg, 2),
                "home_shots_inside_box": home_box_shots,
                "away_shots_inside_box": away_box_shots,
                "total_box_shots": home_box_shots + away_box_shots,
                "home_corners": home_corners,
                "away_corners": away_corners,
                "total_corners": home_corners + away_corners,
                "home_red_cards": home_red,
                "away_red_cards": away_red,
                "total_red_cards": home_red + away_red,
                "home_yellow_cards": home_yellow,
                "away_yellow_cards": away_yellow,
            },
            "momentum": {
                "home_10m_momentum": round(home_momentum_10m, 1),
                "away_10m_momentum": round(away_momentum_10m, 1),
                "dominant_side": dominant_side,
            },
        }
        return json.dumps(data, indent=2)

    def _parse_response(self, raw: str) -> Optional[Dict[str, Any]]:
        """Parse and validate Gemini's JSON response."""
        try:
            # Strip any markdown code fences if model adds them
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean
            result = json.loads(clean)

            # Validate required fields
            if result.get("decision") not in ("BET", "NO_BET"):
                logger.warning(f"[GeminiAgent] Unexpected decision value: {result.get('decision')}")
                return None

            return result
        except (json.JSONDecodeError, AttributeError) as e:
            logger.error(f"[GeminiAgent] Failed to parse response: {e}\nRaw: {raw[:300]}")
            return None

    async def evaluate_match(
        self,
        match: Dict[str, Any],
        stats: Optional[Dict[str, Any]] = None,
        momentum: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Main entry-point. Sends a live match context to Gemini and returns
        a structured betting decision, or None if the AI passes / errors.

        Returns dict with keys:
          decision, market, confidence, risk_rating, odds_estimate, reasoning
        or None if NO_BET or error.
        """
        if not self._enabled:
            logger.warning("[GeminiAgent] Gemini API key not configured. Skipping AI evaluation.")
            return None

        self._last_response_valid = False
        prompt = self._build_match_prompt(match, stats, momentum)

        try:
            client = self._get_client()

            # Run synchronous Gemini call in executor to keep bot's async loop clean
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=self._types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.2,
                        top_p=0.85,
                        max_output_tokens=2048,
                        response_mime_type="application/json",
                    )
                )
            )

            raw_text = response.text
            result = self._parse_response(raw_text)

            if result is None:
                return None

            self._last_response_valid = True

            if result["decision"] == "NO_BET":
                home = match.get("home_team", match.get("home", {}).get("name", "?"))
                away = match.get("away_team", match.get("away", {}).get("name", "?"))
                logger.debug(
                    f"[GeminiAgent] NO_BET for {home} vs {away}: {result.get('reasoning', '')}"
                )
                return None

            # Clamp confidence to valid range
            result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))

            return result

        except Exception as e:
            logger.error(f"[GeminiAgent] API call failed: {e}")
            return None

    async def test_connection(self) -> Dict[str, Any]:
        """
        Sends a minimal test prompt to Gemini to verify connectivity.
        Returns a result dict with 'success', 'model', and optionally 'error'.
        """
        if not self._enabled:
            return {"success": False, "error": "GEMINI_API_KEY is not configured in .env"}

        test_match = {
            "home_team": "Manchester City", "away_team": "Arsenal",
            "league": "Premier League", "minute": 67,
            "home_score": 1, "away_score": 1,
        }
        test_stats = {
            "home_xg": 1.6, "away_xg": 0.9,
            "home_shots_inside_box": 8, "away_shots_inside_box": 4,
            "home_corners": 5, "away_corners": 2,
            "home_red_cards": 0, "away_red_cards": 0,
            "home_yellow_cards": 1, "away_yellow_cards": 2,
        }
        test_momentum = {
            "last_10m_home_momentum": 38.0, "last_10m_away_momentum": 14.0,
            "dominant_side": "HOME",
        }

        try:
            result = await self.evaluate_match(test_match, test_stats, test_momentum)
            return {
                "success": self._last_response_valid,
                "model": self.model,
                "sample_decision": result if result else {"decision": "NO_BET"},
                **({} if self._last_response_valid else {"error": "Gemini returned invalid or truncated JSON"}),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def answer_question(self, question: str) -> Optional[str]:
        """Answers a user question using the same configured Gemini agent."""
        if not self._enabled:
            return None

        try:
            client = self._get_client()
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: client.models.generate_content(
                    model=self.model,
                    contents=question,
                    config=self._types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        temperature=0.2,
                        max_output_tokens=512,
                    )
                )
            )
            return response.text.strip() if response.text else None
        except Exception as e:
            logger.error(f"[GeminiAgent] Question failed: {e}")
            return None
