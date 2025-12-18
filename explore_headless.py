"""Quick headless exploration to fetch HTML"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = context.new_page()

    print("Navigating to Iowa Realty...")
    page.goto("https://www.iowarealty.com/realestate/search/property-type-SingleFamily", wait_until='networkidle')

    print("Page loaded, waiting for content...")
    page.wait_for_timeout(3000)

    print("Taking screenshot...")
    page.screenshot(path="iowa_realty_screenshot.png", full_page=False)

    print("Saving HTML...")
    with open("iowa_realty_source.html", "w", encoding="utf-8") as f:
        f.write(page.content())

    # Try to find property cards
    print("\nLooking for property cards...")

    # Try common selectors
    selectors_to_try = [
        '.property-card',
        '.listing-card',
        '.property-item',
        '[data-testid*="property"]',
        '[data-testid*="listing"]',
        'article',
        '.search-result',
        '.listing',
    ]

    for selector in selectors_to_try:
        count = page.locator(selector).count()
        if count > 0:
            print(f"  ✓ Found {count} elements with selector: {selector}")

    print("\nDone! Check iowa_realty_source.html and iowa_realty_screenshot.png")
    browser.close()
