"""
Iowa Realty Property Scraper

Standalone Playwright-based scraper for extracting all single-family home listings
from Iowa Realty's search page with comprehensive property details and CSV export.

Usage:
    python iowa_realty_scraper.py
"""

import os
import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime
import time
import random

from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from rich.panel import Panel
from rich.table import Table
import pandas as pd


# ============================================================================
# EXCEPTION HIERARCHY
# ============================================================================

class IowaRealtyScraperError(Exception):
    """Base exception for all Iowa Realty scraper errors"""
    pass


class PaginationError(IowaRealtyScraperError):
    """Raised when pagination discovery or navigation fails"""
    pass


class PropertyExtractionError(IowaRealtyScraperError):
    """Raised when property data extraction fails"""
    pass


class DetailPageError(IowaRealtyScraperError):
    """Raised when detail page loading or parsing fails"""
    pass


class ScrapingTimeoutError(IowaRealtyScraperError):
    """Raised when scraping operation times out"""
    pass


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class ScraperConfig:
    """Configuration settings for the Iowa Realty scraper"""
    base_url: str = "https://www.iowarealty.com/realestate/search/property-type-SingleFamily"
    output_dir: str = "docs"
    headless: bool = True
    page_delay: float = 1.5  # Seconds between listing pages
    detail_delay: float = 2.5  # Seconds between detail pages
    checkpoint_interval: int = 10  # Save checkpoint every N detail pages
    timeout: int = 30000  # 30 seconds default timeout in milliseconds
    max_pages: Optional[int] = None  # Limit pages for testing (None = all pages)
    skip_details: bool = False  # Skip detail page scraping (for testing listing extraction only)


# ============================================================================
# DATA MODEL
# ============================================================================

@dataclass
class PropertyListing:
    """Data model for a property listing"""

    # Core identifiers
    url: str
    property_id: Optional[str] = None

    # Listing page data
    address: Optional[str] = None
    price: Optional[int] = None
    beds: Optional[int] = None
    baths: Optional[float] = None
    sqft: Optional[int] = None
    listing_type: Optional[str] = None  # Active, Pending, etc.

    # Detail page data
    full_address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    year_built: Optional[int] = None
    lot_size: Optional[str] = None
    property_type: Optional[str] = None
    description: Optional[str] = None
    listing_date: Optional[str] = None
    days_on_market: Optional[int] = None
    mls_number: Optional[str] = None

    # Additional fields discovered during scraping
    extras: Dict[str, Any] = field(default_factory=dict)

    # Metadata
    scraped_at: str = field(default_factory=lambda: datetime.now().isoformat())


# ============================================================================
# MAIN SCRAPER CLASS
# ============================================================================

class IowaRealtyScraper:
    """
    Scraper for Iowa Realty property listings.

    Uses Playwright for headless browser automation to extract comprehensive
    property data from both listing pages and individual property detail pages.
    """

    def __init__(self, config: ScraperConfig, console: Console):
        """
        Initialize the Iowa Realty scraper.

        Args:
            config: Scraper configuration settings
            console: Rich console for user feedback
        """
        self.config = config
        self.console = console
        self.properties: List[PropertyListing] = []
        self.errors: List[Dict[str, str]] = []
        self.stats = {
            'total_pages': 0,
            'total_properties': 0,
            'detail_pages_scraped': 0,
            'errors': 0
        }

    def scrape_all_listings(self) -> List[PropertyListing]:
        """
        Main entry point for scraping all property listings.

        Returns:
            List of PropertyListing objects with scraped data

        Raises:
            IowaRealtyScraperError: For critical scraping failures
        """
        self.console.print(Panel.fit(
            "[bold cyan]Iowa Realty Property Scraper[/bold cyan]\n"
            f"Target: {self.config.base_url}\n"
            f"Headless: {self.config.headless}",
            border_style="cyan"
        ))

        try:
            # Perform scraping with browser
            properties = self._scrape_with_browser()
            return properties

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Scraping interrupted by user[/yellow]")
            self._save_checkpoint()
            self.console.print("[cyan]Progress saved to checkpoint file[/cyan]")
            raise

        except Exception as e:
            self.console.print(f"[red]Critical error during scraping: {str(e)}[/red]")
            self._save_checkpoint()
            raise IowaRealtyScraperError(f"Scraping failed: {str(e)}")

    def _scrape_with_browser(self) -> List[PropertyListing]:
        """
        Internal method to perform scraping with Playwright browser.

        Uses context manager pattern for proper resource cleanup.

        Returns:
            List of PropertyListing objects
        """
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(
                headless=self.config.headless,
                args=['--no-sandbox', '--disable-dev-shm-usage']  # Linux compatibility
            )

            try:
                # Create browser context with realistic settings
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )

                # Set default timeout for all operations
                context.set_default_timeout(self.config.timeout)

                # Create new page
                page = context.new_page()

                # Perform scraping workflow
                result = self._perform_scraping(page)

                return result

            finally:
                # Always cleanup browser resources
                browser.close()

    def _perform_scraping(self, page: Page) -> List[PropertyListing]:
        """
        Execute the main scraping workflow.

        Args:
            page: Playwright Page object

        Returns:
            List of PropertyListing objects
        """
        # Step 1: Navigate to base URL
        self.console.print("[cyan]Navigating to search page...[/cyan]")
        page.goto(self.config.base_url, wait_until='networkidle')
        page.wait_for_timeout(2000)  # Wait for dynamic content

        # Step 2: Discover pagination
        total_pages = self._discover_pagination(page)

        # Limit pages if max_pages is set
        if self.config.max_pages:
            total_pages = min(total_pages, self.config.max_pages)
            self.console.print(f"[yellow]Limiting to {total_pages} pages (max_pages={self.config.max_pages})[/yellow]")

        self.console.print(f"[green]✓ Found {total_pages} pages to scrape[/green]")

        # Step 3: Scrape all listing pages
        self.console.print(f"\n[bold cyan]Scraping listing pages...[/bold cyan]")
        for page_num in range(1, total_pages + 1):
            try:
                self._scrape_listing_page(page, page_num)
                self.stats['total_pages'] += 1

                # Politeness delay between pages
                if page_num < total_pages:
                    delay = self.config.page_delay + random.uniform(-0.5, 0.5)
                    time.sleep(delay)

            except Exception as e:
                self.console.print(f"[red]Error on page {page_num}: {str(e)}[/red]")
                self.errors.append({
                    'type': 'listing_page',
                    'page': page_num,
                    'error': str(e)
                })
                self.stats['errors'] += 1

        self.console.print(f"\n[green]✓ Scraped {len(self.properties)} properties from {self.stats['total_pages']} pages[/green]")

        # Step 4: Scrape detail pages (unless skip_details is True)
        if self.properties and not self.config.skip_details:
            self.console.print(f"\n[bold cyan]Scraping detail pages...[/bold cyan]")
            self._scrape_all_detail_pages(page)
        elif self.config.skip_details:
            self.console.print(f"\n[yellow]Skipping detail pages (skip_details=True)[/yellow]")

        return self.properties

    def _discover_pagination(self, page: Page) -> int:
        """
        Discover total number of pages from pagination controls.

        Args:
            page: Playwright Page object

        Returns:
            Total number of pages (minimum 1)
        """
        try:
            # Try to find pagination element
            pagination = page.locator('.pagination').first

            if pagination.count() == 0:
                self.console.print("[yellow]No pagination found, assuming single page[/yellow]")
                return 1

            # Find all page number links
            page_links = pagination.locator('a')
            page_numbers = []

            for i in range(page_links.count()):
                try:
                    text = page_links.nth(i).inner_text().strip()
                    if text.isdigit():
                        page_numbers.append(int(text))
                except:
                    continue

            if page_numbers:
                total_pages = max(page_numbers)
                return total_pages

            # Fallback: assume single page
            self.console.print("[yellow]Could not determine page count, assuming single page[/yellow]")
            return 1

        except Exception as e:
            self.console.print(f"[yellow]Pagination discovery error: {str(e)}, assuming single page[/yellow]")
            return 1

    def _scrape_listing_page(self, page: Page, page_num: int):
        """
        Scrape all properties from a single listing page.

        Args:
            page: Playwright Page object
            page_num: Current page number
        """
        # Navigate to specific page if not on page 1
        if page_num > 1:
            # Click on page number
            try:
                page_link = page.locator(f'.pagination a:has-text("{page_num}")').first
                page_link.click()
                page.wait_for_timeout(2000)  # Wait for page load
            except:
                self.console.print(f"[yellow]Could not navigate to page {page_num}[/yellow]")
                return

        self.console.print(f"[cyan]Scraping page {page_num}...[/cyan]")

        # Find all property cards
        articles = page.locator('article')
        card_count = articles.count()

        self.console.print(f"  Found {card_count} properties on page {page_num}")

        # Extract data from each card
        for i in range(card_count):
            try:
                card = articles.nth(i)
                property_data = self._extract_card_data(card)
                self.properties.append(property_data)
                self.stats['total_properties'] += 1
            except Exception as e:
                self.console.print(f"  [yellow]Warning: Failed to extract property {i+1}: {str(e)}[/yellow]")
                self.stats['errors'] += 1

    def _extract_card_data(self, card) -> PropertyListing:
        """
        Extract data from a single property card.

        Args:
            card: Playwright Locator for the article element

        Returns:
            PropertyListing object with extracted data
        """
        # Extract property ID from article id attribute
        property_id = None
        try:
            article_id = card.get_attribute('id')
            if article_id and article_id.startswith('property_'):
                property_id = article_id.replace('property_', '')
        except:
            pass

        # Extract price
        price = None
        try:
            price_elem = card.locator('.price').first
            if price_elem.count() > 0:
                price_text = price_elem.inner_text()
                price = self._parse_price(price_text)
        except:
            pass

        # Extract status
        status = None
        try:
            status_elem = card.locator('.status').first
            if status_elem.count() > 0:
                status = status_elem.inner_text().strip()
        except:
            pass

        # Extract addresses (two h3.address elements)
        address_line1 = None
        address_line2 = None
        city = None
        state = None
        zip_code = None
        try:
            address_elems = card.locator('h3.address')
            if address_elems.count() >= 1:
                address_line1 = address_elems.nth(0).inner_text().strip()
            if address_elems.count() >= 2:
                address_line2 = address_elems.nth(1).inner_text().strip()
                # Parse city, state, zip from second address line
                city, state, zip_code = self._parse_city_state_zip(address_line2)
        except:
            pass

        # Combine addresses
        full_address = address_line1
        if address_line2:
            full_address = f"{address_line1}, {address_line2}" if address_line1 else address_line2

        # Extract property details from ul.info list
        property_type = None
        beds = None
        baths = None
        sqft = None
        try:
            info_items = card.locator('ul.info li')
            if info_items.count() > 0:
                property_type = info_items.nth(0).inner_text().strip()
            if info_items.count() > 1:
                beds_text = info_items.nth(1).inner_text()
                beds = self._parse_beds(beds_text)
            if info_items.count() > 2:
                baths_text = info_items.nth(2).inner_text()
                baths = self._parse_baths(baths_text)
            if info_items.count() > 3:
                sqft_text = info_items.nth(3).inner_text()
                sqft = self._parse_sqft(sqft_text)
        except:
            pass

        # Build detail page URL
        detail_url = self._build_detail_url(property_id, address_line1) if property_id and address_line1 else ""

        # Create PropertyListing object
        return PropertyListing(
            url=detail_url,
            property_id=property_id,
            address=address_line1,
            full_address=full_address,
            city=city,
            state=state,
            zip_code=zip_code,
            price=price,
            beds=beds,
            baths=baths,
            sqft=sqft,
            property_type=property_type,
            listing_type=status
        )

    def _scrape_all_detail_pages(self, page: Page):
        """
        Scrape detail pages for all properties.

        Args:
            page: Playwright Page object
        """
        total = len(self.properties)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console
        ) as progress:
            task = progress.add_task(f"[cyan]Scraping detail pages...", total=total)

            for idx, prop in enumerate(self.properties):
                try:
                    if prop.url:
                        detail_data = self._scrape_detail_page(page, prop.url)
                        self._merge_detail_data(prop, detail_data)
                        self.stats['detail_pages_scraped'] += 1

                        # Save checkpoint periodically
                        if (idx + 1) % self.config.checkpoint_interval == 0:
                            self._save_checkpoint()

                    # Politeness delay
                    if idx < total - 1:
                        delay = self.config.detail_delay + random.uniform(-0.5, 0.5)
                        time.sleep(delay)

                    progress.update(task, advance=1)

                except Exception as e:
                    self.console.print(f"[yellow]Error on detail page {prop.url}: {str(e)}[/yellow]")
                    self.errors.append({
                        'type': 'detail_page',
                        'url': prop.url,
                        'error': str(e)
                    })
                    self.stats['errors'] += 1
                    progress.update(task, advance=1)

    def _scrape_detail_page(self, page: Page, url: str) -> Dict[str, Any]:
        """
        Scrape additional data from property detail page.

        Args:
            page: Playwright Page object
            url: URL of the detail page

        Returns:
            Dictionary with additional property details
        """
        detail_data = {}

        try:
            # Navigate to detail page
            page.goto(url, wait_until='networkidle', timeout=self.config.timeout)
            page.wait_for_timeout(1000)

            # TODO: Add selectors for detail page fields once we explore a detail page
            # For now, just return empty dict
            # Future fields: description, MLS number, year built, lot size, listing date, etc.

        except PlaywrightTimeout:
            raise DetailPageError(f"Timeout loading detail page: {url}")
        except Exception as e:
            raise DetailPageError(f"Error scraping detail page: {str(e)}")

        return detail_data

    def _merge_detail_data(self, listing: PropertyListing, detail_data: Dict[str, Any]):
        """
        Merge detail page data into existing PropertyListing.

        Args:
            listing: PropertyListing object to update
            detail_data: Dictionary with detail page data
        """
        for key, value in detail_data.items():
            if hasattr(listing, key) and value is not None:
                setattr(listing, key, value)
            elif value is not None:
                listing.extras[key] = value

    # Parsing helper functions
    def _parse_price(self, text: str) -> Optional[int]:
        """Parse price string to integer"""
        try:
            # Remove $, commas, and spaces
            cleaned = re.sub(r'[$,\s]', '', text)
            return int(cleaned)
        except:
            return None

    def _parse_beds(self, text: str) -> Optional[int]:
        """Parse beds string to integer"""
        try:
            # Extract first number from text like "3 Beds"
            match = re.search(r'(\d+)', text)
            if match:
                return int(match.group(1))
        except:
            pass
        return None

    def _parse_baths(self, text: str) -> Optional[float]:
        """Parse baths string to float"""
        try:
            # Extract number (including decimals) from text like "2.5 Baths"
            match = re.search(r'([\d.]+)', text)
            if match:
                return float(match.group(1))
        except:
            pass
        return None

    def _parse_sqft(self, text: str) -> Optional[int]:
        """Parse square footage string to integer"""
        try:
            # Remove commas and "sqft", extract number
            cleaned = re.sub(r'[,\s]', '', text.lower())
            cleaned = cleaned.replace('sqft', '').replace('sq', '')
            return int(cleaned)
        except:
            return None

    def _parse_city_state_zip(self, text: str) -> tuple:
        """
        Parse city, state, and ZIP code from address line.

        Args:
            text: Address line like "Mason City, IA 50401"

        Returns:
            Tuple of (city, state, zip_code)
        """
        city = None
        state = None
        zip_code = None

        try:
            # Pattern: "City Name, ST 12345"
            match = re.match(r'([^,]+),\s*([A-Z]{2})\s+(\d{5}(?:-\d{4})?)', text)
            if match:
                city = match.group(1).strip()
                state = match.group(2).strip()
                zip_code = match.group(3).strip()
        except:
            pass

        return city, state, zip_code

    def _build_detail_url(self, property_id: str, address: str) -> str:
        """
        Build detail page URL from property ID and address.

        Args:
            property_id: Property ID (e.g., "117500519")
            address: Street address (e.g., "659 3rd Place")

        Returns:
            Full detail page URL
        """
        try:
            # Convert address to slug format
            # "659 3rd Place" → "659-3rd-place"
            slug = address.lower().replace(' ', '-')
            slug = re.sub(r'[^a-z0-9-]', '', slug)

            return f"https://www.iowarealty.com/details/{property_id}/{slug}"
        except:
            return f"https://www.iowarealty.com/details/{property_id}"

    # Checkpoint/Resume functionality
    def _save_checkpoint(self):
        """Save current progress to checkpoint file"""
        checkpoint_path = '.iowa_realty_checkpoint.json'
        checkpoint_data = {
            'properties': [asdict(p) for p in self.properties],
            'stats': self.stats,
            'errors': self.errors,
            'timestamp': datetime.now().isoformat()
        }

        with open(checkpoint_path, 'w') as f:
            json.dump(checkpoint_data, f, indent=2)

        self.console.print(f"[green]Checkpoint saved: {len(self.properties)} properties[/green]")

    def _load_checkpoint(self) -> Optional[Dict[str, Any]]:
        """Load checkpoint data if it exists"""
        checkpoint_path = '.iowa_realty_checkpoint.json'

        if os.path.exists(checkpoint_path):
            with open(checkpoint_path, 'r') as f:
                checkpoint_data = json.load(f)

            self.console.print(f"[cyan]Found checkpoint from {checkpoint_data['timestamp']}[/cyan]")
            self.console.print(f"[cyan]  - {len(checkpoint_data['properties'])} properties scraped[/cyan]")

            return checkpoint_data

        return None

    def _cleanup_checkpoint(self):
        """Remove checkpoint file after successful completion"""
        checkpoint_path = '.iowa_realty_checkpoint.json'
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
            self.console.print("[green]Checkpoint file cleaned up[/green]")

    # CSV Export
    def save_to_csv(self, output_path: str):
        """
        Convert properties to DataFrame and save as CSV.

        Args:
            output_path: Path where CSV file should be saved
        """
        if not self.properties:
            self.console.print("[yellow]No properties to save[/yellow]")
            return

        # Convert to list of dicts
        data = []
        for prop in self.properties:
            prop_dict = asdict(prop)
            # Flatten extras dict into separate columns
            extras = prop_dict.pop('extras', {})
            prop_dict.update(extras)
            data.append(prop_dict)

        # Create DataFrame with logical column ordering
        df = pd.DataFrame(data)

        # Reorder columns for usability
        priority_cols = ['url', 'address', 'city', 'state', 'zip_code', 'price',
                        'beds', 'baths', 'sqft', 'year_built', 'lot_size',
                        'listing_type', 'mls_number', 'description', 'scraped_at']

        # Keep priority columns in order, then add any extras
        cols = [c for c in priority_cols if c in df.columns]
        extra_cols = [c for c in df.columns if c not in cols]
        df = df[cols + extra_cols]

        # Save to CSV
        df.to_csv(output_path, index=False)
        self.console.print(f"[green]✓ Saved {len(df)} properties to {output_path}[/green]")

    def display_summary(self):
        """Display final scraping statistics"""
        table = Table(title="Scraping Summary", border_style="cyan")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Pages Scraped", str(self.stats['total_pages']))
        table.add_row("Total Properties Found", str(self.stats['total_properties']))
        table.add_row("Detail Pages Scraped", str(self.stats['detail_pages_scraped']))
        table.add_row("Errors Encountered", str(self.stats['errors']))

        if self.stats['total_properties'] > 0:
            success_rate = (self.stats['detail_pages_scraped'] / self.stats['total_properties']) * 100
            table.add_row("Success Rate", f"{success_rate:.1f}%")

        self.console.print(table)


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def main():
    """Main entry point for the scraper"""
    console = Console()

    # Initialize configuration
    config = ScraperConfig()

    # Initialize scraper
    scraper = IowaRealtyScraper(config, console)

    # Check for checkpoint
    checkpoint = scraper._load_checkpoint()
    if checkpoint:
        # TODO: Add user prompt to resume
        console.print("[yellow]Checkpoint resume not yet implemented[/yellow]")

    try:
        # Run scraper
        properties = scraper.scrape_all_listings()

        if properties:
            # Save to CSV
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(config.output_dir, f"iowa_realty_{timestamp}.csv")
            scraper.save_to_csv(output_path)

            # Display summary
            scraper.display_summary()

            # Cleanup checkpoint
            scraper._cleanup_checkpoint()
        else:
            console.print("[yellow]No properties were scraped[/yellow]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Scraping stopped by user[/yellow]")
        console.print("[cyan]Run again to resume from checkpoint[/cyan]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")
        raise


if __name__ == "__main__":
    main()
