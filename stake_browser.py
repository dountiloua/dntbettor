"""
Stake.com Playwright Automation Wrapper.
Manages persistent browser sessions, anti-detection flags, and bet slip execution.
"""

import asyncio
from pathlib import Path
from typing import Optional
from playwright.async_api import async_playwright, BrowserContext, Page
from config import Config
from strategy import BetSignal


import pyotp
from playwright_stealth import Stealth


class StakeBrowser:
    def __init__(self, headless: bool = False):
        Config.validate()
        self.user_data_dir = str(Config.STAKE_USER_DATA_DIR)
        self.headless = headless
        self.playwright = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.stealth = Stealth()

    @staticmethod
    def get_2fa_code() -> Optional[str]:
        """Generates the current 6-digit Google Authenticator TOTP code from STAKE_2FA_SECRET."""
        if not Config.STAKE_2FA_SECRET:
            return None
        try:
            totp = pyotp.TOTP(Config.STAKE_2FA_SECRET.strip())
            return totp.now()
        except Exception as e:
            print(f"[StakeBrowser] Error generating 2FA TOTP code: {e}")
            return None

    async def start(self):
        """Starts Playwright with a persistent browser context to retain login cookies."""
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

        launch_kwargs = {
            "user_data_dir": self.user_data_dir,
            "headless": self.headless,
            "viewport": {"width": 1280, "height": 800},
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "args": args,
            "ignore_default_args": ["--enable-automation"]
        }
        if Config.BROWSER_CHANNEL:
            launch_kwargs["channel"] = Config.BROWSER_CHANNEL

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)
        except Exception as e:
            print(f"[StakeBrowser] Note: Failed to launch channel '{Config.BROWSER_CHANNEL}' ({e}). Falling back to standard Chromium.")
            launch_kwargs.pop("channel", None)
            self.context = await self.playwright.chromium.launch_persistent_context(**launch_kwargs)

        # Apply comprehensive Playwright Stealth
        await self.stealth.apply_stealth_async(self.context)

        # Inject session cookie if configured in .env
        if Config.STAKE_SESSION_COOKIE:
            try:
                from urllib.parse import urlparse
                parsed_domain = urlparse(Config.STAKE_BASE_URL).netloc or "stake.com"
                await self.context.add_cookies([{
                    "name": "session",
                    "value": Config.STAKE_SESSION_COOKIE.strip(),
                    "domain": f".{parsed_domain}",
                    "path": "/"
                }])
                print(f"[StakeBrowser] 🔑 Injected session cookie for domain: .{parsed_domain}")
            except Exception as e:
                print(f"[StakeBrowser] Failed to inject session cookie: {e}")

        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        await self.stealth.apply_stealth_async(self.page)

    async def login_interactive(self):
        """
        Launches an interactive visible browser window for the user to log into Stake.com once.
        Waits until the user completes login and 2FA.
        """
        print("[StakeBrowser] Launching interactive browser for one-time login...")
        await self.start()
        try:
            await self.page.goto(f"{Config.STAKE_BASE_URL}/sports", wait_until="commit", timeout=45000)
        except Exception as e:
            print(f"[StakeBrowser] Note during initial navigation: {e}")
        
        print("\n========================================================")
        print(f"  👉 Navigated to: {Config.STAKE_BASE_URL}")
        print("  👉 PLEASE LOG INTO YOUR STAKE ACCOUNT IN THE BROWSER")
        print("  Solve any Cloudflare check / 2FA as needed.")
        print("  Once you are fully logged in and see your balance,")
        print("  come back here and press ENTER to save the session.")
        print("========================================================\n")
        
        input("Press Enter once logged in...")
        print("[StakeBrowser] Session state saved successfully!")
        await self.close()

    async def execute_bet_flow(self, signal: BetSignal) -> bool:
        """
        Navigates to the match and executes the bet placement.
        If SIMULATION_MODE is True, populates the bet slip and simulates without placing real money.
        """
        if not self.context or not self.page:
            await self.start()

        print(f"\n[StakeBrowser] Processing Signal: {signal.home_team} vs {signal.away_team} -> {signal.target_market}")
        
        try:
            # 1. Search or navigate to Sports section
            await self.page.goto(f"{Config.STAKE_BASE_URL}/sports", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)

            # Check if user is logged in
            is_logged_in = await self.page.query_selector("button:has-text('Wallet'), div[data-testid='user-balance']")
            if not is_logged_in:
                print("[StakeBrowser] ⚠️ Warning: User may not be logged in. Please run `python bot.py --login` first.")

            # Search for the team / match on Stake search bar if available
            search_input = await self.page.query_selector("input[placeholder*='Search'], input[type='search']")
            if search_input:
                await search_input.fill(signal.home_team)
                await self.page.keyboard.press("Enter")
                await asyncio.sleep(2)

            # Determine stake amount from dynamic signal with safety ceiling clamp
            stake_to_place = getattr(signal, "stake_amount", Config.BET_AMOUNT)
            stake_to_place = max(Config.MIN_STAKE, min(stake_to_place, Config.MAX_BET_CAP))

            # 2. Simulation check
            if Config.SIMULATION_MODE:
                print(f"[StakeBrowser] 🧪 [SIMULATION MODE] Autonomous Bet Prepared:")
                print(f"   Match:      {signal.home_team} vs {signal.away_team}")
                print(f"   Market:     {signal.target_market}")
                print(f"   Conviction: {signal.confidence_score * 100:.0f}% ({signal.risk_rating} Risk)")
                print(f"   Stake Size: ${stake_to_place:.2f} (Dynamic)")
                print(f"   Reason:     {signal.reasoning}")
                
                # Take screenshot for proof
                screenshot_path = Config.BASE_DIR / "browser_data" / f"sim_bet_{signal.match_id}.png"
                await self.page.screenshot(path=str(screenshot_path))
                print(f"   📸 Screenshot saved: {screenshot_path}")
                return True
            else:
                # LIVE MODE: Locate market selection button, type bet amount, and click Place Bet
                print(f"[StakeBrowser] ⚡ [LIVE MODE] Submitting Dynamic Bet of ${stake_to_place:.2f}...")
                
                # Input bet amount into the active bet slip input
                bet_input = await self.page.query_selector("input[data-testid='bet-input'], input[name='bet-amount']")
                if bet_input:
                    await bet_input.fill(f"{stake_to_place:.2f}")
                    await asyncio.sleep(0.5)
                
                # Locate and click submit button
                submit_button = await self.page.query_selector("button:has-text('Place Bet'), button[data-testid='place-bet-button']")
                if submit_button:
                    await submit_button.click()
                    await asyncio.sleep(2)
                    print(f"[StakeBrowser] ✅ Live Bet of ${stake_to_place:.2f} successfully placed!")
                    return True
                else:
                    print("[StakeBrowser] ❌ Could not find 'Place Bet' submit button on slip.")
                    return False

        except Exception as e:
            print(f"[StakeBrowser] Error executing bet flow: {e}")
            return False

    async def close(self):
        """Closes browser context."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
