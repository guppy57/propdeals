"""
Test script for Iowa Realty Property Status Scraper

This is a standalone test script that allows you to test the Iowa Realty scraper
without affecting the production database. Run this before using the script in production.

Usage:
    python test_iowa_realty_scraper.py
"""

import os
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from supabase import create_client
from iowa_realty_scraper import (
    IowaRealtyScraper,
    PropertyNotFoundError,
    ScrapingTimeoutError,
    ScrapingError
)

# Load environment variables
load_dotenv()

# Initialize console for output
console = Console()

# Test addresses - mix of different scenarios
TEST_ADDRESSES = [
    # Active listing (from your example)
    "4545 NE Aurora Ave, Des Moines, IA 50317",

    # Add more test addresses here as needed
    # "1234 Main St, Des Moines, IA 50309",  # Another test address
    # "5678 Oak Ave, Des Moines, IA 50310",   # Another test address
]


def run_scraper_tests():
    """
    Run scraper tests on sample addresses.

    Tests the scraper without making any database updates.
    Displays results in a formatted table.
    """
    console.print("\n")
    console.print(Panel(
        "[bold cyan]Iowa Realty Scraper - Test Mode[/bold cyan]\n\n"
        "This test will scrape property status from iowarealty.com\n"
        "WITHOUT updating the database.\n\n"
        f"Testing {len(TEST_ADDRESSES)} properties...",
        title="Test Script",
        border_style="cyan"
    ))
    console.print("\n")

    # Initialize Supabase client (needed for scraper init, but won't be used)
    try:
        supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
    except Exception as e:
        console.print(f"[red]Error initializing Supabase client: {e}[/red]")
        console.print("[yellow]Note: Database connection not needed for testing, but credentials must be valid[/yellow]")
        return

    # Initialize scraper
    scraper = IowaRealtyScraper(supabase_client=supabase, console=console)

    # Track results
    results = []
    total = len(TEST_ADDRESSES)
    success_count = 0
    not_found_count = 0
    error_count = 0

    # Test each address
    for i, address in enumerate(TEST_ADDRESSES, 1):
        console.print(f"\n[bold cyan]Test {i}/{total}[/bold cyan]")
        console.print(f"[cyan]Address: {address}[/cyan]\n")

        try:
            # Attempt to scrape status
            status = scraper.get_property_status_by_address(address)

            results.append({
                'address': address,
                'status': status,
                'result': 'Success',
                'error': None
            })
            success_count += 1

        except PropertyNotFoundError as e:
            results.append({
                'address': address,
                'status': None,
                'result': 'Not Found',
                'error': str(e)
            })
            not_found_count += 1

        except ScrapingTimeoutError as e:
            results.append({
                'address': address,
                'status': None,
                'result': 'Timeout',
                'error': str(e)
            })
            error_count += 1

        except ScrapingError as e:
            results.append({
                'address': address,
                'status': None,
                'result': 'Error',
                'error': str(e)
            })
            error_count += 1

        except Exception as e:
            results.append({
                'address': address,
                'status': None,
                'result': 'Unexpected Error',
                'error': str(e)
            })
            error_count += 1

    # Display results summary
    console.print("\n\n")
    console.print(Panel(
        f"[bold cyan]Test Complete![/bold cyan]\n\n"
        f"Total Tests: {total}\n"
        f"[green]Successful: {success_count}[/green]\n"
        f"[yellow]Not Found: {not_found_count}[/yellow]\n"
        f"[red]Errors: {error_count}[/red]\n"
        f"Success Rate: {(success_count / total * 100):.1f}%",
        title="Summary",
        border_style="cyan"
    ))

    # Display detailed results table
    console.print("\n")
    table = Table(title="Test Results", show_header=True, header_style="bold cyan")
    table.add_column("Address", style="white", width=40)
    table.add_column("Status", style="green", width=15)
    table.add_column("Result", width=15)
    table.add_column("Error", style="red", width=40)

    for result in results:
        result_style = "green" if result['result'] == 'Success' else "yellow" if result['result'] == 'Not Found' else "red"
        table.add_row(
            result['address'],
            result['status'] or "N/A",
            f"[{result_style}]{result['result']}[/{result_style}]",
            result['error'][:40] + "..." if result['error'] and len(result['error']) > 40 else (result['error'] or "")
        )

    console.print(table)

    # Display next steps
    console.print("\n")
    console.print(Panel(
        "[bold cyan]Next Steps:[/bold cyan]\n\n"
        "1. Verify the scraped statuses are correct by checking iowarealty.com manually\n"
        "2. If results look good, you can safely use the script in production\n"
        "3. Add more test addresses to TEST_ADDRESSES list to test edge cases\n"
        "4. Run this test script again after any code changes\n\n"
        "[yellow]Note: No database updates were made during this test[/yellow]",
        title="Testing Complete",
        border_style="green"
    ))


def test_single_address():
    """
    Interactive mode - test a single address of your choice.
    """
    console.print("\n")
    console.print(Panel(
        "[bold cyan]Single Address Test Mode[/bold cyan]\n\n"
        "Enter a property address to test the scraper.",
        title="Interactive Test",
        border_style="cyan"
    ))

    address = console.input("\n[cyan]Enter property address:[/cyan] ")

    if not address or not address.strip():
        console.print("[red]No address provided. Exiting.[/red]")
        return

    console.print("\n")

    # Initialize Supabase client
    try:
        supabase = create_client(
            os.getenv("SUPABASE_URL"),
            os.getenv("SUPABASE_KEY")
        )
    except Exception as e:
        console.print(f"[red]Error initializing Supabase client: {e}[/red]")
        return

    # Initialize scraper
    scraper = IowaRealtyScraper(supabase_client=supabase, console=console)

    try:
        status = scraper.get_property_status_by_address(address)
        console.print(f"\n[bold green]✓ Success![/bold green]")
        console.print(f"[cyan]Address:[/cyan] {address}")
        console.print(f"[cyan]Status:[/cyan] {status}\n")

    except PropertyNotFoundError as e:
        console.print(f"\n[yellow]⚠ Property not found[/yellow]")
        console.print(f"[yellow]{str(e)}[/yellow]\n")

    except ScrapingTimeoutError as e:
        console.print(f"\n[yellow]⏱ Timeout occurred[/yellow]")
        console.print(f"[yellow]{str(e)}[/yellow]\n")

    except ScrapingError as e:
        console.print(f"\n[red]✗ Scraping error[/red]")
        console.print(f"[red]{str(e)}[/red]\n")

    except Exception as e:
        console.print(f"\n[red]✗ Unexpected error[/red]")
        console.print(f"[red]{str(e)}[/red]\n")


def main():
    """
    Main test function - choose test mode.
    """
    console.print("\n")
    console.print("[bold cyan]Iowa Realty Scraper - Test Script[/bold cyan]\n")
    console.print("Choose test mode:")
    console.print("  [1] Run automated tests on predefined addresses")
    console.print("  [2] Test a single address (interactive)")
    console.print("  [q] Quit\n")

    choice = console.input("[cyan]Select option:[/cyan] ").strip().lower()

    if choice == "1":
        run_scraper_tests()
    elif choice == "2":
        test_single_address()
    elif choice == "q":
        console.print("[yellow]Exiting...[/yellow]")
    else:
        console.print("[red]Invalid choice. Exiting.[/red]")


if __name__ == "__main__":
    main()
