"""
Inspect all balances in Stake wallet dropdown.
"""

import sys
import asyncio
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import Config
from stake_browser import StakeBrowser


async def inspect_wallet():
    browser = StakeBrowser(headless=False)
    await browser.start()
    try:
        await browser.page.goto(f"{Config.STAKE_BASE_URL}/sports", wait_until="domcontentloaded", timeout=45000)
        await asyncio.sleep(5)

        # Click on the balance dropdown button
        dropdown_btn = await browser.page.query_selector("button:has([data-testid='balance']), button:has-text('0.00'), button:has-text('Wallet')")
        if dropdown_btn:
            await dropdown_btn.click()
            await asyncio.sleep(2)
            
            # Screenshot of dropdown
            dropdown_path = BASE_DIR / "browser_data" / "wallet_dropdown.png"
            await browser.page.screenshot(path=str(dropdown_path))
            print(f"Dropdown screenshot saved: {dropdown_path}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await asyncio.sleep(2)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(inspect_wallet())
