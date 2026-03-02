import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        errors = []
        page.on("console", lambda msg: errors.append(f"CONSOLE {msg.type}: {msg.text}") if msg.type in ['error', 'warning'] else None)
        page.on("pageerror", lambda err: errors.append(f"PAGE ERROR: {err}"))
        
        print("Navigating to dashboard...")
        await page.goto("http://localhost:8000/")
        await page.wait_for_load_state("networkidle")
        
        print("Opening wizard...")
        await page.evaluate("openWizardModal()")
        await page.wait_for_timeout(1000)
        
        print("Clicking Submit...")
        await page.evaluate("wizardSubmit()")
        await page.wait_for_timeout(2000)
        
        print("\n--- BROWSER ERRORS ---")
        for e in errors:
            print(e)
            
        # Get UI Status Message
        msg = await page.evaluate("document.getElementById('wiz-status-msg').innerText")
        print("\nUI Status Msg:", msg)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
