"""Analyze Iowa Realty page structure and extract selectors"""
from playwright.sync_api import sync_playwright
import json

def analyze_structure():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = context.new_page()

        print("Navigating to Iowa Realty...")
        page.goto("https://www.iowarealty.com/realestate/search/property-type-SingleFamily", wait_until='networkidle')
        page.wait_for_timeout(3000)

        print("\n" + "="*80)
        print("ANALYZING PAGE STRUCTURE")
        print("="*80)

        # Find property cards
        articles = page.locator('article')
        count = articles.count()
        print(f"\n✓ Found {count} article elements (property cards)")

        if count > 0:
            # Analyze first property card
            first_article = articles.first

            print("\n" + "-"*80)
            print("FIRST PROPERTY CARD STRUCTURE:")
            print("-"*80)

            # Get outer HTML of first card
            outer_html = first_article.evaluate("el => el.outerHTML")

            # Save first card HTML to file
            with open("first_property_card.html", "w", encoding="utf-8") as f:
                f.write(outer_html)
            print("Saved first card HTML to: first_property_card.html")

            # Get the class attribute
            card_class = first_article.get_attribute('class')
            print(f"\nArticle classes: {card_class}")

            # Try to extract visible text
            text = first_article.inner_text()
            print(f"\nCard text content:\n{text[:500]}")

            # Try to find specific elements within the card
            print("\n" + "-"*80)
            print("LOOKING FOR SPECIFIC FIELDS:")
            print("-"*80)

            # Look for price
            price_selectors = ['[data-testid*="price"]', '.price', '[class*="price" i]', 'span:has-text("$")']
            for sel in price_selectors:
                try:
                    price_elem = first_article.locator(sel).first
                    if price_elem.count() > 0:
                        price_text = price_elem.inner_text()
                        print(f"  Price: '{price_text}' (selector: {sel})")
                        break
                except:
                    pass

            # Look for beds/baths
            bed_selectors = ['[data-testid*="bed"]', '[class*="bed" i]', 'span:has-text("bd")', 'span:has-text("bed")']
            for sel in bed_selectors:
                try:
                    bed_elem = first_article.locator(sel).first
                    if bed_elem.count() > 0:
                        bed_text = bed_elem.inner_text()
                        print(f"  Beds: '{bed_text}' (selector: {sel})")
                        break
                except:
                    pass

            # Look for address
            addr_selectors = ['[data-testid*="address"]', '[class*="address" i]', 'h2', 'h3', 'a[href*="/property/"]']
            for sel in addr_selectors:
                try:
                    addr_elem = first_article.locator(sel).first
                    if addr_elem.count() > 0:
                        addr_text = addr_elem.inner_text()
                        print(f"  Address: '{addr_text}' (selector: {sel})")
                        break
                except:
                    pass

            # Look for link to detail page
            link_selectors = ['a[href*="/property/"]', 'a[href*="/listing/"]', 'a']
            for sel in link_selectors:
                try:
                    link_elem = first_article.locator(sel).first
                    if link_elem.count() > 0:
                        href = link_elem.get_attribute('href')
                        print(f"  Detail URL: '{href}' (selector: {sel})")
                        break
                except:
                    pass

        # Check for pagination
        print("\n" + "="*80)
        print("PAGINATION ANALYSIS:")
        print("="*80)

        pagination_selectors = [
            '.pagination',
            '[class*="pagination" i]',
            'nav[aria-label*="page" i]',
            'button:has-text("Next")',
            'a:has-text("Next")',
            '[data-testid*="pagination"]'
        ]

        for sel in pagination_selectors:
            try:
                pag_elem = page.locator(sel)
                if pag_elem.count() > 0:
                    print(f"  ✓ Found pagination with selector: {sel}")
                    print(f"    Text: {pag_elem.first.inner_text()[:200]}")
            except:
                pass

        print("\n" + "="*80)
        print("DONE! Check first_property_card.html for detailed structure")
        print("="*80)

        browser.close()

if __name__ == "__main__":
    analyze_structure()
