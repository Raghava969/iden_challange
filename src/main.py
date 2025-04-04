import asyncio
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

SESSION_FILE = "session.json"
OUTPUT_FILE = "product_data.json"
LOGIN_URL = "https://hiring.idenhq.com/"


async def save_session(context, page):
    """Saves browser session (cookies + local storage)."""
    try:
        storage_state = await context.storage_state()
        session_storage = await page.evaluate("JSON.stringify(sessionStorage)")
        session_data = {
            "session_storage": session_storage,
            "storage_state": storage_state
        }
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            json.dump(session_data, f, indent=4)
        print("✅ Session saved successfully!")
    except Exception as e:
        print(f"❌ Error saving session: {e}")

async def load_session(context):
    """Loads session if available."""
    if not Path(SESSION_FILE).exists():
        print("🔹 No saved session found.")
        return

    try:
        print("🔹 Loading session...")
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_data = json.load(f)

        await context.add_cookies(session_data["storage_state"]["cookies"])

        session_storage = session_data["session_storage"]
        await context.add_init_script(f"""(storage => {{
            if (window.location.hostname === 'hiring.idenhq.com') {{
                const entries = JSON.parse(storage);
                for (const [key, value] of Object.entries(entries)) {{
                    window.sessionStorage.setItem(key, value);
                }}
            }}
        }})('{session_storage}')""")

        print("✅ Session loaded!")
    except Exception as e:
        print(f"❌ Error loading session: {e}")


async def login_if_needed(page):
    """Logs in only if required."""
    if not USERNAME or not PASSWORD:
        raise ValueError("❌ Username or Password is missing. Check your .env file.")
    try:
        print("🔹 Checking login status...")
        await page.goto(LOGIN_URL, timeout=30000)

        if await page.locator("h3:text('Sign in')").is_visible():
            print("🔑 Logging in...")
            await page.fill("input#email", USERNAME)
            await page.fill("input#password", PASSWORD)
            await page.click("button[type='submit']")
            await page.wait_for_selector("text='Sign out'", timeout=10000)
            print("✅ Login successful!")
        else:
            print("✅ Already logged in.")
    except PlaywrightTimeoutError:
        print("❌ Login page load timeout.")
        raise RuntimeError("❌ Login page load timeout. Check internet connection.")
    except Exception as e:
        print(f"❌ Error during login: {e}")
        raise RuntimeError(f"❌ Error during login: {e}")


async def navigate_to_product_table(page):
    """Navigate to product table with minimal checks."""
    try:
        print("📌 Navigating to product table...")

        await page.wait_for_selector("//button[contains(text(),'Launch Challenge')]", timeout=10000)
        await page.click("//button[contains(text(),'Launch Challenge')]")
        await page.click("//button[contains(text(),'Dashboard')]")
        await page.click("//h3[contains(text(),'Inventory')]")
        await page.click("//h3[contains(text(),'Products')]")
        await page.click("//h3[contains(text(),'Full Catalog')]")

        await page.wait_for_selector("//h3[contains(text(),'Product Inventory')]", timeout=15000)
        print("✅ Reached product table.")
    except PlaywrightTimeoutError:
        print("❌ Timeout while navigating.")
        raise RuntimeError("❌ Timeout while navigating to product table.")
    except Exception as e:
        print(f"❌ Error during navigation: {e}")
        raise RuntimeError(f"❌ Error during navigation: {e}")


async def extract_products(page):
    """Extracts product details with efficient checks."""
    all_products = []
    try:
        await page.wait_for_selector("//h3[contains(text(),'Product Inventory')]", timeout=10000)
        print("🔹 Extracting products...")

        total_table_count_text = await page.locator("//div[contains(text(),'Showing ')]").text_content()
        total_count = int(total_table_count_text.split("of")[1].split("products")[0].strip())

        prev_count = -1
        count = 0
        while count < total_count:
            rows = await page.locator("div.grid>div.rounded-lg").all()
            count = len(rows)

             # Ensure new products are loaded before scrolling further
            if count == prev_count:
                break
            
            prev_count = count
            if count < total_count:
                await rows[-1].hover()
                await page.mouse.wheel(0, 200)
                await page.wait_for_function(
                    "document.querySelectorAll('div.grid>div.rounded-lg').length > " + str(count),
                    timeout=5000
                )

        for item in rows:
            inner_elements = await item.locator("div.p-3>div>div").all()

            name = (await item.locator("div.h-12").text_content()).strip()
            id_text = (await inner_elements[0].text_content()).split(":")[1].strip() if len(inner_elements) > 0 else ""
            shade_text = (await inner_elements[1].text_content()).split("Shade")[1].strip() if len(inner_elements) > 1 else ""
            details_text = (await inner_elements[2].text_content()).split("Details")[1].strip() if len(inner_elements) > 2 else ""
            guarantee_text = (await inner_elements[3].text_content()).split("Guarantee")[1].strip() if len(inner_elements) > 3 else ""

            all_products.append({
                "Product Name": name,
                "ID": id_text,
                "Shade": shade_text,
                "Details": details_text,
                "Guarantee": guarantee_text
            })

        print(f"✅ Extracted {len(all_products)} products.")
        return all_products
    except PlaywrightTimeoutError:
        print("❌ Timeout while extracting products.")
        raise RuntimeError("❌ Timeout while extracting products.")
    except Exception as e:
        print(f"❌ Error extracting products: {e}")
        raise RuntimeError(f"❌ Error extracting products: {e}")


async def save_to_json(data):
    """Save extracted product data to a JSON file."""
    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        print(f"✅ Data saved to {OUTPUT_FILE}")
    except Exception as e:
        print(f"❌ Error saving data: {e}")
        raise RuntimeError(f"❌ Failed to save data: {e}")


async def main():
    """Main Playwright automation function."""
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=False, args=["--start-maximized"])
            context = await browser.new_context(no_viewport=True)

            await load_session(context)
            page = await context.new_page()

            page.set_default_timeout(30000)
            await page.wait_for_load_state("networkidle")

            await login_if_needed(page)
            await navigate_to_product_table(page)
            products = await extract_products(page)

            await save_to_json(products)
            await save_session(context, page)

        except Exception as e:
            print(f"❌ Unexpected error in main: {e}")
        finally:
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
