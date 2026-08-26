"""
SofaScore Live Statistics Engine.
Zero-cost, real-time client providing live match data, in-play xG,
shot breakdown (inside/outside the penalty box), big chances, and
minute-by-minute Attack Momentum graphs.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, BrowserContext, Page
from playwright_stealth import Stealth

logger = logging.getLogger("SofaScoreClient")


class SofaScoreClient:
    def __init__(self, headless: bool = True):
        self.headless = headless
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.stealth = Stealth()
        self.base_url = "https://api.sofascore.com/api/v1"
        self._lock = asyncio.Lock()

    async def start(self):
        """Initializes the background browser session for authenticated zero-token scraping."""
        if self.page and not self.page.is_closed():
            return
        
        self.playwright = await async_playwright().start()
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-infobars",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--window-size=1280,800"
        ]
        
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir="",  # in-memory context
            headless=self.headless,
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            args=args,
            ignore_default_args=["--enable-automation"]
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.stealth.apply_stealth_async(self.page)
        logger.info("SofaScore background engine started successfully.")

    async def _fetch_json(self, url: str, timeout: int = 15000) -> Optional[Dict[str, Any]]:
        """Safely navigates to a SofaScore endpoint and parses the JSON response."""
        async with self._lock:
            if not self.page or self.page.is_closed():
                await self.start()
            
            try:
                resp = await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                if resp and resp.status == 200:
                    body = await self.page.inner_text("body")
                    if body:
                        return json.loads(body)
                else:
                    status = resp.status if resp else "None"
                    logger.warning(f"SofaScore returned status {status} for {url}")
                    return None
            except Exception as e:
                logger.error(f"Error fetching SofaScore URL {url}: {e}")
                return None

    async def get_live_matches(self) -> List[Dict[str, Any]]:
        """
        Fetches all football matches currently live worldwide.
        Returns a structured list of match summaries with IDs, teams, scores, and minutes.
        """
        data = await self._fetch_json(f"{self.base_url}/sport/football/events/live")
        if not data:
            return []

        raw_events = data.get("events", [])
        matches = []

        for ev in raw_events:
            try:
                tournament = ev.get("tournament", {}).get("name", "Unknown League")
                category = ev.get("tournament", {}).get("category", {}).get("name", "")
                league_name = f"{category}: {tournament}" if category else tournament

                home_team = ev.get("homeTeam", {}).get("name", "Home")
                away_team = ev.get("awayTeam", {}).get("name", "Away")
                
                status_info = ev.get("status", {})
                status_desc = status_info.get("description", "In Progress")
                
                # Determine current played minute
                time_info = ev.get("time", {})
                played_minute = time_info.get("played", 0)
                if not played_minute:
                    # Estimate from start timestamp if in-play
                    current_period_start = time_info.get("currentPeriodStartTimestamp")
                    if current_period_start:
                        now_ts = int(datetime.now(timezone.utc).timestamp())
                        elapsed = (now_ts - current_period_start) // 60
                        if status_desc.lower() in ("2nd half", "second half"):
                            played_minute = min(90, 45 + elapsed)
                        elif status_desc.lower() in ("1st half", "first half"):
                            played_minute = min(45, elapsed)
                        else:
                            played_minute = elapsed

                home_score = ev.get("homeScore", {}).get("current", 0)
                away_score = ev.get("awayScore", {}).get("current", 0)

                matches.append({
                    "id": ev.get("id"),
                    "home_team": home_team,
                    "away_team": away_team,
                    "league": league_name,
                    "minute": played_minute or 0,
                    "status": status_desc,
                    "home_score": home_score,
                    "away_score": away_score,
                    "start_time": ev.get("startTimestamp"),
                    "slug": ev.get("slug", "")
                })
            except Exception as e:
                logger.debug(f"Error parsing event item: {e}")
                continue

        return matches

    async def get_match_stats(self, event_id: int | str) -> Dict[str, Any]:
        """
        Fetches in-depth match statistics including xG, shots inside box,
        big chances, corners, fouls, and possession.
        """
        data = await self._fetch_json(f"{self.base_url}/event/{event_id}/statistics")
        if not data or "statistics" not in data:
            return {}

        all_stats = {}
        for period_data in data.get("statistics", []):
            period = period_data.get("period", "ALL")
            if period != "ALL":
                continue

            for group in period_data.get("groups", []):
                for item in group.get("statisticsItems", []):
                    name = item.get("name", "").strip().lower()
                    h_val = item.get("home", "0")
                    a_val = item.get("away", "0")

                    # Parse numbers safely (handling percentages or float strings)
                    def clean_val(v):
                        if isinstance(v, (int, float)):
                            return float(v)
                        s = str(v).replace("%", "").strip()
                        try:
                            return float(s)
                        except ValueError:
                            return 0.0

                    all_stats[name] = {
                        "home": clean_val(h_val),
                        "away": clean_val(a_val),
                        "home_raw": h_val,
                        "away_raw": a_val
                    }

        return {
            "home_xg": all_stats.get("expected goals", {}).get("home", 0.0),
            "away_xg": all_stats.get("expected goals", {}).get("away", 0.0),
            "home_xgot": all_stats.get("expected goals on target", {}).get("home", 0.0),
            "away_xgot": all_stats.get("expected goals on target", {}).get("away", 0.0),
            "home_total_shots": int(all_stats.get("total shots", {}).get("home", 0)),
            "away_total_shots": int(all_stats.get("total shots", {}).get("away", 0)),
            "home_shots_on_target": int(all_stats.get("shots on target", {}).get("home", 0)),
            "away_shots_on_target": int(all_stats.get("shots on target", {}).get("away", 0)),
            "home_shots_inside_box": int(all_stats.get("shots inside box", {}).get("home", 0)),
            "away_shots_inside_box": int(all_stats.get("shots inside box", {}).get("away", 0)),
            "home_shots_outside_box": int(all_stats.get("shots outside box", {}).get("home", 0)),
            "away_shots_outside_box": int(all_stats.get("shots outside box", {}).get("away", 0)),
            "home_big_chances": int(all_stats.get("big chances", {}).get("home", 0)),
            "away_big_chances": int(all_stats.get("big chances", {}).get("away", 0)),
            "home_big_chances_missed": int(all_stats.get("big chances missed", {}).get("home", 0)),
            "away_big_chances_missed": int(all_stats.get("big chances missed", {}).get("away", 0)),
            "home_corners": int(all_stats.get("corner kicks", {}).get("home", 0)),
            "away_corners": int(all_stats.get("corner kicks", {}).get("away", 0)),
            "home_possession": all_stats.get("ball possession", {}).get("home", 50.0),
            "away_possession": all_stats.get("ball possession", {}).get("away", 50.0),
            "home_fouls": int(all_stats.get("fouls", {}).get("home", 0)),
            "away_fouls": int(all_stats.get("fouls", {}).get("away", 0)),
            "home_yellow_cards": int(all_stats.get("yellow cards", {}).get("home", 0)),
            "away_yellow_cards": int(all_stats.get("yellow cards", {}).get("away", 0)),
            "home_red_cards": int(all_stats.get("red cards", {}).get("home", 0)),
            "away_red_cards": int(all_stats.get("red cards", {}).get("away", 0)),
            "home_goalkeeper_saves": int(all_stats.get("goalkeeper saves", {}).get("home", 0)),
            "away_goalkeeper_saves": int(all_stats.get("goalkeeper saves", {}).get("away", 0))
        }

    async def get_attack_momentum(self, event_id: int | str) -> Dict[str, Any]:
        """
        Fetches the Attack Momentum graph points (minute-by-minute pressure index).
        Positive values (> 0) indicate Home team dominance.
        Negative values (< 0) indicate Away team dominance.
        """
        data = await self._fetch_json(f"{self.base_url}/event/{event_id}/graph")
        if not data:
            return {"points": [], "last_10m_home_momentum": 0.0, "last_10m_away_momentum": 0.0, "dominant_side": "NEUTRAL"}

        points = data.get("graphPoints", [])
        if not points:
            return {"points": [], "last_10m_home_momentum": 0.0, "last_10m_away_momentum": 0.0, "dominant_side": "NEUTRAL"}

        # Analyze the last 10 minutes of play
        last_points = points[-10:] if len(points) >= 10 else points
        home_pressure = sum(max(0, p.get("value", 0)) for p in last_points) / max(1, len(last_points))
        away_pressure = sum(abs(min(0, p.get("value", 0))) for p in last_points) / max(1, len(last_points))

        dominant = "NEUTRAL"
        if home_pressure > away_pressure + 15:
            dominant = "HOME"
        elif away_pressure > home_pressure + 15:
            dominant = "AWAY"

        return {
            "points": points,
            "latest_minute": points[-1].get("minute", 0) if points else 0,
            "latest_value": points[-1].get("value", 0) if points else 0,
            "last_10m_home_momentum": round(home_pressure, 1),
            "last_10m_away_momentum": round(away_pressure, 1),
            "dominant_side": dominant
        }

    async def get_match_incidents(self, event_id: int | str) -> List[Dict[str, Any]]:
        """Fetches live incidents like goals, cards, and substitutions."""
        data = await self._fetch_json(f"{self.base_url}/event/{event_id}/incidents")
        if not data:
            return []
        return data.get("incidents", [])

    async def close(self):
        """Cleanly terminates the background browser session."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        self.page = None
        self.context = None
        self.playwright = None
        logger.info("SofaScore client closed.")
