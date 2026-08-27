"""
Configuration module for the Autonomous SofaScore-Stake Betting Bot.
Loads settings from .env with validation and hard safety bounds.
Includes Gemini AI Agent configuration for Full Agent Mode.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    BASE_DIR: Path = BASE_DIR
    
    # --- Stake Configuration ---
    STAKE_BASE_URL: str = os.getenv("STAKE_BASE_URL", "https://stake.com")
    STAKE_USER_DATA_DIR: Path = BASE_DIR / "browser_data" / "stake_profile"
    BROWSER_CHANNEL: str = os.getenv("BROWSER_CHANNEL", "")  # '' for clean isolated Chromium, or 'msedge'/'chrome'
    STAKE_SESSION_COOKIE: str = os.getenv("STAKE_SESSION_COOKIE", "")  # Direct session cookie bypass
    STAKE_2FA_SECRET: str = os.getenv("STAKE_2FA_SECRET", "")  # Google Authenticator TOTP Secret Key

    # --- Telegram Notifications Configuration ---
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")
    TELEGRAM_ENABLED: bool = os.getenv("TELEGRAM_ENABLED", "true").lower() in ("true", "1", "yes")

    # --- User Payout Wallet Configuration ---
    PAYOUT_WALLET_ADDRESS: str = os.getenv("PAYOUT_WALLET_ADDRESS", "")
    PAYOUT_CURRENCY: str = os.getenv("PAYOUT_CURRENCY", "USDT_BSC")  # USDT on BNB Smart Chain (BEP20, starts with 0x)
    PAYOUT_MIN_THRESHOLD: float = float(os.getenv("PAYOUT_MIN_THRESHOLD", "25.00"))

    # --- Betting Parameters & Risk Management ---
    # When True, the bot will navigate and prepare the bet slip without clicking the final submit
    SIMULATION_MODE: bool = os.getenv("SIMULATION_MODE", "true").lower() in ("true", "1", "yes")
    
    # Enable autonomous dynamic bet sizing (Kelly / bankroll-scaled) vs fixed bet
    ENABLE_DYNAMIC_SIZING: bool = os.getenv("ENABLE_DYNAMIC_SIZING", "true").lower() in ("true", "1", "yes")
    
    # Base risk percentage of active bankroll per wager (e.g. 0.02 = 2.0%)
    BASE_BANKROLL_PERCENT: float = float(os.getenv("BASE_BANKROLL_PERCENT", "0.02"))
    
    # Minimum stake per wager in currency units
    MIN_STAKE: float = float(os.getenv("MIN_STAKE", "0.50"))
    
    # Default / fallback fixed bet amount per wager
    BET_AMOUNT: float = float(os.getenv("BET_AMOUNT", "1.00"))
    
    # HARD CEILING: Maximum bet allowed under any circumstances
    MAX_BET_CAP: float = float(os.getenv("MAX_BET_CAP", "10.00"))
    
    # Minimum confidence score (0.0 to 1.0) required to place a bet (e.g. 0.75 = 75%)
    MIN_CONFIDENCE_THRESHOLD: float = float(os.getenv("MIN_CONFIDENCE_THRESHOLD", "0.75"))
    
    # Minimum and maximum decimal odds allowed
    MIN_ODDS: float = float(os.getenv("MIN_ODDS", "1.40"))
    MAX_ODDS: float = float(os.getenv("MAX_ODDS", "4.50"))
    
    # Daily stop-loss (maximum allowed total losses in a day before pausing)
    DAILY_STOP_LOSS: float = float(os.getenv("DAILY_STOP_LOSS", "50.00"))

    # Bet Volume Controls (Min 0, Max 25 per week / Max 4 per day)
    MAX_DAILY_BETS: int = int(os.getenv("MAX_DAILY_BETS", "4"))
    MAX_WEEKLY_BETS: int = int(os.getenv("MAX_WEEKLY_BETS", "25"))

    # League Whitelist Filter (Comma-separated keywords)
    # Defaults to the competitions approved for betting.
    ALLOWED_LEAGUES: str = os.getenv(
        "ALLOWED_LEAGUES",
        "La Liga, Serie A, Premier League, Champions League",
    )

    # --- Gemini AI Agent Configuration ---
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    # Model to use: "gemini-2.5-flash" (fast/cheap) or "gemini-1.5-pro" (smarter)
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # AI integration mode: "agent" (Gemini replaces rules) or "hybrid" (rules + AI validation)
    GEMINI_AI_MODE: str = os.getenv("GEMINI_AI_MODE", "agent")

    # --- Polling & Interval Settings ---
    POLL_INTERVAL_SECONDS: int = int(os.getenv("POLL_INTERVAL_SECONDS", "15"))

    @classmethod
    def validate(cls):
        if cls.BET_AMOUNT > cls.MAX_BET_CAP:
            raise ValueError(f"BET_AMOUNT ({cls.BET_AMOUNT}) exceeds safety MAX_BET_CAP ({cls.MAX_BET_CAP}).")
        cls.STAKE_USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
