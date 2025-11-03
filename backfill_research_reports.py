"""
Interactive Backfill Research Reports Script

This script allows users to interactively go through all properties and:
1. Generate research reports for properties that don't have them
2. View existing research reports 
3. Extract rent estimates from reports
4. Update the database with new estimates

The script reuses existing methods from the main application to maintain consistency.
"""

import os
from typing import Dict, List, Any
import questionary
from rich.console import Console
from rich.panel import Panel
from dotenv import load_dotenv
from supabase import create_client, Client
from InquirerPy import inquirer

# Import existing modules
from rent_research import RentResearcher
from run import reload_dataframe, format_currency

# Load environment variables
load_dotenv()

# Initialize console and supabase
console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

class BackfillStats:
    """Track statistics for the backfill process"""
    def __init__(self):
        self.total_properties = 0
        self.processed = 0
        self.skipped = 0
        self.reports_generated = 0
        self.estimates_extracted = 0
        self.database_updates = 0
        self.errors = 0
        self.error_details = []

    def add_error(self, property_id: str, error_msg: str):
        self.errors += 1
        self.error_details.append(f"{property_id}: {error_msg}")

    def summary(self) -> str:
        success_rate = ((self.processed - self.errors) / max(self.processed, 1) * 100) if self.processed > 0 else 0
        return f"""[bold cyan]Backfill Process Summary[/bold cyan]

Total Properties: {self.total_properties}
Processed: {self.processed}
Skipped: {self.skipped}
Reports Generated: {self.reports_generated}
Estimates Extracted: {self.estimates_extracted}
Database Updates: {self.database_updates}
Errors: {self.errors}

Success Rate: {success_rate:.1f}%"""

def display_property_summary(property_data: Dict[str, Any], current_index: int, total_count: int):
    """Display a summary of the current property being processed"""
    
    address = property_data.get('address1', 'Unknown')
    price = property_data.get('purchase_price', 0)
    beds = property_data.get('beds', 0)
    baths = property_data.get('baths', 0)
    units = property_data.get('units', 1)
    status = property_data.get('status', 'unknown')
    
    summary_text = f"""Address: {address}
Purchase Price: {format_currency(price)}
Configuration: {beds} bed, {baths} bath, {units} units
Status: {status}

Progress: Property {current_index} of {total_count}"""
    
    console.print(Panel(
        summary_text,
        title=f"[bold cyan]Property {current_index}/{total_count}[/bold cyan]",
        border_style="cyan"
    ))

def get_all_properties() -> List[Dict[str, Any]]:
    """Load all properties from the database"""
    try:
        response = supabase.table('properties').select('*').order('address1').execute()
        return response.data if response.data else []
    except Exception as e:
        console.print(f"[red]Error loading properties: {str(e)}[/red]")
        return []

def check_existing_reports(property_id: str) -> int:
    """Check how many research reports exist for a property"""
    try:
        researcher = RentResearcher(supabase, console)
        reports = researcher.get_reports_for_property(property_id)
        return len(reports) if reports else 0
    except Exception as e:
        console.print(f"[red]Error checking reports for {property_id}: {str(e)}[/red]")
        return 0

def main():
    """Main interactive backfill process"""
    console.print(Panel(
        "[bold green]🔄 Interactive Research Reports Backfill[/bold green]\n\n"
        "This script will help you generate research reports and rent estimates\n"
        "for all properties in your database.\n\n"
        "For each property, you can:\n"
        "• Generate new research reports\n"
        "• View existing reports\n" 
        "• Extract rent estimates from reports\n"
        "• Update the database with new estimates",
        title="Backfill Research Reports",
        border_style="green"
    ))
    
    # Initialize stats tracking
    stats = BackfillStats()
    
    # Load all properties
    console.print("\n[cyan]Loading properties from database...[/cyan]")
    properties = get_all_properties()
    
    if not properties:
        console.print("[red]No properties found in database.[/red]")
        return
    
    stats.total_properties = len(properties)
    console.print(f"[green]Found {len(properties)} properties to process.[/green]\n")
    
    # Ask for confirmation to proceed
    proceed = questionary.confirm(
        f"Do you want to start the backfill process for {len(properties)} properties?",
        default=True
    ).ask()
    
    if not proceed:
        console.print("[yellow]Backfill process cancelled.[/yellow]")
        return
    
    # Main processing loop
    skip_all = False
    
    for i, property_data in enumerate(properties, 1):
        if skip_all:
            stats.skipped += 1
            continue
            
        property_id = property_data['address1']
        
        # Display current property
        console.print("\n" + "="*80 + "\n")
        display_property_summary(property_data, i, len(properties))
        
        # Check existing reports
        existing_reports_count = check_existing_reports(property_id)
        if existing_reports_count > 0:
            console.print(f"[blue]ℹ️  This property has {existing_reports_count} existing research report(s).[/blue]")
        else:
            console.print("[yellow]⚠️  This property has no research reports.[/yellow]")
        
        # Main action menu
        action_choices = [
            "Generate new research report",
            "Skip this property",
            "Skip all remaining properties",
            "Quit backfill process"
        ]
        
        # Add conditional choices
        if existing_reports_count > 0:
            action_choices.insert(1, "View existing research reports")
            action_choices.insert(2, "Extract rent estimates from report")
        
        action = questionary.select(
            f"What would you like to do for {property_id}?",
            choices=action_choices
        ).ask()
        
        if action == "Skip this property":
            stats.skipped += 1
            stats.processed += 1
            continue
        elif action == "Skip all remaining properties":
            remaining = len(properties) - i + 1
            stats.skipped += remaining
            break
        elif action == "Quit backfill process":
            break
        elif action == "Generate new research report":
            try:
                console.print(f"\n[cyan]🔍 Generating research report for {property_id}...[/cyan]")
                researcher = RentResearcher(supabase, console)
                report_id = researcher.generate_rent_research(property_id)
                
                if report_id:
                    stats.reports_generated += 1
                    console.print("[green]✅ Research report generated successfully![/green]")
                    
                    # Ask if user wants to view the report
                    view_report = questionary.confirm("Would you like to view the report now?").ask()
                    if view_report:
                        report_data = researcher.get_report_by_id(report_id)
                        if report_data:
                            researcher.display_report(report_data['report_content'])
                    
                    # Ask about extracting estimates
                    extract_estimates = questionary.confirm(
                        "Would you like to extract rent estimates from this report?"
                    ).ask()
                    
                    if extract_estimates:
                        result = researcher.generate_rent_estimates_from_report(report_id)
                        if result.get("success"):
                            stats.estimates_extracted += 1
                            
                            # Ask about database update
                            update_db = questionary.confirm(
                                "Would you like to update the database with these estimates?"
                            ).ask()
                            
                            if update_db:
                                estimates = result["estimates"]
                                unit_configs = result.get("unit_configs", [])
                                
                                # Perform database update
                                update_success = researcher._update_rent_estimates_in_db(
                                    property_id, unit_configs, estimates
                                )
                                
                                if update_success:
                                    stats.database_updates += 1
                                    console.print("[green]✅ Database updated successfully![/green]")
                                    reload_dataframe()
                                else:
                                    stats.add_error(property_id, "Database update failed")
                        else:
                            error_msg = result.get('error', 'Unknown error')
                            stats.add_error(property_id, f"Estimate extraction failed: {error_msg}")
                else:
                    stats.add_error(property_id, "Research report generation failed")
                    
            except Exception as e:
                stats.add_error(property_id, f"Error during report generation: {str(e)}")
                
        elif action == "View existing research reports":
            try:
                researcher = RentResearcher(supabase, console)
                reports = researcher.get_reports_for_property(property_id)
                
                if reports:
                    # Show report selection
                    report_choices = []
                    for report in reports:
                        created_date = report['created_at'][:10]
                        status = report['status']
                        cost = report['api_cost']
                        choice_text = f"{created_date} - {status} (${cost:.4f}) - ID: {report['id'][:8]}"
                        report_choices.append(choice_text)
                    
                    report_choices.append("← Go back")
                    
                    selected = questionary.select(
                        "Select a research report to view:",
                        choices=report_choices
                    ).ask()
                    
                    if selected != "← Go back":
                        # Find and display selected report
                        for report in reports:
                            if report['id'][:8] in selected:
                                researcher.display_report(report['report_content'])
                                break
                else:
                    console.print("[yellow]No research reports found.[/yellow]")
                    
            except Exception as e:
                stats.add_error(property_id, f"Error viewing reports: {str(e)}")
                
        elif action == "Extract rent estimates from report":
            try:
                researcher = RentResearcher(supabase, console)
                reports = researcher.get_reports_for_property(property_id)
                
                if reports:
                    # Create choices for report selection
                    report_choices = []
                    for report in reports:
                        created_date = report['created_at'][:10]
                        status = report['status']
                        cost = report['api_cost']
                        choice_label = f"{created_date} - {status} (${cost:.4f}) - ID: {report['id'][:8]}"
                        report_choices.append(choice_label)
                    
                    # Use fuzzy search for selection
                    selected = inquirer.fuzzy(
                        message="Type to search and select a research report:",
                        choices=report_choices,
                        default="",
                        multiselect=False,
                        validate=None,
                        invalid_message="Invalid selection"
                    ).execute()
                    
                    if selected:
                        # Extract report ID
                        selected_id = None
                        for report in reports:
                            if report['id'][:8] in selected:
                                selected_id = report['id']
                                break
                        
                        if selected_id:
                            result = researcher.generate_rent_estimates_from_report(selected_id)
                            
                            if result.get("success"):
                                stats.estimates_extracted += 1
                                
                                # Ask about database update
                                update_db = questionary.confirm(
                                    "Would you like to update the database with these estimates?"
                                ).ask()
                                
                                if update_db:
                                    estimates = result["estimates"]
                                    unit_configs = result.get("unit_configs", [])
                                    
                                    # Perform database update
                                    update_success = researcher._update_rent_estimates_in_db(
                                        property_id, unit_configs, estimates
                                    )
                                    
                                    if update_success:
                                        stats.database_updates += 1
                                        console.print("[green]✅ Database updated successfully![/green]")
                                        reload_dataframe()
                                    else:
                                        stats.add_error(property_id, "Database update failed")
                            else:
                                error_msg = result.get('error', 'Unknown error')
                                stats.add_error(property_id, f"Estimate extraction failed: {error_msg}")
                else:
                    console.print("[yellow]No research reports found.[/yellow]")
                    
            except Exception as e:
                stats.add_error(property_id, f"Error extracting estimates: {str(e)}")
        
        stats.processed += 1
    
    # Final summary
    console.print("\n" + "="*80 + "\n")
    console.print(Panel(stats.summary(), title="Backfill Complete", border_style="green"))
    
    # Show errors if any
    if stats.errors > 0:
        console.print("\n[red]Errors encountered:[/red]")
        for error in stats.error_details:
            console.print(f"[red]• {error}[/red]")

if __name__ == "__main__":
    main()