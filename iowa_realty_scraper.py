"""
Iowa Realty Property Status Scraper

This module provides web scraping functionality to extract property listing status
from iowarealty.com using Playwright for headless browser automation.
"""

import time
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from rich.console import Console
from supabase import Client


# Custom Exceptions
class IowaRealtyScraperError(Exception):
    """Base exception for all Iowa Realty scraper errors"""
    pass


class PropertyNotFoundError(IowaRealtyScraperError):
    """Raised when property is not found on iowarealty.com or Google"""
    pass


class ScrapingTimeoutError(IowaRealtyScraperError):
    """Raised when scraping operation times out"""
    pass


class ScrapingError(IowaRealtyScraperError):
    """Raised for general scraping failures (network, parsing, etc.)"""
    pass


class IowaRealtyScraper:
    """
    Scrapes property listing status from iowarealty.com.

    Uses Playwright for headless browser automation to search Google for
    Iowa Realty property listings and extract current listing status.
    """

    def __init__(self, supabase_client: Client, console: Console):
        """
        Initialize the Iowa Realty scraper.

        Args:
            supabase_client: Supabase client for database operations
            console: Rich console for user feedback
        """
        self.supabase = supabase_client
        self.console = console
        self.google_url = "https://www.google.com"
        self.timeout = 30000  # 30 seconds default timeout

    def get_property_status_by_address(self, address: str) -> str:
        """
        Scrape property listing status for a given address from iowarealty.com.

        This method uses Playwright to automate Google search to find the Iowa Realty
        listing page, then extracts the current listing status.

        Args:
            address: Full property address (e.g., "1234 Main St, Des Moines, IA")

        Returns:
            str: Property listing status (e.g., "Active", "Pending", "Sold")

        Raises:
            ValueError: If address is empty/invalid format
            PropertyNotFoundError: If property is not found on iowarealty.com
            ScrapingTimeoutError: If page load or element wait times out
            ScrapingError: For other scraping failures (network, element not found, etc.)

        Example:
            >>> scraper = IowaRealtyScraper(supabase_client, console)
            >>> status = scraper.get_property_status_by_address("4545 NE Aurora Ave, Des Moines, IA")
            >>> print(status)
            'Active'
        """
        # Input validation
        if not address or not address.strip():
            raise ValueError("Address cannot be empty")

        address = address.strip()

        # Show progress with Rich console
        with self.console.status(
            f"[bold cyan]Scraping status for: {address}...",
            spinner="dots"
        ):
            try:
                status = self._scrape_with_browser(address)
                self.console.print(f"[green]✓ Found status: {status}[/green]")
                return status

            except PropertyNotFoundError as e:
                self.console.print(f"[yellow]⚠ {str(e)}[/yellow]")
                raise

            except ScrapingTimeoutError as e:
                self.console.print(f"[yellow]⏱ {str(e)}[/yellow]")
                raise

            except ScrapingError as e:
                self.console.print(f"[red]✗ {str(e)}[/red]")
                raise

            except Exception as e:
                error_msg = f"Unexpected error during scraping: {str(e)}"
                self.console.print(f"[red]✗ {error_msg}[/red]")
                raise ScrapingError(error_msg)

    def _scrape_with_browser(self, address: str) -> str:
        """
        Internal method to perform the actual scraping with Playwright.

        Uses context manager pattern for proper resource cleanup.

        Args:
            address: Address to search for

        Returns:
            str: Property listing status

        Raises:
            PropertyNotFoundError: If property not found
            ScrapingTimeoutError: If operation times out
            ScrapingError: For other failures
        """
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']  # Linux compatibility
            )

            try:
                # Create browser context with reasonable timeout
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )

                # Set default timeout for all operations
                context.set_default_timeout(self.timeout)

                # Create new page
                page = context.new_page()

                # Perform scraping
                result = self._perform_scraping(page, address)

                return result

            finally:
                # Always cleanup browser resources
                browser.close()

    def _perform_scraping(self, page: Page, address: str) -> str:
        """
        Execute the scraping workflow to get property status.

        Steps:
        1. Navigate to Google
        2. Search for "iowarealty.com {address}"
        3. Click on the Iowa Realty listing
        4. Extract property status
        5. Handle error states

        Args:
            page: Playwright Page object
            address: Address to search for

        Returns:
            str: Property listing status

        Raises:
            PropertyNotFoundError: If property not found
            ScrapingTimeoutError: If timeout occurs
            ScrapingError: For other failures
        """
        try:
            # Step 1: Navigate to Google
            self.console.print(f"[cyan]Navigating to Google...[/cyan]")
            page.goto(self.google_url, wait_until='networkidle')

            # Step 2: Perform Google search
            search_query = f"iowarealty.com {address}"
            self.console.print(f"[cyan]Searching for: {search_query}[/cyan]")

            # Wait for page to be fully loaded
            page.wait_for_load_state('domcontentloaded')
            time.sleep(1)

            # Find Google search input
            search_input = None
            search_selectors = [
                'textarea[name="q"]',  # New Google search box (textarea)
                'input[name="q"]',     # Old Google search box (input)
                '#APjFqb',             # Google's search box ID
                'textarea.gLFyf',      # Google's search box class
            ]

            for selector in search_selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        search_input = locator
                        break
                except:
                    continue

            if not search_input:
                raise ScrapingError("Could not find Google search input field")

            # Enter search query
            search_input.click()
            search_input.fill(search_query)
            time.sleep(0.5)
            search_input.press("Enter")

            # Wait for search results
            self.console.print(f"  [dim]Waiting for search results...[/dim]")
            page.wait_for_load_state('networkidle')
            time.sleep(2)

            # Step 3: Find Iowa Realty listing in search results
            self.console.print("[cyan]Looking for Iowa Realty listing...[/cyan]")

            # Look for Iowa Realty links
            iowa_realty_link = None
            link_patterns = [
                'a[href*="iowarealty.com/realestate/details/"]',
                'a[href*="iowarealty.com"][href*="details"]',
            ]

            for pattern in link_patterns:
                try:
                    locator = page.locator(pattern).first
                    if locator.count() > 0:
                        iowa_realty_link = locator
                        break
                except:
                    continue

            if not iowa_realty_link:
                raise PropertyNotFoundError(
                    f"Property '{address}' not found on iowarealty.com via Google search"
                )

            # Click the Iowa Realty listing
            self.console.print("[cyan]Opening property details...[/cyan]")
            iowa_realty_link.click()

            # Wait for the property details page to load
            page.wait_for_load_state('networkidle')
            time.sleep(2)

            # Step 4: Extract property status from the page
            self.console.print("[cyan]Extracting property status...[/cyan]")

            # Try multiple selectors to find the status element
            status = None
            status_selectors = [
                '.listing-status',
                '.property-status',
                'span.status',
                'div.status',
                '[class*="status"]',
                '[data-testid*="status"]',
                'span:has-text("Active")',
                'span:has-text("Pending")',
                'span:has-text("Sold")',
                'div:has-text("Status:")',
            ]

            for selector in status_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0 and element.is_visible():
                        text = element.inner_text().strip()
                        # Clean up the text - might be "Status: Active" or just "Active"
                        if text:
                            # Remove "Status:" prefix if present
                            text = text.replace("Status:", "").strip()
                            if text and len(text) > 0:
                                status = text
                                break
                except:
                    continue

            # If we still don't have status, try a more aggressive search in page content
            if not status:
                try:
                    page_content = page.content()
                    # Look for common status indicators in the HTML
                    status_keywords = ['Active', 'Pending', 'Sold', 'Contingent', 'Under Contract', 'Closed']
                    for keyword in status_keywords:
                        if keyword in page_content:
                            # Try to find it as visible text
                            try:
                                element = page.locator(f'text="{keyword}"').first
                                if element.is_visible():
                                    status = keyword
                                    break
                            except:
                                continue
                except:
                    pass

            if not status:
                raise ScrapingError(
                    f"Could not extract property status from Iowa Realty page for address: {address}. "
                    "Website structure may have changed."
                )

            return status

        except PlaywrightTimeout as e:
            raise ScrapingTimeoutError(
                f"Timeout while scraping status for '{address}': {str(e)}"
            )
        except (PropertyNotFoundError, ScrapingTimeoutError):
            # Re-raise our custom exceptions as-is
            raise
        except Exception as e:
            raise ScrapingError(
                f"Failed to scrape status for '{address}': {str(e)}"
            )
