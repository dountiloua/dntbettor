"""
Telegram Notification Engine for SofaScore-Stake Autonomous Agent.
Dispatches real-time alerts for bet signals, live/simulated executions,
outcomes, profit distributions, and circuit breaker trip events.
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any
import httpx
from config import Config
from strategy import BetSignal


class TelegramNotifier:
    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        enabled: Optional[bool] = None
    ):
        self.token = token if token is not None else Config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id if chat_id is not None else Config.TELEGRAM_CHAT_ID
        self.enabled = enabled if enabled is not None else Config.TELEGRAM_ENABLED
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    @property
    def is_configured(self) -> bool:
        """Returns True if Telegram credentials are set and enabled."""
        return bool(self.enabled and self.token and self.chat_id and self.token != "your_telegram_bot_token_here")

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Sends an HTML/Markdown formatted message to the configured Telegram chat."""
        if not self.is_configured:
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                else:
                    print(f"[Telegram] Error {resp.status_code}: {resp.text}")
                    return False
        except Exception as e:
            print(f"[Telegram] Failed to send message: {e}")
            return False

    async def get_updates(self, offset: int = 0) -> list[Dict[str, Any]]:
        """Reads new messages for the configured chat using Telegram polling."""
        if not self.is_configured:
            return []

        try:
            async with httpx.AsyncClient(timeout=35.0) as client:
                response = await client.get(
                    f"{self.base_url}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                if response.status_code == 200:
                    return response.json().get("result", [])
        except Exception as e:
            print(f"[Telegram] Failed to read messages: {e}")
        return []

    async def send_photo(self, photo_path: Path | str, caption: Optional[str] = None) -> bool:
        """Uploads and sends a photo (such as a bet slip screenshot) with an optional caption."""
        if not self.is_configured:
            return False

        path_obj = Path(photo_path)
        if not path_obj.exists():
            return False

        url = f"{self.base_url}/sendPhoto"
        data = {"chat_id": self.chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = "HTML"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                with open(path_obj, "rb") as f:
                    files = {"photo": (path_obj.name, f, "image/png")}
                    resp = await client.post(url, data=data, files=files)
                    return resp.status_code == 200
        except Exception as e:
            print(f"[Telegram] Failed to send photo: {e}")
            return False

    async def notify_startup(self, bankroll: float, simulation_mode: bool, dynamic_sizing: bool):
        """Sends a notification when the bot starts monitoring."""
        mode_badge = "🧪 <b>SIMULATION (Paper Trading)</b>" if simulation_mode else "⚡ <b>LIVE BETTING (Real Money)</b>"
        sizing_badge = "Active (Dynamic Sizing)" if dynamic_sizing else "Fixed Sizing"
        
        msg = (
            "🤖 <b>Autonomous Betting Agent Started</b>\n\n"
            f"<b>Mode:</b> {mode_badge}\n"
            f"<b>Data Engine:</b> <b>SofaScore Live (Zero API Cost)</b>\n"
            f"<b>Dynamic Sizing:</b> {sizing_badge}\n"
            f"<b>Active Bankroll:</b> ${bankroll:.2f}\n"
            f"<b>Base Risk:</b> {Config.BASE_BANKROLL_PERCENT * 100:.1f}%\n"
            f"<b>Min Confidence:</b> {Config.MIN_CONFIDENCE_THRESHOLD * 100:.0f}%\n"
            f"<b>Poll Interval:</b> {Config.POLL_INTERVAL_SECONDS}s\n\n"
            "<i>Agent is actively scanning live matches worldwide...</i>"
        )
        await self.send_message(msg)

    async def notify_bet_placed(
        self,
        signal: BetSignal,
        is_simulation: bool = True,
        screenshot_path: Optional[Path] = None
    ):
        """Sends an alert when a bet is executed or simulated."""
        badge = "🧪 [SIMULATION BET]" if is_simulation else "⚡ [LIVE BET PLACED]"
        
        xg_text = ""
        if signal.home_xg is not None and signal.away_xg is not None:
            xg_text = f"🎯 <b>Live xG:</b> {signal.home_xg:.2f} - {signal.away_xg:.2f}\n"
        
        pressure_text = ""
        if signal.dominant_side:
            pressure_text = f"🔥 <b>Momentum:</b> {signal.dominant_side} Dominating\n"

        # Detect AI-generated signals by reasoning prefix and format separately
        reasoning = signal.reasoning or ""
        if reasoning.startswith("[🤖 Gemini AI]"):
            ai_reasoning = reasoning.replace("[🤖 Gemini AI]", "").strip()
            ai_block = f"\n🤖 <b>Gemini AI Reasoning:</b>\n<i>{ai_reasoning}</i>\n"
        else:
            ai_block = f"💡 <b>Reason:</b> {reasoning}\n"

        caption = (
            f"🎯 <b>{badge}</b>\n\n"
            f"⚽ <b>Match:</b> {signal.home_team} vs {signal.away_team}\n"
            f"🏆 <b>League:</b> {signal.league}\n"
            f"⏱️ <b>Time & Score:</b> Min {signal.current_minute}' ({signal.current_score})\n"
            f"{xg_text}"
            f"{pressure_text}"
            f"📊 <b>Market:</b> <code>{signal.target_market}</code>\n"
            f"💵 <b>Dynamic Stake:</b> <b>${signal.stake_amount:.2f}</b>\n"
            f"🧠 <b>Conviction:</b> {signal.confidence_score * 100:.0f}% ({signal.risk_rating} Risk)\n"
            f"{ai_block}"
        )

        if screenshot_path and Path(screenshot_path).exists():
            await self.send_photo(screenshot_path, caption=caption)
        else:
            await self.send_message(caption)

    async def notify_bet_outcome(
        self,
        match_name: str,
        market: str,
        outcome: str,
        profit_loss: float,
        new_bankroll: float,
        wage_pool: float
    ):
        """Sends an alert when a bet concludes and profits are distributed."""
        is_win = outcome.upper() == "WON"
        icon = "🎉" if is_win else "📉"
        pnl_formatted = f"+${profit_loss:.2f}" if profit_loss >= 0 else f"-${abs(profit_loss):.2f}"

        msg = (
            f"{icon} <b>BET SETTLED: {outcome.upper()}</b>\n\n"
            f"⚽ <b>Match:</b> {match_name}\n"
            f"📊 <b>Market:</b> {market}\n"
            f"💰 <b>Net PnL:</b> <b>{pnl_formatted}</b>\n"
            f"🏦 <b>Updated Bankroll:</b> ${new_bankroll:.2f}\n"
            f"💼 <b>User Wage Pool:</b> ${wage_pool:.2f} (Available)\n"
        )
        await self.send_message(msg)

    async def notify_circuit_breaker(self, current_bankroll: float, drawdown_pct: float):
        """Sends a high-priority circuit breaker alert."""
        msg = (
            "🚨 <b>CIRCUIT BREAKER TRIGGERED!</b> 🚨\n\n"
            f"Current Bankroll has dropped to <b>${current_bankroll:.2f}</b> "
            f"(Drawdown: <b>{drawdown_pct:.1f}%</b>).\n\n"
            "⚠️ <i>Live betting is automatically HALTED to protect capital.</i>\n"
            "Please review the ledger using: <code>python bot.py --financials</code>"
        )
        await self.send_message(msg)

    async def notify_financial_summary(self, status: Dict[str, Any]):
        """Sends the financial ledger summary report."""
        msg = (
            "📊 <b>BOT FINANCIAL HEALTH REPORT</b>\n\n"
            f"💰 <b>Active Bankroll:</b> ${status['current_bankroll']:.2f}\n"
            f"💼 <b>User Wage Pool:</b> ${status['user_wage_pool']:.2f}\n"
            f"💵 <b>Bills Reserve:</b> ${status['bills_reserve_pool']:.2f}\n"
            f"🛡️ <b>Emergency Buffer:</b> ${status['emergency_pool']:.2f}\n"
            "------------------------------------\n"
            f"📈 <b>Total Net Profit:</b> ${status['total_profit_generated']:.2f}\n"
            f"🧾 <b>Total Bills Paid:</b> ${status['total_bills_paid']:.2f}\n"
            f"⏳ <b>Bills Coverage:</b> {status['bills_coverage_months']} months\n"
            f"🚨 <b>Circuit Breaker:</b> {'TRIPPED' if status['circuit_breaker_tripped'] else 'HEALTHY'}\n"
        )
        await self.send_message(msg)

    async def test_connection(self) -> Dict[str, Any]:
        """Tests the Telegram Bot connection and returns bot identity."""
        if not self.token:
            return {"success": False, "error": "TELEGRAM_BOT_TOKEN is not set in .env"}

        url = f"{self.base_url}/getMe"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    bot_user = data.get("result", {})
                    # Also try to send test message if chat_id is present
                    sent_msg = False
                    if self.chat_id:
                        sent_msg = await self.send_message("✅ <b>Autonomous Betting Bot Telegram Integration Verified!</b>")
                    return {
                        "success": True,
                        "bot_username": bot_user.get("username"),
                        "bot_first_name": bot_user.get("first_name"),
                        "test_message_sent": sent_msg
                    }
                else:
                    return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
