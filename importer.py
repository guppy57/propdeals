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

# Import existing modules
from add_property import (
    add_property_to_supabase,
    get_rental_estimations_singlefamily,
    add_rent_to_supabase_singlefamily
)
from rent_research import RentResearcher

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

    property_details = {
        "full_address": full_address,
        "address1": address1,
        "purchase_price": int(row["Purchase Price"]),
        "beds": int(row["Bedrooms"]),
        "baths": float(row["Bathrooms"]),
        "square_ft": int(row["Square Feet"]),
        "zillow_link": "",  # Empty string per user request
        "built_in": None,  # None per user request
        "listed_date": None,  # None per user request
        "has_reduced_price": False,
        "has_tenants": False,
        "units": 0  # Single family per user request
    }

    return property_details


def import_properties(csv_filepath: str, generate_research: bool = True) -> Dict[str, Any]:
    """
    Import properties from CSV file into Supabase.

    Args:
        csv_filepath: Path to CSV file
        generate_research: Whether to generate AI-powered rent research reports

    Returns:
        Dictionary with import statistics
    """
    # Statistics tracking
    stats = {
        "total": 0,
        "successful": 0,
        "skipped": 0,
        "errors": 0,
        "total_api_cost": 0.0,
        "error_details": []
    }

    try:
        # Load CSV
        df = load_csv(csv_filepath)
        stats["total"] = len(df)

        console.print(f"\n[bold cyan]Starting import of {stats['total']} properties...[/bold cyan]\n")

        # Process each property
        for property_num, (_, row) in enumerate(df.iterrows(), start=1):
            full_address = row["Full Address"]

            console.print(f"Processing property {property_num}")
            console.print(f"[bold]Property {property_num}/{stats['total']}:[/bold] {full_address}")

            try:
                # Check for duplicates
                property_exists = check_if_property_exists(supabase, full_address)

                if not property_exists:
                    # Convert CSV row to property_details format
                    property_details = csv_row_to_property_details(row)

                    # Step 1: Add property to Supabase (with enrichment)
                    console.print("  [cyan]→[/cyan] Adding property with enrichment data...")
                    add_property_to_supabase(property_details, supabase)
                    console.print("  [green]✓[/green] Property added successfully")

                    # Step 2: Get rental estimations
                    console.print("  [cyan]→[/cyan] Generating rent estimates...")
                    unit_configs_w_rent, comparables = get_rental_estimations_singlefamily(property_details)
                    console.print("  [green]✓[/green] Rent estimates generated")

                    # Step 3: Add rent estimates to Supabase
                    console.print("  [cyan]→[/cyan] Saving rent estimates to database...")
                    add_rent_to_supabase_singlefamily(property_details["address1"], unit_configs_w_rent, comparables, supabase)
                    console.print("  [green]✓[/green] Rent estimates saved")
                else:
                    console.print("[yellow]⊘ Property exists - skipping property/rent import[/yellow]")
                    property_details = csv_row_to_property_details(row)

                # Step 4: Generate AI research report (always run, even for existing properties)
                if generate_research:
                    console.print("  [cyan]→[/cyan] Generating AI-powered rent research report...")
                    try:
                        researcher = RentResearcher(supabase, console)

                        # Generate research report
                        report_result = researcher.generate_rent_research(
                            property_details["address1"]
                        )

                        if report_result:
                            console.print("  [green]✓[/green] Research report generated")

                            # Track API cost
                            if "api_cost" in report_result:
                                stats["total_api_cost"] += report_result["api_cost"]

                            # Generate rent estimates from report
                            console.print("  [cyan]→[/cyan] Extracting rent estimates from report...")
                            researcher.generate_rent_estimates_from_report(
                                property_details["address1"]
                            )
                            console.print("  [green]✓[/green] Estimates extracted from research")
                        else:
                            console.print("  [yellow]⚠ Research report generation returned no result[/yellow]")
                    except Exception as e:
                        console.print(f"  [yellow]⚠ Research generation failed: {e}[/yellow]")
                        # Don't fail the entire import if research fails

                if not property_exists:
                    console.print("[bold green]✓ Successfully imported![/bold green]\n")
                    stats["successful"] += 1
                else:
                    console.print("[bold yellow]✓ Research updated for existing property![/bold yellow]\n")
                    stats["skipped"] += 1

            except Exception as e:
                console.print(f"[bold red]✗ Error: {e}[/bold red]\n")
                stats["errors"] += 1
                stats["error_details"].append({
                    "property": full_address,
                    "error": str(e)
                })
                continue

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
    # Configuration
    csv_file = "docs/bulk-test.csv"
    generate_research_reports = True

    try:
        # Display banner
        console.print(Panel.fit(
            "[bold cyan]Property CSV Importer[/bold cyan]\n"
            "Bulk import properties with enrichment & rent research",
            border_style="cyan"
        ))
        console.print()

        # Run import
        stats = import_properties(csv_file, generate_research=generate_research_reports)

        # Display summary
        display_import_summary(stats)

    except KeyboardInterrupt:
        console.print("\n[yellow]Import cancelled by user[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"\n[bold red]Import failed: {e}[/bold red]")
        sys.exit(1)
