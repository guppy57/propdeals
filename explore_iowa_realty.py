"""
Iowa Realty Exploration Script

This script opens the Iowa Realty search page in a visible browser window
to allow manual inspection of the HTML structure, property cards, and pagination.

Run this BEFORE implementing the full scraper to identify correct selectors.
"""

from playwright.sync_api import sync_playwright
import time

def explore_site():
    """Open Iowa Realty search page for manual inspection"""
    print("🔍 Launching browser for site exploration...")
    print("=" * 80)

    with sync_playwright() as p:
        # Launch browser in VISIBLE mode
        browser = p.chromium.launch(
            headless=False,  # Show the browser
            args=['--no-sandbox', '--disable-dev-shm-usage']
        )

        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )

        page = context.new_page()

        print("📍 Navigating to: https://www.iowarealty.com/realestate/search/property-type-SingleFamily")
        page.goto("https://www.iowarealty.com/realestate/search/property-type-SingleFamily", wait_until='networkidle')

        print("✅ Page loaded successfully!")
        print("\n" + "=" * 80)
        print("MANUAL INSPECTION TASKS:")
        print("=" * 80)
        print("1. Look for property cards - what HTML structure do they use?")
        print("   - Right-click on a property → Inspect → Note the class names")
        print("   - Are they <div>, <article>, or <li> elements?")
        print("   - What classes or data attributes identify them?")
        print()
        print("2. Inspect property fields on listing cards:")
        print("   - Price: Look for $ amount - what element/class?")
        print("   - Address: Where is the address displayed?")
        print("   - Beds/Baths: What format? (e.g., '3 bd', '2.5 ba')")
        print("   - Square footage: How is it displayed?")
        print("   - Property URL: Inspect the link - what's the href pattern?")
        print()
        print("3. Check pagination:")
        print("   - Scroll to bottom of page")
        print("   - Are there page numbers? (1, 2, 3...)")
        print("   - Is there a 'Next' button?")
        print("   - What classes/IDs do pagination controls have?")
        print("   - How many properties per page?")
        print()
        print("4. Visit ONE property detail page:")
        print("   - Click on a property")
        print("   - What additional details are available?")
        print("   - MLS number, year built, lot size, description?")
        print("   - What's the URL pattern for detail pages?")
        print("=" * 80)

        # Take screenshots
        print("\n📸 Taking screenshot...")
        page.screenshot(path="iowa_realty_listing_page.png", full_page=True)
        print("✅ Screenshot saved: iowa_realty_listing_page.png")

        # Save HTML
        print("\n💾 Saving page HTML...")
        with open("iowa_realty_page.html", "w", encoding="utf-8") as f:
            f.write(page.content())
        print("✅ HTML saved: iowa_realty_page.html")

        print("\n" + "=" * 80)
        print("Browser will stay open for manual inspection.")
        print("Press Ctrl+C in this terminal when done exploring.")
        print("=" * 80)

        try:
            # Keep browser open until user closes it
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\n✅ Exploration complete!")
            print("\nNext steps:")
            print("1. Review the screenshot and HTML file")
            print("2. Document the selectors you found")
            print("3. Update iowa_realty_scraper.py with the correct selectors")

        browser.close()


if __name__ == "__main__":
    explore_site()
