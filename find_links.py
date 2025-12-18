"""Find links to detail pages"""
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    )
    page = context.new_page()

    print("Loading page...")
    page.goto("https://www.iowarealty.com/realestate/search/property-type-SingleFamily", wait_until='networkidle')
    page.wait_for_timeout(2000)

    # Get first article
    first_article = page.locator('article').first

    print("\nSearching for links in first property card...")
    print("="*80)

    # Find all links within the article
    links = first_article.locator('a')
    link_count = links.count()

    print(f"Found {link_count} links in the card\n")

    for i in range(link_count):
        link = links.nth(i)
        href = link.get_attribute('href')
        text = link.inner_text() if link.inner_text() else "[no text]"
        print(f"Link {i+1}:")
        print(f"  href: {href}")
        print(f"  text: {text}")
        print()

    # Check if the whole article is clickable
    onclick = first_article.get_attribute('onclick')
    if onclick:
        print(f"Article has onclick: {onclick}")

    # Check for data attributes
    attrs = first_article.evaluate("""el => {
        const attrs = {};
        for (let attr of el.attributes) {
            if (attr.name.startsWith('data-')) {
                attrs[attr.name] = attr.value;
            }
        }
        return attrs;
    }""")

    if attrs:
        print("\nData attributes on article:")
        for key, val in attrs.items():
            print(f"  {key}: {val}")

    # Try to click the card and see where it goes
    print("\n" + "="*80)
    print("Attempting to click the first property card...")
    print("="*80)

    try:
        # Get the current URL
        current_url = page.url
        print(f"Current URL: {current_url}")

        # Click the first article
        first_article.click()

        # Wait for navigation
        page.wait_for_timeout(2000)

        new_url = page.url
        print(f"New URL after click: {new_url}")

        if new_url != current_url:
            print(f"\n✓ Successfully navigated to detail page!")
            print(f"  Detail URL pattern: {new_url}")

            # Save the detail page HTML
            with open("detail_page_sample.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print(f"  Saved detail page HTML to: detail_page_sample.html")

    except Exception as e:
        print(f"Error clicking card: {e}")

    browser.close()
