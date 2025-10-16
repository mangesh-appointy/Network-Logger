"""Simple test to check if Playwright browser can stay open"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    print("Starting Playwright...")
    playwright = await async_playwright().start()

    print("Launching Firefox browser...")
    browser = await playwright.firefox.launch(headless=False)

    print("Creating page...")
    page = await browser.new_page()

    print("Browser opened! Press Ctrl+C to close...")

    try:
        # Keep alive
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nClosing browser...")

    await browser.close()
    await playwright.stop()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
