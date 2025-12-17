"""
Property CSV Importer
Bulk imports properties from CSV files into Supabase with automatic enrichment and rent research.
"""

import os
import sys
import pandas as pd
from typing import Dict, Any
from dotenv import load_dotenv
from supabase import create_client, Client
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from handlers import handle_scrape_neighborhood_from_findneighborhoods, handle_rent_research_after_add
from neighborhood_scraper import NeighborhoodScraper
from add_property import (
    add_property_to_supabase,
    get_rental_estimations_singlefamily,
    add_rent_to_supabase_singlefamily
)
from run import (
    load_assumptions,
    load_loan,
    reload_dataframe,
    get_combined_phase1_qualifiers
)

# Initialize
load_dotenv()
console = Console()

# Initialize Supabase client
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_KEY")
)


def load_csv(filepath: str) -> pd.DataFrame:
    """
    Load and validate CSV file.

    Args:
        filepath: Path to CSV file

    Returns:
        DataFrame with property data

    Raises:
        FileNotFoundError: If CSV file doesn't exist
        ValueError: If CSV is missing required columns
    """
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    df = pd.read_csv(filepath)

    # Validate required columns
    required_columns = ["Full Address", "Purchase Price", "Bedrooms", "Bathrooms", "Square Feet"]
    missing_columns = [col for col in required_columns if col not in df.columns]

    if missing_columns:
        raise ValueError(f"CSV is missing required columns: {missing_columns}")

    # Remove empty rows
    df = df.dropna(subset=["Full Address"])

    console.print(f"[green]✓[/green] Loaded {len(df)} properties from CSV")
    return df


def check_if_property_exists(supabase: Client, address: str) -> bool:
    """
    Check if a property already exists in the database.

    Args:
        supabase: Supabase client
        address: Full address string

    Returns:
        True if property exists, False otherwise
    """
    try:
        # Extract street address (address1) from full address
        # Format: "4212 Valley Cir, Des Moines, IA 50317" -> "4212 Valley Cir"
        address1 = address.split(",")[0].strip()

        response = supabase.table("properties").select("address1").eq("address1", address1).execute()
        return len(response.data) > 0
    except Exception as e:
        console.print(f"[yellow]Warning: Could not check for duplicate: {e}[/yellow]")
        return False


def csv_row_to_property_details(row: pd.Series) -> Dict[str, Any]:
    """
    Convert a CSV row to property_details dict format.

    Args:
        row: Pandas Series representing a CSV row

    Returns:
        Dictionary in property_details format
    """
    full_address = row["Full Address"]
    # Extract street address from full address
    address1 = full_address.split(",")[0].strip()

    has_reduced_price = True if row['Has Had Price Reductions'] == "Yes" else False

    property_details = {
        "full_address": full_address,
        "address1": address1,
        "purchase_price": int(row["Purchase Price"]),
        "beds": int(row["Bedrooms"]),
        "baths": float(row["Bathrooms"]),
        "square_ft": int(row["Square Feet"]),
        "zillow_link": "",  # Empty string per user request
        "built_in": int(row["Built In"]),  # None per user request
        "listed_date": None,  # None per user request
        "has_reduced_price": has_reduced_price,
        "has_tenants": False,
        "units": 0  # Single family per user request
    }

    return property_details


def generate_output_csv_path(input_filepath: str) -> str:
    """
    Generate output CSV filename from input CSV filename.
    Example: "docs/dsm-250-to-300k.csv" -> "docs/dsm-250-to-300k.out.csv"

    Args:
        input_filepath: Path to input CSV file

    Returns:
        Path to output CSV file
    """
    if input_filepath.endswith('.csv'):
        return input_filepath[:-4] + '.out.csv'
    else:
        return input_filepath + '.out.csv'


def write_qualifying_addresses_to_csv(addresses: list, output_filepath: str):
    """
    Write qualifying addresses to output CSV file.

    Args:
        addresses: List of address1 strings
        output_filepath: Path to output CSV file

    Returns:
        None
    """
    try:
        with open(output_filepath, 'w', newline='') as csvfile:
            csvfile.write("address1\n")
            for address in addresses:
                csvfile.write(f"{address}\n")
        console.print(f"[green]✓[/green] Wrote {len(addresses)} qualifying addresses to {output_filepath}")
    except Exception as e:
        console.print(f"[red]✗ Error writing output CSV: {e}[/red]")


def import_properties(csv_filepath: str) -> Dict[str, Any]:
    """
    Import properties from CSV file into Supabase.

    Args:
        csv_filepath: Path to CSV file

    Returns:
        Dictionary with import statistics
    """
    # Statistics tracking
    stats = {
        "total": 0,
        "successful": 0,
        "skipped": 0,
        "errors": 0,
        "phase1_qualified": 0,
        "total_api_cost": 0.0,
        "error_details": []
    }

    # Track all imported addresses for Phase 1 qualification checking
    imported_addresses = []

    try:
        # Load CSV
        df = load_csv(csv_filepath)
        stats["total"] = len(df)

        console.print(f"\n[bold cyan]Starting import of {stats['total']} properties...[/bold cyan]\n")

        # Process each property
        for property_num, (_, row) in enumerate(df.iterrows(), start=1):
            full_address = row["Full Address"]

            console.print(f"[bold]Property {property_num}/{stats['total']}:[/bold] {full_address}")

            try:
                # Convert CSV row to property_details format
                property_details = csv_row_to_property_details(row)

                # Check for duplicates
                property_exists = check_if_property_exists(supabase, full_address)

                if not property_exists:
                    console.print("  [cyan]→[/cyan] Adding property with enrichment data...")
                    add_property_to_supabase(property_details, supabase)
                    console.print("  [green]✓[/green] Property added successfully")

                    console.print("  [cyan]→[/cyan] Find neighborhood for property...")
                    scraper = NeighborhoodScraper(supabase, console)
                    handle_scrape_neighborhood_from_findneighborhoods(property_details['address1'], supabase, console, scraper, ask_user=False)
                    console.print("  [green]✓[/green] Neighborhood added successfully")

                    console.print("  [cyan]→[/cyan] Generating rent estimates...")
                    unit_configs_w_rent, comparables, property_rent = get_rental_estimations_singlefamily(property_details)
                    console.print("  [green]✓[/green] Rent estimates generated")

                    console.print("  [cyan]→[/cyan] Saving rent estimates to database...")
                    add_rent_to_supabase_singlefamily(property_details["address1"], unit_configs_w_rent, comparables, property_rent, supabase)
                    console.print("  [green]✓[/green] Rent estimates saved")

                    console.print("  [cyan]→[/cyan] Conducting rent research for property...")
                    handle_rent_research_after_add(property_details['address1'], supabase, console, ask_user=False)
                    console.print("  [green]✓[/green] Rent research completed successfully")

                    console.print("[bold green]✓ Successfully imported![/bold green]\n")
                    stats["successful"] += 1
                else:
                    console.print("[yellow]⊘ Property exists - skipping property/rent import[/yellow]")
                    console.print("[bold yellow]⊘ Property already exists - skipped[/bold yellow]\n")
                    stats["skipped"] += 1

                # Track address for Phase 1 qualification checking
                imported_addresses.append(property_details["address1"])

            except Exception as e:
                console.print(f"[bold red]✗ Error: {e}[/bold red]\n")
                stats["errors"] += 1
                stats["error_details"].append({
                    "property": full_address,
                    "error": str(e)
                })
                continue

        # Phase 1 Qualification Checking
        console.print(f"\n[bold cyan]Checking Phase 1 qualifications for imported properties...[/bold cyan]\n")

        if imported_addresses:
            try:
                # Initialize run.py data (assumptions, loan, and property dataframe)
                console.print("  [cyan]→[/cyan] Loading assumptions and loan data...")
                load_assumptions()
                load_loan(1)  # Load default loan (ID 1)

                # Reload dataframe to get all properties with calculated metrics
                console.print("  [cyan]→[/cyan] Reloading property data with Phase 1 metrics...")
                reload_dataframe()

                # Get Phase 1 qualifying properties
                console.print("  [cyan]→[/cyan] Fetching Phase 1 qualifiers...")
                phase1_df = get_combined_phase1_qualifiers()
                qualifying_addresses = phase1_df["address1"].tolist()

                # Find intersection: addresses that were imported AND qualify for Phase 1
                phase1_qualified_addresses = [addr for addr in imported_addresses if addr in qualifying_addresses]
                stats["phase1_qualified"] = len(phase1_qualified_addresses)

                console.print(f"  [green]✓[/green] Found {stats['phase1_qualified']} Phase 1 qualifiers from imported properties")

                # Write qualifying addresses to output CSV
                if phase1_qualified_addresses:
                    output_csv_path = generate_output_csv_path(csv_filepath)
                    console.print(f"  [cyan]→[/cyan] Writing qualifiers to {output_csv_path}...")
                    write_qualifying_addresses_to_csv(phase1_qualified_addresses, output_csv_path)
                else:
                    console.print("  [yellow]No properties qualified for Phase 1[/yellow]")

            except Exception as e:
                console.print(f"  [red]✗ Error during Phase 1 checking: {e}[/red]")
                console.print("  [yellow]Continuing with import summary...[/yellow]")
        else:
            console.print("  [yellow]No addresses to check (all imports failed)[/yellow]")

        return stats

    except Exception as e:
        console.print(f"[bold red]Fatal error during import: {e}[/bold red]")
        raise


def display_import_summary(stats: Dict[str, Any]):
    """
    Display import statistics and summary.

    Args:
        stats: Dictionary with import statistics
    """
    console.print("\n")
    console.print("[bold cyan]═" * 60 + "[/bold cyan]")
    console.print("[bold cyan]IMPORT SUMMARY[/bold cyan]")
    console.print("[bold cyan]═" * 60 + "[/bold cyan]")

    # Create summary table
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total properties in CSV", str(stats["total"]))
    table.add_row("Successfully imported", f"[green]{stats['successful']}[/green]")
    table.add_row("Skipped (duplicates)", f"[yellow]{stats['skipped']}[/yellow]")
    table.add_row("Errors", f"[red]{stats['errors']}[/red]")
    table.add_row("Phase 1 Qualifiers", f"[bold green]{stats['phase1_qualified']}[/bold green]")

    if stats["total_api_cost"] > 0:
        table.add_row("Total API cost (research)", f"${stats['total_api_cost']:.2f}")

    console.print(table)

    # Display error details if any
    if stats["error_details"]:
        console.print("\n[bold red]Error Details:[/bold red]")
        for error in stats["error_details"]:
            console.print(f"  • {error['property']}")
            console.print(f"    [red]{error['error']}[/red]")

    console.print("\n[bold cyan]═" * 60 + "[/bold cyan]\n")


if __name__ == "__main__":
    csv_file = "docs/new-properties.csv"

    try:
        console.print(Panel.fit(
            "[bold cyan]Property CSV Importer[/bold cyan]\n"
            "Bulk import properties with enrichment & rent estimates",
            border_style="cyan"
        ))
        console.print()

        stats = import_properties(csv_file)
        display_import_summary(stats)

    except KeyboardInterrupt:
        console.print("\n[yellow]Import cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Import failed: {e}[/bold red]")
        sys.exit(1)
