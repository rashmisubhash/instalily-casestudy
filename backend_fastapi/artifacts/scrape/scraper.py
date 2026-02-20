import asyncio
import json
import os
import random
import re
from collections import defaultdict
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from pathlib import Path

BASE_URL = "https://www.partselect.com"
OUTPUT_DIR = Path("artifacts/scrape/data")

CATEGORY_URLS = {
    "Refrigerator": f"{BASE_URL}/Refrigerator-Parts.htm",
    "Dishwasher": f"{BASE_URL}/Dishwasher-Parts.htm",
}

async def collect_brand_pages(page, category_url, appliance_type):
    brand_urls = []

    resp = await page.goto(category_url, wait_until="domcontentloaded")
    if resp.status != 200:
        return []

    soup = BeautifulSoup(await page.content(), "html.parser")

    pattern = rf'/[A-Za-z]+-{appliance_type}-Parts\.htm'

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if re.search(pattern, href):
            full = href if href.startswith("http") else BASE_URL + href
            if full not in brand_urls:
                brand_urls.append(full)

    return brand_urls



async def random_delay(min_sec=2, max_sec=4):
    await asyncio.sleep(random.uniform(min_sec, max_sec))


async def create_browser(playwright):
    browser = await playwright.chromium.launch(
        headless=False,
        args=["--disable-blink-features=AutomationControlled"],
    )

    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1920, "height": 1080},
        locale="en-US",
    )

    page = await context.new_page()
    await page.add_init_script(
        'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
    )

    return browser, context, page


async def collect_part_urls(page, url):
    part_urls = []

    resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    if resp.status != 200:
        return []

    await random_delay()

    soup = BeautifulSoup(await page.content(), "html.parser")

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if re.search(r'/PS\d{5,}.*\.htm', href):
            clean = re.sub(r'\?.*$', '', href)
            clean = re.sub(r'#.*$', '', clean)
            full = clean if clean.startswith("http") else BASE_URL + clean
            if full not in part_urls:
                part_urls.append(full)

    return part_urls


async def scrape_part_page(page, url):
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if resp.status != 200:
            return None

        await random_delay()

        soup = BeautifulSoup(await page.content(), "html.parser")

        data = {}

        ps_match = re.search(r'PS(\d+)', url)
        if not ps_match:
            return None

        ps_number = f"PS{ps_match.group(1)}"
        data["part_id"] = ps_number
        data["url"] = url

        # Title
        title_el = soup.select_one("h1")
        if title_el:
            data["title"] = title_el.get_text(strip=True)

        # Description
        desc_el = soup.select_one(".pd__description")
        if desc_el:
            data["description"] = desc_el.get_text(strip=True)[:1500]

        # Price
        price_el = soup.select_one(".pd__price")
        if price_el:
            price_match = re.search(r'\$[\d,.]+', price_el.get_text())
            if price_match:
                data["price"] = price_match.group(0)

        # Availability
        stock_el = soup.select_one(".pd__ships-today")
        data["availability"] = "In Stock" if stock_el else "Check site"

        # Compatible models
        crossref = soup.select_one(".pd__crossref__list")
        if crossref:
            model_links = crossref.find_all("a")
            models = []

            for link in model_links:
                model_text = link.get_text(strip=True)

                # Clean and validate
                if (
                    model_text
                    and any(c.isdigit() for c in model_text)
                    and 6 <= len(model_text) <= 15
                    and not model_text.startswith(("REFRIG", "DISHWA"))
                ):
                    models.append(model_text.upper())

            if models:
                data["compatible_models"] = list(set(models))

        return data

    except:
        return None


async def run(max_parts_per_category=500):
    os.makedirs("data", exist_ok=True)

    parts_list = []
    part_id_map = {}
    model_to_parts_map = defaultdict(list)
    model_id_to_parts_map = defaultdict(list)
    seen_ps = set()

    async with async_playwright() as p:
        browser, context, page = await create_browser(p)

        for appliance_type, category_url in CATEGORY_URLS.items():
            print(f"\nScraping {appliance_type}...")

            part_urls = await collect_part_urls(page, category_url)

            brand_urls = await collect_brand_pages(page, category_url, appliance_type)
            for brand_url in brand_urls:
                brand_parts = await collect_part_urls(page, brand_url)
                for u in brand_parts:
                    if u not in part_urls:
                        part_urls.append(u)

            print(f"Collected {len(part_urls)} URLs")

            # part_urls = part_urls[:max_parts_per_category]

            for i, url in enumerate(part_urls):
                print(f"[{i+1}/{len(part_urls)}] {url}")

                part_data = await scrape_part_page(page, url)
                if not part_data:
                    continue

                ps_id = part_data["part_id"].upper()
                if ps_id in seen_ps:
                    continue

                seen_ps.add(ps_id)
                part_data["appliance_type"] = appliance_type

                parts_list.append(part_data)
                part_id_map[ps_id] = part_data

                models = part_data.get("compatible_models", [])
                for model in models:
                    clean_model = model.strip().upper()

                    raw_key = f"{clean_model} {appliance_type}".lower()
                    model_to_parts_map[raw_key].append(ps_id)
                    model_id_to_parts_map[clean_model].append(ps_id)

                await random_delay()

        await browser.close()

    # Remove duplicates
    model_to_parts_map = {
        k: list(set(v)) for k, v in model_to_parts_map.items()
    }
    model_id_to_parts_map = {
        k: list(set(v)) for k, v in model_id_to_parts_map.items()
    }
    
    all_part_ids = set(part_id_map.keys())

    for model, part_ids in model_id_to_parts_map.items():
        for pid in part_ids:
            if pid not in all_part_ids:
                raise ValueError(f"Invalid mapping: {model} -> {pid}")

    print("Integrity check passed.")

    with open(OUTPUT_DIR / "parts.json", "w") as f:
        json.dump(parts_list, f, indent=2)

    with open(OUTPUT_DIR / "part_id_map.json", "w") as f:
        json.dump(part_id_map, f, indent=2)

    with open(OUTPUT_DIR / "model_to_parts_map.json", "w") as f:
        json.dump(model_to_parts_map, f, indent=2)

    with open(OUTPUT_DIR / "model_id_to_parts_map.json", "w") as f:
        json.dump(model_id_to_parts_map, f, indent=2)

    print("\nIngestion complete.")


if __name__ == "__main__":
    asyncio.run(run())
    
# python artifacts/scrape/scraper.py