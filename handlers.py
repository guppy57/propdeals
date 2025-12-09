import questionary
from rent_research import RentResearcher
from loans import LoansProvider

def handle_property_wide_research_generation(property_id: str, supabase, console):
    """Generate property-wide rent research for single family homes (whole-house rental analysis)"""
    researcher = RentResearcher(supabase, console)

    try:
        report_id = researcher.generate_property_wide_research(property_id)

        if report_id:
            console.print(
                f"[green]✅ Property-wide research completed! Report ID: {report_id}[/green]"
            )

            view_now = questionary.confirm(
                "Would you like to view the report now?"
            ).ask()

            if view_now:
                report_data = researcher.get_report_by_id(report_id)
                if report_data:
                    researcher.display_report(report_data["report_content"])

            extract_estimates = questionary.confirm(
                "Would you like to extract property-wide rent estimates and update the properties table?"
            ).ask()

            if extract_estimates:
                property_wide_result = researcher.extract_property_wide_estimates(
                    report_id
                )

                if not property_wide_result:
                    console.print(
                        "\n[bold red]❌ Failed to extract property-wide estimates.[/bold red]"
                    )
        else:
            console.print("[red]❌ Property-wide research generation failed.[/red]")

    except Exception as e:
        console.print(
            f"[red]Error during property-wide research generation: {str(e)}[/red]"
        )

def handle_neighborhood_analysis(property_id: str, console, neighborhoods):
    """Run neighborhood analysis for a property (checks for existing reports first)"""
    try:
        report_id, was_existing = neighborhoods.generate_neighborhood_research(property_id)

        if report_id:
            if was_existing:
                # Existing report found - just offer to view it
                console.print("\n[bold yellow]📍 An existing neighborhood report was found for this area.[/bold yellow]")
                console.print("[dim]This report is shared across all properties in the same neighborhood.[/dim]")

                view_now = questionary.confirm("Would you like to view the existing neighborhood report?").ask()

                if view_now:
                    report_data = neighborhoods.get_report_by_id(report_id)
                    if report_data:
                        neighborhoods.display_report(report_data['report_content'])
                    else:
                        console.print("[red]❌ Error: Could not load the report.[/red]")
            else:
                # New report was generated
                console.print(f"\n[bold green]✅ New neighborhood research completed! Report ID: {report_id}[/bold green]")

                view_now = questionary.confirm("Would you like to view the neighborhood report now?").ask()

                if view_now:
                    report_data = neighborhoods.get_report_by_id(report_id)
                    if report_data:
                        neighborhoods.display_report(report_data['report_content'])
                    else:
                        console.print("[red]❌ Error: Could not load the report.[/red]")

                # Automatically extract and save letter grade for new reports
                console.print("\n[cyan]📊 Extracting neighborhood letter grade...[/cyan]")
                try:
                    grade_result = neighborhoods.extract_neighborhood_grade(report_id, show_progress=True)

                    if grade_result and grade_result.get('letter_grade'):
                        console.print(f"[bold green]✓ Letter grade '{grade_result['letter_grade']}' saved to neighborhoods table[/bold green]")
                    else:
                        console.print("[yellow]⚠ Failed to extract letter grade[/yellow]")
                except Exception as e:
                    console.print(f"[yellow]⚠ Error extracting letter grade: {str(e)}[/yellow]")
        else:
            console.print("[red]❌ Neighborhood analysis failed.[/red]")

    except Exception as e:
        console.print(f"[red]Error during neighborhood analysis: {str(e)}[/red]")

def handle_changing_loan(supabase, console):
    loan_provider = LoansProvider(supabase_client=supabase, console=console)
    loans = loan_provider.get_loans()
    loan_choices = []

    for loan in loans:
        loan_choices.append(f"{loan.id} - {loan.name}")

    selected_loan = questionary.select("Select a loan", choices=loan_choices).ask()
    selected_loan_id = None

    for loan in loans:
        if f"{loan.id} - {loan.name}" == selected_loan:
            selected_loan_id = loan.id

    return selected_loan_id
    
def handle_extract_neighborhood_grade(property_id: str, supabase, console, neighborhoods):
    """Manually extract letter grade from existing neighborhood report"""
    try:
        # Get neighborhood for the property
        neighborhood_response = (
            supabase.table("property_neighborhood")
            .select("neighborhoods(name)")
            .eq("address1", property_id)
            .limit(1)
            .execute()
        )

        if not neighborhood_response.data or len(neighborhood_response.data) == 0:
            console.print(
                f"\n[yellow]⚠️  No neighborhood assigned for property: {property_id}[/yellow]"
            )
            console.print(
                "[yellow]Please assign a neighborhood first before extracting letter grade.[/yellow]"
            )
            return

        # Extract neighborhood name
        neighborhood_dict = neighborhood_response.data[0].get("neighborhoods")
        if (
            not neighborhood_dict
            or not isinstance(neighborhood_dict, dict)
            or "name" not in neighborhood_dict
        ):
            console.print("[red]❌ Invalid neighborhood data structure[/red]")
            return

        neighborhood_name = neighborhood_dict["name"]

        # Look for existing completed neighborhood report
        existing_report = (
            supabase.table("research_reports")
            .select("id")
            .eq("research_type", f"{neighborhood_name}_neighborhood_report")
            .eq("status", "completed")
            .limit(1)
            .execute()
        )

        if not existing_report.data or len(existing_report.data) == 0:
            console.print(
                f"\n[yellow]⚠️  No neighborhood report found for '{neighborhood_name}'[/yellow]"
            )
            console.print(
                "[yellow]Please run a neighborhood analysis first before extracting letter grade.[/yellow]"
            )
            return

        report_id = existing_report.data[0]["id"]
        console.print(
            f"\n[cyan]📊 Extracting letter grade from neighborhood report for '{neighborhood_name}'...[/cyan]"
        )

        # Extract and save the letter grade
        grade_result = neighborhoods.extract_neighborhood_grade(
            report_id, show_progress=True
        )

        if grade_result and grade_result.get("letter_grade"):
            console.print(
                f"\n[bold green]✓ Letter grade '{grade_result['letter_grade']}' saved to neighborhoods table[/bold green]"
            )
            console.print(
                f"[dim]Confidence: {grade_result.get('confidence_score', 'N/A')}[/dim]"
            )
        else:
            console.print("[red]❌ Failed to extract letter grade[/red]")

    except Exception as e:
        console.print(
            f"[red]Error extracting neighborhood letter grade: {str(e)}[/red]"
        )