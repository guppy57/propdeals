"""
Backfill Neighborhood Analysis Script

This script generates neighborhood analyses for all Phase 1 qualifying properties
that don't already have analyses, then batch extracts letter grades for all reports.

Workflow:
1. Get all Phase 1 qualifier properties
2. For each property, check if it has a neighborhood linked
3. If it does, check if there is a neighborhood analysis
4. If there isn't one, create a new neighborhood analysis
5. At the end, use batch extraction for letter grades on all neighborhood reports
"""

import os
from typing import Dict, List
from dotenv import load_dotenv
from supabase import create_client
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import pandas as pd

from run import load_assumptions, load_loan, reload_dataframe, get_combined_phase1_qualifiers
from neighborhoods import NeighborhoodsClient

load_dotenv()
console = Console()


def display_summary(
    summary: Dict,
    properties_without_hoods: pd.DataFrame,
    failed_reports: List[Dict]
):
    """Display comprehensive summary of backfill operation"""

    # Main statistics panel
    console.print("\n")
    stats_panel = Panel(
        f"[bold cyan]Phase 1 Properties Summary[/bold cyan]\n"
        f"Total Phase 1 Properties: {summary['total_phase1_properties']}\n"
        f"Properties with Neighborhoods: {summary['properties_with_neighborhoods']}\n"
        f"Properties without Neighborhoods: {summary['properties_without_neighborhoods']}\n\n"
        f"[bold green]Neighborhood Analysis Summary[/bold green]\n"
        f"Unique Neighborhoods: {summary['unique_neighborhoods']}\n"
        f"Already Had Analysis: {summary['neighborhoods_with_existing_analysis']}\n"
        f"Newly Generated: {summary['neighborhoods_generated']}\n"
        f"Failed: {summary['neighborhoods_failed']}\n\n"
        f"[bold yellow]Letter Grade Extraction[/bold yellow]\n"
        f"Successfully Extracted: {summary['letter_grades_extracted']}\n\n"
        f"[bold magenta]Cost Summary[/bold magenta]\n"
        f"Generation Cost: ${summary['total_generation_cost']:.4f}\n"
        f"Extraction Cost: ${summary['total_extraction_cost']:.4f}\n"
        f"Total Cost: ${summary['total_cost']:.4f}",
        title="Backfill Summary",
        border_style="green"
    )
    console.print(stats_panel)

    # Properties without neighborhoods table
    if len(properties_without_hoods) > 0:
        console.print("\n[bold yellow]⚠️  Properties Without Assigned Neighborhoods:[/bold yellow]\n")
        no_hood_table = Table(show_header=True, header_style="bold yellow")
        no_hood_table.add_column("Address", style="cyan", width=40)
        no_hood_table.add_column("Qualification", style="magenta", width=15)
        no_hood_table.add_column("Beds/Baths", justify="center", width=12)

        for _, prop in properties_without_hoods.iterrows():
            no_hood_table.add_row(
                prop['address1'],
                prop.get('qualification_type', 'N/A'),
                f"{prop.get('beds', 0)}/{prop.get('baths', 0)}"
            )

        console.print(no_hood_table)
        console.print("\n[yellow]These properties were skipped. Assign neighborhoods manually and re-run.[/yellow]\n")

    # Failed reports table
    if failed_reports:
        console.print("\n[bold red]❌ Failed Neighborhood Analyses:[/bold red]\n")
        failed_table = Table(show_header=True, header_style="bold red")
        failed_table.add_column("Neighborhood", style="cyan", width=30)
        failed_table.add_column("Address", style="yellow", width=35)
        failed_table.add_column("Error", style="red", width=40)

        for failure in failed_reports:
            failed_table.add_row(
                failure['neighborhood'],
                failure['address1'],
                failure['error'][:40] + "..." if len(failure['error']) > 40 else failure['error']
            )

        console.print(failed_table)


def backfill_neighborhood_analyses() -> Dict:
    """
    Main backfill function that processes all Phase 1 qualifying properties.

    Returns:
        Dict with summary statistics
    """
    # Step 1: Initialize and Load Phase 1 Properties
    console.print("\n[bold cyan]🔄 Step 1: Loading Phase 1 qualifying properties...[/bold cyan]")

    supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
    neighborhoods_client = NeighborhoodsClient(supabase, console)

    # Load calculation engine
    load_assumptions()
    load_loan(1)
    reload_dataframe()

    # Get all Phase 1 qualifiers
    phase1_df = get_combined_phase1_qualifiers(active=True)
    total_properties = len(phase1_df)
    console.print(f"[green]✓ Found {total_properties} Phase 1 qualifying properties[/green]\n")

    # Step 2: Identify properties with and without neighborhoods
    console.print("[bold cyan]🔄 Step 2: Checking neighborhood assignments...[/bold cyan]")

    # Ensure 'neighborhood' column exists (reload_dataframe already loads this)
    if 'neighborhood' not in phase1_df.columns:
        console.print("[yellow]⚠ No 'neighborhood' column in Phase 1 data - adding empty column...[/yellow]")
        phase1_df['neighborhood'] = None

    # Separate properties with and without neighborhoods
    properties_with_hoods = phase1_df[phase1_df['neighborhood'].notna()].copy()
    properties_without_hoods = phase1_df[phase1_df['neighborhood'].isna()].copy()

    console.print(f"[green]✓ Properties with neighborhoods: {len(properties_with_hoods)}[/green]")
    console.print(f"[yellow]⚠ Properties without neighborhoods: {len(properties_without_hoods)}[/yellow]\n")

    # Step 3: Get Unique Neighborhoods and Check for Existing Analyses
    console.print("[bold cyan]🔄 Step 3: Checking for existing neighborhood analyses...[/bold cyan]")

    unique_neighborhoods = properties_with_hoods['neighborhood'].unique().tolist()
    console.print(f"[cyan]Found {len(unique_neighborhoods)} unique neighborhoods[/cyan]")

    # Batch check which neighborhoods already have analyses
    existing_analyses = neighborhoods_client.has_neighborhood_analysis_batch(unique_neighborhoods)

    # Filter to neighborhoods needing analysis
    neighborhoods_needing_analysis = [
        neighborhood for neighborhood in unique_neighborhoods
        if not existing_analyses.get(neighborhood, False)
    ]

    already_analyzed = sum(existing_analyses.values())
    console.print(f"[green]✓ Already have analysis: {already_analyzed}[/green]")
    console.print(f"[yellow]⚠ Need new analysis: {len(neighborhoods_needing_analysis)}[/yellow]\n")

    # Step 4: Generate Missing Neighborhood Analyses
    generated_reports = []
    failed_reports = []
    total_generation_cost = 0.0

    if len(neighborhoods_needing_analysis) > 0:
        console.print(f"[bold cyan]🔄 Step 4: Generating {len(neighborhoods_needing_analysis)} neighborhood analyses...[/bold cyan]\n")

        # For each neighborhood needing analysis, pick one property as representative
        neighborhoods_to_generate = {}
        for neighborhood in neighborhoods_needing_analysis:
            # Get first property in this neighborhood
            first_property = properties_with_hoods[
                properties_with_hoods['neighborhood'] == neighborhood
            ].iloc[0]
            neighborhoods_to_generate[neighborhood] = first_property['address1']

        # Generate analyses with progress tracking
        for i, (neighborhood, address1) in enumerate(neighborhoods_to_generate.items(), 1):
            console.print(f"[cyan][{i}/{len(neighborhoods_to_generate)}] Processing {neighborhood}...[/cyan]")

            try:
                report_id, was_existing = neighborhoods_client.generate_neighborhood_research(address1)

                if report_id and not was_existing:
                    # Fetch the report to get cost information
                    report_data = neighborhoods_client.get_report_by_id(report_id)
                    if report_data and 'api_cost' in report_data:
                        total_generation_cost += float(report_data['api_cost'])

                    generated_reports.append({
                        'neighborhood': neighborhood,
                        'report_id': report_id,
                        'address1': address1
                    })
                    console.print(f"[green]  ✓ Generated report for {neighborhood}[/green]\n")
                elif was_existing:
                    # Shouldn't happen if batch check worked, but handle it
                    console.print(f"[yellow]  ⚠ Report already exists for {neighborhood}[/yellow]\n")

            except Exception as e:
                failed_reports.append({
                    'neighborhood': neighborhood,
                    'address1': address1,
                    'error': str(e)
                })
                console.print(f"[red]  ✗ Failed: {str(e)[:50]}...[/red]\n")

        console.print(f"[green]✓ Successfully generated {len(generated_reports)} new analyses[/green]")
        if failed_reports:
            console.print(f"[red]✗ Failed to generate {len(failed_reports)} analyses[/red]\n")
    else:
        console.print("[green]✓ Step 4: All neighborhoods already have analyses, skipping generation...[/green]\n")

    # Step 5: Batch Extract Letter Grades
    console.print("[bold cyan]🔄 Step 5: Batch extracting letter grades for all neighborhood reports...[/bold cyan]\n")

    # Get all report IDs (both existing and newly generated)
    all_report_ids = []

    # Get existing report IDs
    for neighborhood in unique_neighborhoods:
        if existing_analyses.get(neighborhood):
            # Query to get report_id
            report = supabase.table("research_reports")\
                .select("id")\
                .eq("research_type", f"{neighborhood}_neighborhood_report")\
                .eq("status", "completed")\
                .limit(1)\
                .execute()
            if report.data:
                all_report_ids.append(report.data[0]['id'])

    # Add newly generated report IDs
    all_report_ids.extend([r['report_id'] for r in generated_reports])

    # Debug: Show what we're processing
    console.print(f"[cyan]Found {len(all_report_ids)} report IDs to process[/cyan]")
    if all_report_ids:
        console.print(f"[cyan]Sample report IDs: {all_report_ids[:3]}[/cyan]\n")

    # Batch extract letter grades for all reports
    if all_report_ids:
        extraction_results = neighborhoods_client.extract_neighborhood_grades_batch(all_report_ids)
    else:
        extraction_results = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'total_cost': 0.0
        }

    # Step 6: Display Comprehensive Summary
    console.print("\n[bold cyan]📊 Step 6: Generating summary...[/bold cyan]")

    summary = {
        'total_phase1_properties': total_properties,
        'properties_with_neighborhoods': len(properties_with_hoods),
        'properties_without_neighborhoods': len(properties_without_hoods),
        'unique_neighborhoods': len(unique_neighborhoods),
        'neighborhoods_with_existing_analysis': already_analyzed,
        'neighborhoods_generated': len(generated_reports),
        'neighborhoods_failed': len(failed_reports),
        'letter_grades_extracted': extraction_results['successful'],
        'total_generation_cost': total_generation_cost,
        'total_extraction_cost': extraction_results['total_cost'],
        'total_cost': total_generation_cost + extraction_results['total_cost']
    }

    display_summary(summary, properties_without_hoods, failed_reports)

    return summary


if __name__ == "__main__":
    console.print("\n[bold cyan]╔════════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║  Neighborhood Analysis Backfill Script            ║[/bold cyan]")
    console.print("[bold cyan]╚════════════════════════════════════════════════════╝[/bold cyan]\n")

    try:
        results = backfill_neighborhood_analyses()
        console.print("\n[bold green]✅ Backfill completed successfully![/bold green]\n")
    except Exception as e:
        console.print(f"\n[bold red]❌ Backfill failed: {str(e)}[/bold red]\n")
        import traceback
        console.print(f"[red]{traceback.format_exc()}[/red]")
        raise
