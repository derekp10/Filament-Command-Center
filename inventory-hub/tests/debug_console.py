from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        # Log console errors
        page.on("console", lambda msg: print(f"Browser Log: {msg.text}") if msg.type in ['error', 'warning', 'log'] else None)
        page.on("pageerror", lambda err: print(f"Browser Error: {err}"))
        
        try:
            page.goto("http://localhost:8000")
            page.get_by_role("button", name="📦 ADD INVENTORY").click()
            page.wait_for_timeout(500)
            
            page.locator("#btn-type-manual").click()
            page.fill("#wiz-fil-material", "Pytest-PLA")
            page.fill("#wiz-fil-color_name", "E2E Ruby Red")
            page.locator("#wiz-fil-color_hex_0").fill("#FF0044")
            page.fill("#wiz-fil-density", "1.24")
            page.fill("#wiz-fil-diameter", "1.75")
            page.locator("#wiz-fil-weight").fill("1000")
            page.fill("#wiz-fil-empty_weight", "250")
            
            page.locator("#btn-wiz-submit").click()
            page.wait_for_timeout(2000)
        except Exception as e:
            print(f"Exception triggered: {e}")
            
        browser.close()

if __name__ == "__main__":
    run()
