"""
Neighborhood Scraper for Des Moines City Neighborhood Finder

This module provides web scraping functionality to extract neighborhood names
from the Des Moines city website using Playwright for headless browser automation.
"""

from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from rich.console import Console
from supabase import Client


# Custom Exceptions
class NeighborhoodScraperError(Exception):
    """Base exception for all neighborhood scraper errors"""
    pass


class NeighborhoodNotFoundError(NeighborhoodScraperError):
    """Raised when address is not a valid Des Moines address"""
    pass


class ScrapingTimeoutError(NeighborhoodScraperError):
    """Raised when scraping operation times out"""
    pass


class ScrapingError(NeighborhoodScraperError):
    """Raised for general scraping failures (network, parsing, etc.)"""
    pass


class NeighborhoodScraper:
    """
    Scrapes neighborhood information from Des Moines city neighborhood finder.

    Uses Playwright for headless browser automation to retrieve neighborhood
    names for Des Moines addresses from https://findneighborhoods.dsm.city/
    """

    def __init__(self, supabase_client: Client, console: Console):
        """
        Initialize the neighborhood scraper.

        Args:
            supabase_client: Supabase client for database operations
            console: Rich console for user feedback
        """
        self.supabase = supabase_client
        self.console = console
        self.target_url = "https://findneighborhoods.dsm.city/"
        self.timeout = 30000  # 30 seconds default timeout

    def get_neighborhood_by_address(self, address: str) -> str:
        """
        Scrape neighborhood name for a given Des Moines address.

        This method uses Playwright to automate the neighborhood search website.
        It does NOT cache results - every call performs a fresh scrape.

        Args:
            address: Full Des Moines address (e.g., "1234 Main St, Des Moines, IA")

        Returns:
            str: Neighborhood name

        Raises:
            ValueError: If address is empty/invalid format
            NeighborhoodNotFoundError: If address is not a valid Des Moines address
            ScrapingTimeoutError: If page load or element wait times out
            ScrapingError: For other scraping failures (network, element not found, etc.)

        Example:
            >>> scraper = NeighborhoodScraper(supabase_client, console)
            >>> neighborhood = scraper.get_neighborhood_by_address("400 Robert D Ray Dr, Des Moines, IA")
            >>> print(neighborhood)
            'Downtown'
        """
        # Input validation
        if not address or not address.strip():
            raise ValueError("Address cannot be empty")

        address = address.strip()

        # Show progress with Rich console
        with self.console.status(
            f"[bold cyan]Scraping neighborhood for: {address}...",
            spinner="dots"
        ):
            try:
                neighborhood = self._scrape_with_browser(address)
                self.console.print(f"[green]✓ Found neighborhood: {neighborhood}[/green]")
                return neighborhood

            except NeighborhoodNotFoundError as e:
                self.console.print(f"[red]✗ {str(e)}[/red]")
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
            str: Neighborhood name

        Raises:
            NeighborhoodNotFoundError: If address not valid in Des Moines
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
        Execute the scraping workflow on the neighborhood finder page.

        Steps:
        1. Navigate to URL
        2. Wait for page to be fully loaded
        3. Locate and fill address input field
        4. Click search button
        5. Wait for results or error message
        6. Extract neighborhood name
        7. Handle error states

        Args:
            page: Playwright Page object
            address: Address to search for

        Returns:
            str: Neighborhood name

        Raises:
            NeighborhoodNotFoundError: If address not valid
            ScrapingTimeoutError: If timeout occurs
            ScrapingError: For other failures
        """
        try:
            # Step 1: Navigate to the neighborhood finder
            self.console.print(f"[cyan]Navigating to {self.target_url}...[/cyan]")
            page.goto(self.target_url, wait_until='networkidle')

            # Step 2: Wait for critical page elements to load
            page.wait_for_load_state('domcontentloaded')

            # Step 3: Find and fill the address input field
            # Strategy: Try multiple selectors (ID, placeholder text, CSS)
            self.console.print(f"[cyan]Entering address: {address}[/cyan]")

            # Try multiple selector strategies for robustness
            address_input = None
            input_selectors = [
                'input[type="text"]',
                'input[placeholder*="address" i]',
                'input[placeholder*="Address" i]',
                '#addressInput',
                '.address-input',
                'input[name*="address" i]'
            ]

            for selector in input_selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0:
                        address_input = locator
                        break
                except:
                    continue

            if not address_input:
                raise ScrapingError("Could not find address input field on page")

            address_input.fill(address)

            # Step 4: Click the search button
            # Strategy: Look for button with "Search" text or specific ID
            self.console.print("[cyan]Clicking search...[/cyan]")

            search_button = None
            button_selectors = [
                'button:has-text("Search")',
                'input[type="submit"]',
                'button[type="submit"]',
                '#searchButton',
                '.search-button',
                'button:has-text("search")'  # lowercase variant
            ]

            for selector in button_selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0:
                        search_button = locator
                        break
                except:
                    continue

            if not search_button:
                raise ScrapingError("Could not find search button on page")

            search_button.click()

            # Step 5: Wait for results OR error message
            # This is critical - need to wait for EITHER outcome
            self.console.print("[cyan]Waiting for results...[/cyan]")

            # Wait a bit for the page to process
            page.wait_for_timeout(2000)  # 2 second buffer for dynamic content

            # Step 6: Check for error state first
            # Check if the error div is visible
            error_div = page.locator('#AddrSearchError')
            if error_div.count() > 0 and error_div.is_visible():
                # Try to get the error message text
                try:
                    error_text = page.locator('#preSearchInfo').inner_text()
                    raise NeighborhoodNotFoundError(
                        f"Address '{address}' is not valid: {error_text}"
                    )
                except NeighborhoodNotFoundError:
                    raise
                except:
                    # Generic error if we can't get the text
                    raise NeighborhoodNotFoundError(
                        f"Address '{address}' is not a valid Des Moines address"
                    )

            # Also check for common error phrases in the page text
            error_phrases = [
                "Invalid Des Moines address",
                "Unable to get details at this time",
                "invalid address"
            ]

            for error_phrase in error_phrases:
                try:
                    error_element = page.locator(f'text="{error_phrase}"')
                    if error_element.count() > 0 and error_element.first.is_visible():
                        raise NeighborhoodNotFoundError(
                            f"Address '{address}' is not a valid Des Moines address"
                        )
                except NeighborhoodNotFoundError:
                    raise
                except:
                    continue

            # Step 7: Extract neighborhood name from results
            # Try multiple possible selectors for neighborhood display
            # Based on actual page structure: #hoodBody contains the neighborhood name in a table
            neighborhood_selectors = [
                '#hoodBody td',  # Primary: table cell with neighborhood name
                '#attributesResultHead h2 strong',  # Secondary: details header
                '#Attributes h2 strong',  # Alternative details header
                'div#attributesResultHead strong',  # Fallback
                '#resultsHoodWrapper h2 strong'  # Another fallback
            ]

            neighborhood = None
            for selector in neighborhood_selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0 and element.is_visible():
                        text = element.inner_text().strip()
                        if text and len(text) > 0:
                            neighborhood = text
                            break
                except:
                    continue

            if not neighborhood:
                # Try getting any visible text from the page that might be the neighborhood
                # This is a last resort fallback
                try:
                    # Look for any heading or bold text that appeared after search
                    page_content = page.content()
                    if 'neighborhood' in page_content.lower():
                        # Page has results, but we couldn't extract the name
                        raise ScrapingError(
                            "Found results but could not extract neighborhood name. Website structure may have changed."
                        )
                except:
                    pass

                raise ScrapingError(
                    f"Could not extract neighborhood name from results page for address: {address}"
                )

            return neighborhood

        except PlaywrightTimeout as e:
            raise ScrapingTimeoutError(
                f"Timeout while scraping neighborhood for '{address}': {str(e)}"
            )
        except (NeighborhoodNotFoundError, ScrapingTimeoutError):
            # Re-raise our custom exceptions as-is
            raise
        except Exception as e:
            raise ScrapingError(
                f"Failed to scrape neighborhood for '{address}': {str(e)}"
            )
