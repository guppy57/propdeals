"""
Iowa Realty Property Status Scraper

This module provides web scraping functionality to extract property listing status
from iowarealty.com using Playwright for headless browser automation.
"""

import time
import requests
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PlaywrightTimeout
from rich.console import Console
from supabase import Client
from bs4 import BeautifulSoup


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
        self.iowa_realty_base_url = "https://www.iowarealty.com"
        self.timeout = 30000  # 30 seconds default timeout

    def get_property_status_by_address(self, address: str) -> str:
        """
        Scrape property listing status for a given address from iowarealty.com.

        Tries direct HTTP API calls first for speed, falls back to browser automation if needed.

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
                # Try Bing search approach (less bot detection than Google)
                self.console.print(f"[cyan]Trying Bing search approach...[/cyan]")
                status = self._scrape_with_bing_search(address)
                self.console.print(f"[green]✓ Found status: {status}[/green]")
                return status

            except (PropertyNotFoundError, ScrapingError) as e:
                self.console.print(f"[yellow]⚠ Bing search failed: {str(e)}[/yellow]")

                # Try direct HTTP API approach as fallback
                try:
                    self.console.print(f"[cyan]Trying direct API approach...[/cyan]")
                    status = self._scrape_with_http(address)
                    self.console.print(f"[green]✓ Found status: {status}[/green]")
                    return status
                except (PropertyNotFoundError, ScrapingError) as e2:
                    self.console.print(f"[yellow]⚠ All approaches failed[/yellow]")
                    raise PropertyNotFoundError(
                        f"Could not find property '{address}' on iowarealty.com. "
                        f"Tried: Bing search, Direct API"
                    )

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
            # Launch Firefox browser (less bot detection than Chromium)
            browser = p.firefox.launch(
                headless=True,  # Back to headless for production
                firefox_user_prefs={
                    "dom.webdriver.enabled": False,  # Hide webdriver property
                    "useAutomationExtension": False,
                }
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

                # Listen to network requests and responses to debug autocomplete API
                def log_request(request):
                    if 'address' in request.url.lower() or 'autocomplete' in request.url.lower() or 'suggest' in request.url.lower():
                        self.console.print(f"[dim]  API Request: {request.method} {request.url}[/dim]")

                def log_response(response):
                    if 'autocomplete' in response.url.lower():
                        self.console.print(f"[dim]  API Response: {response.status} - {response.url}[/dim]")
                        try:
                            # Try to log response body
                            body = response.body()
                            if len(body) < 500:
                                self.console.print(f"[dim]  Response body: {body.decode('utf-8')}[/dim]")
                            else:
                                self.console.print(f"[dim]  Response body length: {len(body)} bytes[/dim]")
                        except:
                            pass

                page.on("request", log_request)
                page.on("response", log_response)

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
        1. Navigate to Iowa Realty homepage
        2. Extract street address from full address
        3. Type street address into search box
        4. Wait for autocomplete dropdown
        5. Match and click best dropdown suggestion
        6. Extract property status

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
            # Step 1: Navigate to Iowa Realty homepage
            self.console.print(f"[cyan]Navigating to Iowa Realty homepage...[/cyan]")
            page.goto(self.iowa_realty_base_url, wait_until='domcontentloaded')
            time.sleep(3)  # Give page time to fully load

            # Handle cookie consent if present
            try:
                cookie_buttons = [
                    'button:has-text("Accept")',
                    'button:has-text("Accept All")',
                    'button:has-text("Accept Cookies")',
                    '#onetrust-accept-btn-handler',
                    '.cookie-accept',
                ]
                for selector in cookie_buttons:
                    try:
                        btn = page.locator(selector).first
                        if btn.count() > 0 and btn.is_visible():
                            self.console.print("[dim]  Accepting cookies...[/dim]")
                            btn.click(timeout=5000)
                            time.sleep(1)
                            break
                    except:
                        continue
            except:
                pass

            # Take screenshot of homepage
            page.screenshot(path='debug_iowa_homepage.png')
            self.console.print("[dim]  Screenshot: debug_iowa_homepage.png[/dim]")

            # Step 2: Extract street address from full address
            street_address = self._extract_street_address(address)
            self.console.print(f"[cyan]Using street address: {street_address}[/cyan]")

            # Step 3: Find the main search input on homepage
            search_input = None
            search_selectors = [
                'input[type="text"][placeholder*="Search"]',
                'input[type="text"][placeholder*="search"]',
                'input[type="search"]',
                'input[placeholder*="address"]',
                'input[placeholder*="Address"]',
                'input[placeholder*="city"]',
                'input[type="text"]',  # Homepage has prominent search box
            ]

            for selector in search_selectors:
                try:
                    locator = page.locator(selector).first
                    if locator.count() > 0 and locator.is_visible():
                        search_input = locator
                        self.console.print(f"[dim]  Found search input[/dim]")
                        break
                except:
                    continue

            if not search_input:
                raise ScrapingError("Could not find search input on Iowa Realty homepage")

            # Step 4: Type street address to trigger autocomplete
            self.console.print(f"[cyan]Typing address to trigger autocomplete...[/cyan]")
            search_input.click()
            time.sleep(1)

            # Clear any existing value first
            search_input.fill('')
            time.sleep(0.5)

            # Use press_sequentially() which is designed for autocomplete scenarios
            # This types character-by-character and fires all the appropriate events
            search_input.press_sequentially(street_address, delay=100)

            # Wait for autocomplete to appear
            time.sleep(3)

            # Wait for autocomplete dropdown container to appear
            self.console.print(f"[dim]  Waiting for autocomplete dropdown...[/dim]")

            # Try to wait for dropdown container to be visible
            dropdown_container_selectors = [
                '.autocomplete-results',
                '.dropdown-menu',
                '[role="listbox"]',
                '.suggestions',
                '.addressSuggestion',
            ]

            dropdown_appeared = False
            for selector in dropdown_container_selectors:
                try:
                    page.wait_for_selector(selector, state='visible', timeout=5000)
                    self.console.print(f"[dim]  Dropdown appeared: {selector}[/dim]")
                    dropdown_appeared = True
                    break
                except:
                    continue

            # Give extra time for suggestions to populate
            time.sleep(2)

            # Take screenshot of autocomplete
            page.screenshot(path='debug_iowa_autocomplete.png')
            self.console.print("[dim]  Screenshot: debug_iowa_autocomplete.png[/dim]")

            # Step 5: Find autocomplete dropdown suggestions
            self.console.print(f"[cyan]Looking for autocomplete suggestions...[/cyan]")

            # Try different selectors for dropdown items (more specific first)
            dropdown_selectors = [
                '.autocomplete-results > li',
                '.dropdown-menu > li',
                '[role="listbox"] [role="option"]',
                '.suggestions > li',
                '.addressSuggestion li',
                'ul.addressAutocomplete li',  # More specific
                '.autocomplete-item',
            ]

            suggestions = []
            for selector in dropdown_selectors:
                try:
                    locator = page.locator(selector)
                    count = locator.count()
                    if count > 0 and count < 50:  # Reasonable number of suggestions
                        suggestions = locator.all()
                        self.console.print(f"[dim]  Found {count} suggestions using: {selector}[/dim]")
                        break
                except:
                    continue

            if not suggestions:
                raise PropertyNotFoundError(
                    f"No autocomplete suggestions appeared for '{street_address}'. "
                    f"Property may not be listed on Iowa Realty. Check debug_iowa_autocomplete.png"
                )

            # Step 6: Find and click the best matching suggestion
            self.console.print(f"[cyan]Matching address against suggestions...[/cyan]")
            best_match = self._find_matching_suggestion(suggestions, address)

            if not best_match:
                raise PropertyNotFoundError(
                    f"Could not find matching suggestion for '{address}'"
                )

            # Show which suggestion we're clicking
            try:
                match_text = best_match.inner_text()
                self.console.print(f"[dim]  Clicking suggestion: {match_text}[/dim]")
            except:
                pass

            # Click the matched suggestion
            self.console.print(f"[cyan]Opening property details...[/cyan]")
            best_match.click()

            # Wait for property details page to load
            page.wait_for_load_state('domcontentloaded')
            time.sleep(3)

            # Take screenshot of property page
            page.screenshot(path='debug_iowa_property.png')
            self.console.print("[dim]  Screenshot: debug_iowa_property.png[/dim]")

            # Step 7: Extract property status from the page
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

    def _scrape_with_bing_search(self, address: str) -> str:
        """
        Scrape property status using Bing search (less bot detection than Google).

        Args:
            address: Full property address

        Returns:
            str: Property listing status

        Raises:
            PropertyNotFoundError: If property not found
            ScrapingError: If scraping fails
        """
        with sync_playwright() as p:
            # Launch Chromium browser (Bing works better with Chrome-based browsers)
            browser = p.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-dev-shm-usage']
            )

            try:
                context = browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                )
                context.set_default_timeout(self.timeout)
                page = context.new_page()

                # Navigate to Bing
                self.console.print(f"[cyan]Navigating to Bing...[/cyan]")
                page.goto("https://www.bing.com", wait_until='domcontentloaded')
                time.sleep(3)

                # Take screenshot of Bing homepage
                page.screenshot(path='debug_bing_homepage.png')
                self.console.print(f"[dim]  Screenshot: debug_bing_homepage.png[/dim]")

                # Find Bing search box with more selectors
                search_input = None
                search_selectors = [
                    'input[name="q"]',
                    'input#sb_form_q',
                    'input[aria-label*="search"]',
                    'input[aria-label*="Search"]',
                    'textarea[name="q"]',
                    'input[type="search"]',
                    'input[type="text"]',  # Last resort
                ]

                for selector in search_selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.count() > 0:
                            search_input = locator
                            self.console.print(f"[dim]  Found Bing search box: {selector}[/dim]")
                            break
                    except:
                        continue

                if not search_input:
                    raise ScrapingError("Could not find Bing search box. Check debug_bing_homepage.png")

                # Search for Iowa Realty property
                search_query = f"iowarealty.com {address}"
                self.console.print(f"[cyan]Searching Bing for: {search_query}[/cyan]")

                search_input.click()
                time.sleep(0.5)
                search_input.fill(search_query)
                time.sleep(0.5)

                # Submit search and wait for navigation
                search_input.press("Enter")

                # Wait for search results page to load
                self.console.print(f"[dim]  Waiting for search results...[/dim]")
                try:
                    # Wait for results container to appear
                    page.wait_for_selector('#b_results', timeout=10000)
                    time.sleep(2)
                except:
                    # If results container doesn't appear, wait anyway
                    page.wait_for_load_state('networkidle', timeout=10000)
                    time.sleep(3)

                # Take screenshot for debugging
                page.screenshot(path='debug_bing_results.png')
                self.console.print(f"[dim]  Screenshot: debug_bing_results.png[/dim]")

                # Look for Iowa Realty links in search results
                self.console.print(f"[cyan]Looking for Iowa Realty listing...[/cyan]")

                # Get all links and filter for actual Iowa Realty URLs
                all_links = page.locator('a[href]').all()
                iowa_realty_link = None

                for link in all_links:
                    try:
                        href = link.get_attribute('href')
                        if not href:
                            continue

                        # Skip Bing's internal links (copilot, etc.)
                        if '/copilotsearch' in href or '/search' in href or href.startswith('/'):
                            continue

                        # Look for actual Iowa Realty domain
                        if 'iowarealty.com' in href and ('realestate' in href or 'details' in href):
                            iowa_realty_link = link
                            self.console.print(f"[dim]  Found Iowa Realty link: {href}[/dim]")
                            break

                    except:
                        continue

                if not iowa_realty_link:
                    raise PropertyNotFoundError(
                        f"Property '{address}' not found in Bing search results. "
                        f"No Iowa Realty property links found. Check debug_bing_results.png"
                    )

                # Click the Iowa Realty listing
                self.console.print(f"[cyan]Opening property page...[/cyan]")
                iowa_realty_link.click()

                # Wait for property page to load
                page.wait_for_load_state('domcontentloaded')
                time.sleep(3)

                # Take screenshot of property page
                page.screenshot(path='debug_property_page.png')
                self.console.print(f"[dim]  Screenshot: debug_property_page.png[/dim]")

                # Extract status from the property page using existing method
                self.console.print(f"[cyan]Extracting property status...[/cyan]")

                # Try multiple selectors to find the status element
                status = None
                status_selectors = [
                    '.listing-status',
                    '.property-status',
                    '.status',
                    '#propertyStatus',
                    '.listingStatus',
                    '[class*="status"]',
                    '[class*="Status"]',
                ]

                for selector in status_selectors:
                    try:
                        locator = page.locator(selector).first
                        if locator.count() > 0 and locator.is_visible():
                            status = locator.inner_text().strip()
                            if status:
                                self.console.print(f"[dim]  Found status with selector '{selector}': {status}[/dim]")
                                return status
                    except:
                        continue

                # If no status element found, search page text for status keywords
                page_text = page.content()
                soup = BeautifulSoup(page_text, 'html.parser')
                text = soup.get_text()

                status_keywords = ['Active', 'Pending', 'Sold', 'Contingent', 'Under Contract', 'Off Market']
                for keyword in status_keywords:
                    if keyword in text:
                        self.console.print(f"[dim]  Found status in page text: {keyword}[/dim]")
                        return keyword

                raise ScrapingError("Could not find property status on page")

            finally:
                browser.close()

    def _scrape_with_http(self, address: str) -> str:
        """
        Attempt to scrape property status using direct HTTP requests (no browser).

        This approach is faster and may bypass bot detection that blocks Playwright.

        Args:
            address: Full property address

        Returns:
            str: Property listing status

        Raises:
            PropertyNotFoundError: If property not found
            ScrapingError: If API calls fail
        """
        try:
            # Extract street address for autocomplete search
            street_address = self._extract_street_address(address)
            self.console.print(f"[dim]  Searching for: {street_address}[/dim]")

            # Call Iowa Realty autocomplete API
            autocomplete_url = f"{self.iowa_realty_base_url}/RealEstate/Search/Autocomplete"

            # Set headers to mimic a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Origin': self.iowa_realty_base_url,
                'Referer': f'{self.iowa_realty_base_url}/',
                'Sec-Fetch-Dest': 'empty',
                'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            }

            # Make POST request to autocomplete API
            data = {
                'term': street_address,
                'searchType': 'address'
            }

            self.console.print(f"[dim]  Calling autocomplete API...[/dim]")
            response = requests.post(autocomplete_url, headers=headers, data=data, timeout=10)

            self.console.print(f"[dim]  API Response: {response.status_code}[/dim]")

            if response.status_code == 403:
                raise ScrapingError("API returned 403 Forbidden - bot detection active")

            if response.status_code != 200:
                raise ScrapingError(f"API returned status code {response.status_code}")

            # Parse JSON response
            suggestions = response.json()
            self.console.print(f"[dim]  Found {len(suggestions)} suggestions[/dim]")

            if not suggestions:
                raise PropertyNotFoundError(f"No properties found for '{street_address}'")

            # Find best matching suggestion
            best_match = None
            best_score = 0

            for suggestion in suggestions:
                # Suggestions should have 'label', 'value', or 'address' field
                suggestion_text = suggestion.get('label', '') or suggestion.get('value', '') or suggestion.get('address', '')

                # Calculate match score
                addr_lower = address.lower()
                sugg_lower = suggestion_text.lower()

                score = sum(1 for word in addr_lower.split() if word in sugg_lower)

                if score > best_score:
                    best_score = score
                    best_match = suggestion

            if not best_match:
                raise PropertyNotFoundError(f"No matching property found for '{address}'")

            # Extract property URL from suggestion
            property_url = best_match.get('url') or best_match.get('link') or best_match.get('href')

            if not property_url:
                # If no direct URL, try to construct from ID
                property_id = best_match.get('id') or best_match.get('listingId')
                if property_id:
                    property_url = f"{self.iowa_realty_base_url}/realestate/details/{property_id}"
                else:
                    raise ScrapingError("Could not extract property URL from autocomplete response")

            # Make sure URL is absolute
            if not property_url.startswith('http'):
                property_url = self.iowa_realty_base_url + property_url

            self.console.print(f"[dim]  Property URL: {property_url}[/dim]")

            # Fetch property details page
            self.console.print(f"[cyan]Fetching property details...[/cyan]")
            response = requests.get(property_url, headers=headers, timeout=10)

            if response.status_code != 200:
                raise ScrapingError(f"Failed to fetch property page: {response.status_code}")

            # Parse HTML with BeautifulSoup
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract status using various selectors
            status = self._extract_status_from_html(soup)

            return status

        except requests.RequestException as e:
            raise ScrapingError(f"HTTP request failed: {str(e)}")

    def _extract_status_from_html(self, soup: BeautifulSoup) -> str:
        """
        Extract property status from BeautifulSoup parsed HTML.

        Args:
            soup: BeautifulSoup object of property details page

        Returns:
            str: Property status

        Raises:
            ScrapingError: If status cannot be found
        """
        # Try multiple selectors to find status
        status_selectors = [
            ('class', 'listing-status'),
            ('class', 'property-status'),
            ('class', 'status'),
            ('id', 'propertyStatus'),
            ('class', 'listingStatus'),
        ]

        for selector_type, selector_value in status_selectors:
            if selector_type == 'class':
                elements = soup.find_all(class_=selector_value)
            elif selector_type == 'id':
                element = soup.find(id=selector_value)
                elements = [element] if element else []

            for element in elements:
                if element and element.get_text(strip=True):
                    status = element.get_text(strip=True)
                    self.console.print(f"[dim]  Found status: {status}[/dim]")
                    return status

        # If no status found with selectors, look for status in text
        text = soup.get_text()
        status_keywords = ['Active', 'Pending', 'Sold', 'Contingent', 'Under Contract', 'Off Market']

        for keyword in status_keywords:
            if keyword in text:
                self.console.print(f"[dim]  Found status in text: {keyword}[/dim]")
                return keyword

        raise ScrapingError("Could not find property status on page")

    def _extract_street_address(self, full_address: str) -> str:
        """
        Extract just the street address from a full address.

        Examples:
            "4545 NE Aurora Ave, Des Moines, IA 50317" -> "4545 NE Aurora Ave"
            "123 Main St Apt 4B, Des Moines, IA" -> "123 Main St Apt 4B"
            "456 Oak Ln" -> "456 Oak Ln"

        Args:
            full_address: Full property address with city, state, zip

        Returns:
            str: Just the street address portion

        Raises:
            ValueError: If address is empty or invalid
        """
        if not full_address or not full_address.strip():
            raise ValueError("Address cannot be empty")

        # Split on comma and take first part (street address)
        parts = full_address.split(',')
        street_address = parts[0].strip()

        if not street_address:
            raise ValueError(f"Could not extract street address from: {full_address}")

        return street_address

    def _find_matching_suggestion(self, suggestions: list, full_address: str) -> Optional:
        """
        Find the dropdown suggestion that best matches the full address.

        Compares each suggestion's text against the full address to find the best match.
        If multiple matches, returns the first one. If no good match, returns first suggestion.

        Args:
            suggestions: List of Playwright locator objects for dropdown suggestions
            full_address: Full property address to match against

        Returns:
            Optional: The best matching suggestion locator, or None if list is empty
        """
        if not suggestions:
            return None

        # Normalize full address for comparison
        full_addr_lower = full_address.lower().replace(',', '').replace('.', '')
        addr_components = full_addr_lower.split()

        best_match = None
        best_match_score = 0

        for suggestion in suggestions:
            try:
                # Get the text content of the suggestion
                suggestion_text = suggestion.inner_text().lower().replace(',', '').replace('.', '')
                suggestion_words = suggestion_text.split()

                # Calculate match score (how many address components match)
                match_score = sum(1 for word in addr_components if word in suggestion_words)

                if match_score > best_match_score:
                    best_match_score = match_score
                    best_match = suggestion

            except:
                continue

        # If we found a good match (at least 2 components match), use it
        # Otherwise, fall back to first suggestion
        if best_match_score >= 2 and best_match:
            return best_match
        else:
            return suggestions[0] if suggestions else None

    def _try_direct_url_approach(self, page: Page, address: str) -> str:
        """
        Fallback method: Try to access property by constructing a direct URL.

        This is used when the search functionality isn't available or working.

        Args:
            page: Playwright Page object
            address: Address to search for

        Returns:
            str: Property listing status

        Raises:
            PropertyNotFoundError: If property not found
            ScrapingError: For other failures
        """
        raise ScrapingError(
            "Could not find search input on Iowa Realty website. "
            "Direct URL construction not yet implemented. "
            "Please contact support or try manual search."
        )
