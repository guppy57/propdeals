"""
Backfill Rent Research from CSV

This script loads addresses from a CSV file and generates both per-room
and property-wide rent research reports for each property. It provides
interactive confirmations before updating the database.

Usage:
    python backfills/backfill_rent_research_from_csv.py
"""

import os
import pandas as pd
from typing import Dict, List, Any, Optional
import questionary
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv
from supabase import create_client, Client

# Import existing modules
from rent_research import RentResearcher
from run import display_rent_estimates_comparison
from helpers import format_currency

# Load environment variables
load_dotenv()

# Initialize console and supabase
console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


class BackfillStats:
    """Track statistics for the backfill process"""
    def __init__(self):
        self.total_addresses = 0
        self.processed = 0
        self.per_room_reports_generated = 0
        self.per_room_extracted = 0
        self.per_room_updated = 0
        self.property_wide_reports_generated = 0
        self.property_wide_extracted = 0
        self.property_wide_updated = 0
        self.extraction_retries = 0

    def summary(self) -> str:
        return f"""[bold cyan]Backfill Process Summary[/bold cyan]

Total Addresses: {self.total_addresses}
Processed: {self.processed}

Per-Room Research:
  Reports Generated: {self.per_room_reports_generated}
  Estimates Extracted: {self.per_room_extracted}
  Database Updates: {self.per_room_updated}

Property-Wide Research:
  Reports Generated: {self.property_wide_reports_generated}
  Estimates Extracted: {self.property_wide_extracted}
  Database Updates: {self.property_wide_updated}

Extraction Retries: {self.extraction_retries}"""


def load_addresses_from_csv(csv_path: str) -> List[str]:
    """
    Load addresses from CSV file

    Supports CSV with either 'address1' or 'Full Address' column
    """
    try:
        df = pd.read_csv(csv_path)

        # Handle both column name formats
        if "address1" in df.columns:
            addresses = df["address1"].dropna().tolist()
        else:
            # CSV only has addresses as first column (like dsm-max-250k.out.csv)
            addresses = df.iloc[:, 0].dropna().tolist()

        # Filter out empty strings
        addresses = [addr.strip() for addr in addresses if addr and str(addr).strip()]

        return addresses
    except Exception as e:
        console.print(f"[red]Error loading CSV: {str(e)}[/red]")
        raise


def get_property_by_address(address1: str) -> Optional[Dict[str, Any]]:
    """Fetch property data from database by address1"""
    try:
        response = supabase.table('properties').select('*').eq('address1', address1).execute()
        if response.data and len(response.data) > 0:
            return response.data[0]
        return None
    except Exception as e:
        console.print(f"[red]Error fetching property {address1}: {str(e)}[/red]")
        return None


def display_property_wide_comparison(property_id: str, property_data: Dict[str, Any],
                                     new_estimates: Dict[str, Any], result_cost: float) -> bool:
    """
    Display comparison between current and new property-wide rent estimates.

    Returns True if user wants to update database, False otherwise.
    """
    # Create comparison table
    table = Table(
        title=f"Property-Wide Rent Estimate Comparison for {property_id}",
        show_header=True,
        header_style="bold green"
    )
    table.add_column("Field", style="cyan", width=20)
    table.add_column("Current Value", justify="right", style="white", width=15)
    table.add_column("New Value", justify="right", style="green", width=15)
    table.add_column("Difference", justify="right", style="bold", width=15)
    table.add_column("Change %", justify="right", style="bold", width=12)

    # Get current values
    current_estimate = property_data.get('rent_estimate') or 0
    current_high = property_data.get('rent_estimate_high') or 0
    current_low = property_data.get('rent_estimate_low') or 0

    # Get new values
    new_estimate = new_estimates.get('rent_estimate', 0)
    new_high = new_estimates.get('rent_estimate_high', 0)
    new_low = new_estimates.get('rent_estimate_low', 0)

    # Calculate differences and percentages
    def calc_diff(current, new):
        diff = new - current
        pct = ((new - current) / current * 100) if current > 0 else 0
        return diff, pct

    # Primary estimate
    diff_primary, pct_primary = calc_diff(current_estimate, new_estimate)
    diff_color = "green" if diff_primary >= 0 else "red"
    diff_symbol = "+" if diff_primary > 0 else ""
    table.add_row(
        "Primary Estimate",
        format_currency(current_estimate) if current_estimate else "—",
        format_currency(new_estimate),
        f"[{diff_color}]{diff_symbol}${abs(diff_primary):,.0f}[/{diff_color}]",
        f"[{diff_color}]{pct_primary:+.1f}%[/{diff_color}]"
    )

    # High estimate
    diff_high, pct_high = calc_diff(current_high, new_high)
    diff_color_high = "green" if diff_high >= 0 else "red"
    diff_symbol_high = "+" if diff_high > 0 else ""
    table.add_row(
        "High Estimate",
        format_currency(current_high) if current_high else "—",
        format_currency(new_high),
        f"[{diff_color_high}]{diff_symbol_high}${abs(diff_high):,.0f}[/{diff_color_high}]",
        f"[{diff_color_high}]{pct_high:+.1f}%[/{diff_color_high}]"
    )

    # Low estimate
    diff_low, pct_low = calc_diff(current_low, new_low)
    diff_color_low = "green" if diff_low >= 0 else "red"
    diff_symbol_low = "+" if diff_low > 0 else ""
    table.add_row(
        "Low Estimate",
        format_currency(current_low) if current_low else "—",
        format_currency(new_low),
        f"[{diff_color_low}]{diff_symbol_low}${abs(diff_low):,.0f}[/{diff_color_low}]",
        f"[{diff_color_low}]{pct_low:+.1f}%[/{diff_color_low}]"
    )

    console.print("\n")
    console.print(table)
    console.print(f"\n[dim]API Cost: ${result_cost:.4f}[/dim]")

    # Additional property context
    beds = property_data.get('beds', '?')
    baths = property_data.get('baths', '?')
    sqft = property_data.get('square_ft', '?')
    console.print(f"[dim]Property: {beds}bd/{baths}ba, {sqft} sqft[/dim]\n")

    # Ask user for confirmation
    result = questionary.confirm(
        "Update properties table with these new estimates?",
        default=False
    ).ask()

    # Handle user interruption (Ctrl+C)
    if result is None:
        return False

    return result


def update_property_wide_estimates(property_id: str, estimates: Dict[str, Any]) -> bool:
    """Update properties table with new property-wide estimates"""
    try:
        update_data = {
            'rent_estimate': estimates.get('rent_estimate'),
            'rent_estimate_high': estimates.get('rent_estimate_high'),
            'rent_estimate_low': estimates.get('rent_estimate_low'),
        }

        response = supabase.table('properties').update(update_data).eq('address1', property_id).execute()
        return response.data is not None
    except Exception as e:
        console.print(f"[red]Error updating properties table: {str(e)}[/red]")
        return False


def process_property(address1: str, stats: BackfillStats, property_index: int, total_count: int):
    """
    Process a single property: generate reports, extract estimates, update database

    Raises exception on error (per user requirement to stop on first error)
    """
    console.print(f"\n{'='*80}\n")
    console.print(f"[bold cyan]Processing {property_index}/{total_count}: {address1}[/bold cyan]\n")

    # Verify property exists
    property_data = get_property_by_address(address1)
    if not property_data:
        raise Exception(f"Property not found in database: {address1}")

    # Display property summary
    beds = property_data.get('beds', '?')
    baths = property_data.get('baths', '?')
    price = property_data.get('purchase_price', 0)
    units = property_data.get('units', 0)
    is_single_family = units == 0

    console.print(Panel(
        f"Address: {address1}\n"
        f"Price: {format_currency(price)}\n"
        f"Config: {beds}bd/{baths}ba\n"
        f"Type: {'Single Family' if is_single_family else f'{units}-Unit Multifamily'}",
        title=f"Property {property_index}/{total_count}",
        border_style="cyan"
    ))

    # Initialize researcher
    researcher = RentResearcher(supabase, console)

    # ===== PER-ROOM RESEARCH =====
    console.print("\n[bold yellow]Step 1: Per-Room Rent Research[/bold yellow]")

    # Generate per-room research report
    console.print("[cyan]Generating per-room research report...[/cyan]")
    per_room_report_id = researcher.generate_rent_research(address1)

    if not per_room_report_id:
        raise Exception(f"Per-room research report generation failed for {address1}")

    stats.per_room_reports_generated += 1
    console.print("[green]✓ Per-room research report generated[/green]")

    # Extract estimates from per-room report (with retry)
    console.print("[cyan]Extracting per-room estimates from report...[/cyan]")
    per_room_result = researcher.generate_rent_estimates_from_report(per_room_report_id)

    if not per_room_result.get("success"):
        # Retry once
        console.print("[yellow]⚠ Extraction failed, retrying once...[/yellow]")
        stats.extraction_retries += 1
        per_room_result = researcher.generate_rent_estimates_from_report(per_room_report_id)

        if not per_room_result.get("success"):
            error_msg = per_room_result.get('error', 'Unknown error')
            raise Exception(f"Per-room estimate extraction failed after retry: {error_msg}")

    stats.per_room_extracted += 1
    console.print("[green]✓ Per-room estimates extracted[/green]")

    # Display comparison and get user confirmation
    estimates = per_room_result["estimates"]
    existing_estimates = per_room_result.get("existing_estimates", {})
    unit_configs = per_room_result.get("unit_configs", [])

    update_per_room = display_rent_estimates_comparison(
        address1,
        estimates,
        existing_estimates,
        unit_configs,
        per_room_result['cost'],
        f"Generated from new report (ID: {per_room_report_id[:8]})"
    )

    if update_per_room:
        # Update database
        update_success = researcher._update_rent_estimates_in_db(
            address1, unit_configs, estimates
        )

        if not update_success:
            raise Exception(f"Failed to update rent_estimates table for {address1}")

        stats.per_room_updated += 1
        console.print("[green]✅ Rent estimates table updated successfully![/green]")
    else:
        console.print("[yellow]⊘ User declined per-room database update[/yellow]")

    # ===== PROPERTY-WIDE RESEARCH (only for single family) =====
    if is_single_family:
        console.print("\n[bold yellow]Step 2: Property-Wide (Y2) Rent Research[/bold yellow]")

        # Generate property-wide research report
        console.print("[cyan]Generating property-wide research report...[/cyan]")
        pw_report_id = researcher.generate_property_wide_research(address1)

        if not pw_report_id:
            raise Exception(f"Property-wide research report generation failed for {address1}")

        stats.property_wide_reports_generated += 1
        console.print("[green]✓ Property-wide research report generated[/green]")

        # Extract property-wide estimates (with retry)
        console.print("[cyan]Extracting property-wide estimates from report...[/cyan]")
        pw_result = researcher.extract_property_wide_estimates(pw_report_id)

        if not pw_result:
            # Retry once
            console.print("[yellow]⚠ Extraction failed, retrying once...[/yellow]")
            stats.extraction_retries += 1
            pw_result = researcher.extract_property_wide_estimates(pw_report_id)

            if not pw_result:
                raise Exception(f"Property-wide estimate extraction failed after retry")

        stats.property_wide_extracted += 1
        console.print("[green]✓ Property-wide estimates extracted[/green]")

        # Get the cost from the report
        report_data = researcher.get_report_by_id(pw_report_id)
        pw_cost = report_data.get('api_cost', 0) if report_data else 0

        # Display comparison and get user confirmation
        update_property_wide = display_property_wide_comparison(
            address1,
            property_data,
            pw_result,
            pw_cost
        )

        if update_property_wide:
            # Update database
            update_success = update_property_wide_estimates(address1, pw_result)

            if not update_success:
                raise Exception(f"Failed to update properties table for {address1}")

            stats.property_wide_updated += 1
            console.print("[green]✅ Properties table updated successfully![/green]")
        else:
            console.print("[yellow]⊘ User declined property-wide database update[/yellow]")
    else:
        console.print("\n[dim]Skipping property-wide research (not single family)[/dim]")

    stats.processed += 1


def main():
    """Main backfill process"""
    console.print(Panel(
        "[bold green]📊 Rent Research Backfill from CSV[/bold green]\n\n"
        "This script will generate rent research reports for all addresses in a CSV file.\n\n"
        "For each property, it will:\n"
        "• Generate per-room rent research report\n"
        "• Extract and display estimates with confirmation prompt\n"
        "• Generate property-wide (Y2) rent research report (single family only)\n"
        "• Extract and display estimates with confirmation prompt\n\n"
        "[yellow]Note: Process will stop on first error (as configured)[/yellow]",
        title="Backfill Rent Research",
        border_style="green"
    ))

    # Get CSV file path
    csv_path = questionary.text(
        "Enter path to CSV file:",
        default="docs/dsm-max-250k.out.csv"
    ).ask()

    # Handle user interruption (Ctrl+C) or empty input
    if not csv_path:
        console.print("[yellow]No CSV path provided. Exiting.[/yellow]")
        return

    # Check if file exists
    if not os.path.exists(csv_path):
        console.print(f"[red]Error: File not found: {csv_path}[/red]")
        return

    # Load addresses from CSV
    console.print(f"\n[cyan]Loading addresses from {csv_path}...[/cyan]")
    try:
        addresses = load_addresses_from_csv(csv_path)
    except Exception as e:
        console.print(f"[red]Failed to load CSV: {str(e)}[/red]")
        return

    if not addresses:
        console.print("[red]No addresses found in CSV file.[/red]")
        return

    console.print(f"[green]Found {len(addresses)} addresses to process.[/green]")

    # Show first few addresses as preview
    console.print("\n[cyan]Preview of addresses:[/cyan]")
    for i, addr in enumerate(addresses[:5], 1):
        console.print(f"  {i}. {addr}")
    if len(addresses) > 5:
        console.print(f"  ... and {len(addresses) - 5} more")

    # Confirm to proceed
    proceed = questionary.confirm(
        f"\nProceed with backfill for {len(addresses)} properties?",
        default=True
    ).ask()

    # Handle user interruption (Ctrl+C) or declined
    if not proceed:
        console.print("[yellow]Backfill process cancelled.[/yellow]")
        return

    # Initialize stats
    stats = BackfillStats()
    stats.total_addresses = len(addresses)

    # Process each address
    try:
        for i, address1 in enumerate(addresses, 1):
            process_property(address1, stats, i, len(addresses))

    except Exception as e:
        console.print(f"\n[bold red]❌ Error occurred: {str(e)}[/bold red]")
        console.print("[yellow]Stopping process as configured (stop on first error).[/yellow]")

    # Final summary
    console.print("\n" + "="*80 + "\n")
    console.print(Panel(stats.summary(), title="Backfill Complete", border_style="green"))


if __name__ == "__main__":
    main()
