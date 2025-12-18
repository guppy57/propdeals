"""
Test script for Iowa Realty scraper - scrapes first page only
"""
from iowa_realty_scraper import IowaRealtyScraper, ScraperConfig
from rich.console import Console
from datetime import datetime
import os

def test_first_page():
    """Test scraping the first page only"""
    console = Console()

    # Configure for testing: 1 page only, skip detail pages
    config = ScraperConfig(
        max_pages=1,
        skip_details=True,
        headless=True
    )

    console.print("[bold green]Testing Iowa Realty Scraper (First Page Only)[/bold green]\n")

    try:
        scraper = IowaRealtyScraper(config, console)
        properties = scraper.scrape_all_listings()

        if properties:
            # Save to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(config.output_dir, f"iowa_realty_test_{timestamp}.csv")
            scraper.save_to_csv(output_path)

            # Display summary
            scraper.display_summary()

            # Show sample properties
            console.print("\n[bold cyan]Sample Properties:[/bold cyan]")
            for i, prop in enumerate(properties[:3]):
                console.print(f"\n  Property {i+1}:")
                console.print(f"    Address: {prop.address}")
                console.print(f"    City: {prop.city}, {prop.state} {prop.zip_code}")
                console.print(f"    Price: ${prop.price:,}" if prop.price else "    Price: N/A")
                console.print(f"    Beds: {prop.beds}, Baths: {prop.baths}, Sqft: {prop.sqft:,}" if prop.sqft else f"    Beds: {prop.beds}, Baths: {prop.baths}")
                console.print(f"    Type: {prop.property_type}")
                console.print(f"    URL: {prop.url}")

            console.print(f"\n[green]✓ Test completed successfully![/green]")

        else:
            console.print("[yellow]No properties were scraped[/yellow]")

    except Exception as e:
        console.print(f"[red]Test failed: {str(e)}[/red]")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_first_page()
