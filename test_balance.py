"""
Script to test Stake login authentication and fetch user balance.
"""

import sys
import asyncio
from pathlib import Path

# Fix Windows console UTF-8 output
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import Config
from stake_browser import StakeBrowser


async def check_stake_balance():
    print("\n--- Connecting to Stake with Saved Session Cookie ---")
    browser = StakeBrowser(headless=False)
    await browser.start()
    
    try:
        url = f"{Config.STAKE_BASE_URL}/sports"
        print(f"Navigating to {url}...")
        await browser.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(6)

        # Look for balance or wallet elements
        # Stake balance can be in button[data-testid="wallet-button"], span[data-testid="balance"], etc.
        balance_texts = []

        elements = await browser.page.query_selector_all("button:has-text('Wallet'), [data-testid*='balance'], [data-testid*='wallet'], .balance, header")
        for el in elements:
            try:
                txt = await el.inner_text()
                if txt:
                    balance_texts.append(txt.strip())
            except Exception:
                pass

        # Also search whole page header text
        header = await browser.page.query_selector("header")
        if header:
            header_text = await header.inner_text()
            print(f"\n[Header Elements]:\n{header_text}\n")

        # Take screenshot for proof
        screenshot_path = BASE_DIR / "browser_data" / "account_balance_check.png"
        await browser.page.screenshot(path=str(screenshot_path))
        print(f"📸 Screenshot saved to: {screenshot_path}")

        # Check if login succeeded
        title = await browser.page.title()
        print(f"Page Title: {title}")

    except Exception as e:
        print(f"Error during balance check: {e}")
    finally:
        await asyncio.sleep(2)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(check_stake_balance())
