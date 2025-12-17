import questionary
from InquirerPy import inquirer
from rent_research import RentResearcher
from loans import LoansProvider
from property_assessment import RiskAssessmentClient
from property_summary import PropertySummaryClient
from neighborhoods import NeighborhoodsClient
from rich.markdown import Markdown
from display import display_rent_estimates_comparison

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

def handle_rent_research_generation(property_id: str, supabase, console, handle_generate_rent_estimates_func):
    researcher = RentResearcher(supabase, console)

    try:
        report_id = researcher.generate_rent_research(property_id)

        if report_id:
            console.print(f"[green]✅ Research completed! Report ID: {report_id}[/green]")

            view_now = questionary.confirm("Would you like to view the report now?").ask()

            if view_now:
                report_data = researcher.get_report_by_id(report_id)
                if report_data:
                    researcher.display_report(report_data['report_content'])

            extract_estimates = questionary.confirm(
                "Would you like to extract rent estimates from this report?"
            ).ask()

            if extract_estimates:
                handle_generate_rent_estimates_func(property_id, supabase, console, report_id=report_id)
        else:
            console.print("[red]❌ Research generation failed.[/red]")

    except Exception as e:
        console.print(f"[red]Error during research generation: {str(e)}[/red]")

def handle_status_change(property_id, supabase):
    options = ["pending sale", "active", "passed", "sold", "off market"]
    new_status = questionary.select("Price cut amount", choices=options).ask()
    try:
        query = (
            supabase.table("properties")
            .update({"status": new_status})
            .eq("address1", property_id)
        )
        response = query.execute()
        if hasattr(response, "data"):
            print(f"Updated property data with status: {response.data}")
        else:
            print("Update response has no 'data' attribute")
    except Exception as e:
        print(f"Changing statusfor {property_id} failed: {str(e)}")

def handle_price_cut(property_id, current_price, supabase):
    amount = questionary.text("Price cut amount").ask()
    new_price = int(int(current_price) - int(amount))
    try:
      query = supabase.table("properties").update({
          "purchase_price": new_price,
          "has_reduced_price": True
      }).eq("address1", property_id)
      response = query.execute()
      if hasattr(response, "data"):
          print(f"Updated property data with new reduced price: {response.data}")
      else:
          print("Update response has no 'data' attribute")
    except Exception as e:
        print(f"Reducing price for {property_id} failed: {str(e)}")

def handle_view_research_reports(property_id: str, supabase, console):
    """Handle viewing existing research reports for a property"""
    researcher = RentResearcher(supabase, console)
    reports = researcher.get_reports_for_property(property_id)

    if not reports:
        console.print("[yellow]No research reports found for this property.[/yellow]")
        return

    while True:
        report_choices = []
        for report in reports:
            created_date = report['created_at'][:10]  # Extract date part
            status = report['status']
            cost = report['api_cost']
            report_choices.append(f"{created_date} - {status} (${cost:.4f}) - ID: {report['id'][:8]}")

        report_choices.append("← Go back")

        selected = questionary.select(
            "Select a research report to view:",
            choices=report_choices
        ).ask()

        if selected == "← Go back":
            return

        selected_id = None
        for report in reports:
            if report['id'][:8] in selected:
                selected_id = report['id']
                break

        if selected_id:
            report_data = researcher.get_report_by_id(selected_id)
            if report_data:
                researcher.display_report(report_data['report_content'])
            else:
                console.print("[red]Error loading report.[/red]")

def handle_risk_assessment(property_id: str, supabase, console):
    """Handle viewing and generating risk assessment reports"""
    # Check for existing risk assessment reports
    try:
        response = supabase.table("research_reports").select("*").eq(
            "property_id", property_id
        ).eq("research_type", "property_risk_report").order("created_at", desc=True).execute()

        existing_reports = response.data if response.data else []
    except Exception as e:
        console.print(f"[red]Error fetching risk assessment reports: {str(e)}[/red]")
        return

    # If no reports exist, ask if they want to generate one
    if not existing_reports:
        console.print("[yellow]No risk assessment report found for this property.[/yellow]")
        generate = questionary.confirm("Would you like to generate a risk assessment report?").ask()

        if generate:
            client = RiskAssessmentClient(supabase, console)
            report_id = client.generate_risk_assessment(property_id)

            if report_id:
                # Fetch and display the generated report
                try:
                    report_response = supabase.table("research_reports").select("*").eq(
                        "id", report_id
                    ).single().execute()

                    if report_response.data:
                        from rich.markdown import Markdown

                        md = Markdown(report_response.data['report_content'])

                        with console.pager():
                            console.print(md)
                except Exception as e:
                    console.print(f"[red]Error displaying report: {str(e)}[/red]")
        return

    # If reports exist, ask if they want to view or generate new
    action = questionary.select(
        "Risk assessment report(s) exist for this property. What would you like to do?",
        choices=[
            "View existing report",
            "Generate new report",
            "← Go back"
        ]
    ).ask()

    if action == "← Go back":
        return
    elif action == "Generate new report":
        client = RiskAssessmentClient(supabase, console)
        report_id = client.generate_risk_assessment(property_id)

        if report_id:
            # Fetch and display the generated report
            try:
                report_response = supabase.table("research_reports").select("*").eq(
                    "id", report_id
                ).single().execute()

                if report_response.data:
                    from rich.markdown import Markdown

                    md = Markdown(report_response.data['report_content'])

                    with console.pager():
                        console.print(md)
            except Exception as e:
                console.print(f"[red]Error displaying report: {str(e)}[/red]")
    elif action == "View existing report":
        # Show list of existing reports
        while True:
            report_choices = []
            for report in existing_reports:
                created_date = report['created_at'][:10]  # Extract date part
                status = report['status']
                cost = report.get('api_cost', 0)
                report_choices.append(f"{created_date} - {status} (${cost:.4f}) - ID: {report['id'][:8]}")

            report_choices.append("← Go back")

            selected = questionary.select(
                "Select a risk assessment report to view:",
                choices=report_choices
            ).ask()

            if selected == "← Go back":
                return

            # Find selected report
            selected_id = None
            for report in existing_reports:
                if report['id'][:8] in selected:
                    selected_id = report['id']
                    break

            if selected_id:
                try:
                    report_response = supabase.table("research_reports").select("*").eq(
                        "id", selected_id
                    ).single().execute()

                    if report_response.data:
                        from rich.markdown import Markdown

                        md = Markdown(report_response.data['report_content'])

                        with console.pager():
                            console.print(md)
                except Exception as e:
                    console.print(f"[red]Error displaying report: {str(e)}[/red]")

def handle_property_summary(property_id: str, supabase, console, df):
    """Handle viewing and generating property narrative summary reports"""
    # Get enriched property data from dataframe (with calculated financials)
    property_row = df[df['address1'] == property_id]
    if property_row.empty:
        console.print(f"[red]Property not found in dataframe: {property_id}[/red]")
        return

    # Convert row to dict for passing to client
    property_data = property_row.iloc[0].to_dict()

    # Check for existing property summary reports
    try:
        response = supabase.table("research_reports").select("*").eq(
            "property_id", property_id
        ).eq("research_type", "property_narrative_summary").order("created_at", desc=True).execute()

        existing_reports = response.data if response.data else []
    except Exception as e:
        console.print(f"[red]Error fetching property summary reports: {str(e)}[/red]")
        return

    # If no reports exist, ask if they want to generate one
    if not existing_reports:
        console.print("[yellow]No property summary found for this property.[/yellow]")
        generate = questionary.confirm("Would you like to generate a property summary?").ask()

        if generate:
            client = PropertySummaryClient(supabase, console)
            report_id = client.generate_summary(property_id, property_data=property_data)

            if report_id:
                # Fetch and display the generated report
                try:
                    report_response = supabase.table("research_reports").select("*").eq(
                        "id", report_id
                    ).single().execute()

                    if report_response.data:
                        md = Markdown(report_response.data['report_content'])

                        with console.pager():
                            console.print(md)
                except Exception as e:
                    console.print(f"[red]Error displaying report: {str(e)}[/red]")
        return

    # If reports exist, ask if they want to view or generate new
    action = questionary.select(
        "Property summary report(s) exist for this property. What would you like to do?",
        choices=[
            "View existing summary",
            "Generate new summary",
            "← Go back"
        ]
    ).ask()

    if action == "← Go back":
        return
    elif action == "Generate new summary":
        client = PropertySummaryClient(supabase, console)
        report_id = client.generate_summary(property_id, property_data=property_data)

        if report_id:
            # Fetch and display the generated report
            try:
                report_response = supabase.table("research_reports").select("*").eq(
                    "id", report_id
                ).single().execute()

                if report_response.data:
                    md = Markdown(report_response.data['report_content'])

                    with console.pager():
                        console.print(md)
            except Exception as e:
                console.print(f"[red]Error displaying report: {str(e)}[/red]")
    elif action == "View existing summary":
        # Show list of existing reports
        while True:
            report_choices = []
            for report in existing_reports:
                created_date = report['created_at'][:10]  # Extract date part
                status = report['status']
                cost = report.get('api_cost', 0)
                report_choices.append(f"{created_date} - {status} (${cost:.4f}) - ID: {report['id'][:8]}")

            report_choices.append("← Go back")

            selected = questionary.select(
                "Select a property summary to view:",
                choices=report_choices
            ).ask()

            if selected == "← Go back":
                return

            # Find selected report
            selected_id = None
            for report in existing_reports:
                if report['id'][:8] in selected:
                    selected_id = report['id']
                    break

            if selected_id:
                try:
                    report_response = supabase.table("research_reports").select("*").eq(
                        "id", selected_id
                    ).single().execute()

                    if report_response.data:
                        md = Markdown(report_response.data['report_content'])

                        with console.pager():
                            console.print(md)
                except Exception as e:
                    console.print(f"[red]Error displaying report: {str(e)}[/red]")

def handle_generate_rent_estimates(property_id: str, supabase, console, report_id: str = None):
    """Handle generating rent estimates from an existing research report"""
    researcher = RentResearcher(supabase, console)

    selected = None
    selected_id = None

    if not report_id:
        reports = researcher.get_reports_for_property(property_id)

        if not reports:
            console.print("[yellow]No research reports found for this property.[/yellow]")
            console.print("[dim]Generate a research report first to use this feature.[/dim]")
            return

        report_choices = []
        for report in reports:
            created_date = report['created_at'][:10]  # Extract date part
            status = report['status']
            cost = report['api_cost']
            choice_label = f"{created_date} - {status} (${cost:.4f}) - ID: {report['id'][:8]}"
            report_choices.append(choice_label)

        selected = inquirer.fuzzy(
            message="Type to search and select a research report:",
            choices=report_choices,
            default="",
            multiselect=False,
            validate=None,
            invalid_message="Invalid selection"
        ).execute()

        if not selected:
            return

        for report in reports:
            if report['id'][:8] in selected:
                selected_id = report['id']
                break

        if not selected_id:
            console.print("[red]Error: Could not identify selected report.[/red]")
            return
    else:
        # When report_id is provided, create a description for display
        selected_id = report_id
        report_data = researcher.get_report_by_id(report_id)
        if report_data:
            created_date = report_data['created_at'][:10]
            selected = f"{created_date} - Report ID: {report_id[:8]}"
        else:
            selected = f"Report ID: {report_id[:8]}"

    try:
        id_to_use = report_id if report_id else selected_id
        result = researcher.generate_rent_estimates_from_report(id_to_use)

        if result["success"]:
            estimates = result["estimates"]
            existing_estimates = result.get("existing_estimates", {})
            unit_configs = result.get("unit_configs", [])

            display_rent_estimates_comparison(
                property_id, estimates, existing_estimates, unit_configs,
                result['cost'], selected
            )

            update_database = questionary.confirm(
                "Would you like to update the database with these new rent estimates?",
                default=False,
            ).ask()

            if update_database:
                update_success = researcher._update_rent_estimates_in_db(
                    property_id, unit_configs, estimates
                )

                if update_success:
                    console.print("\n[bold green]✅ Database updated successfully![/bold green]")
                else:
                    console.print("\n[bold red]❌ Database update failed. See details above.[/bold red]")
            else:
                console.print("\n[blue]Database update skipped. Estimates are displayed above for review only.[/blue]")
        else:
            console.print(f"[red]Failed to generate estimates: {result['error']}[/red]")

    except Exception as e:
        console.print(f"[red]Error generating estimates: {str(e)}[/red]")

def handle_rent_research_after_add(property_id: str, supabase, console, ask_user=True):
    """Handle rent research workflow after adding a new property"""
    researcher = RentResearcher(supabase, console)

    try:
        property_response = supabase.table("properties").select("units").eq("address1", property_id).single().execute()
        is_single_family = property_response.data and property_response.data.get("units", 1) == 0
    except Exception:
        is_single_family = False

    # Generate per-room rent research (for single family, this is roommate strategy)
    report_id = researcher.generate_rent_research(property_id)

    try:
        result = researcher.generate_rent_estimates_from_report(report_id)

        if result["success"]:
            estimates = result["estimates"]
            existing_estimates = result.get("existing_estimates", {})
            unit_configs = result.get("unit_configs", [])

            display_rent_estimates_comparison(
                property_id, estimates, existing_estimates, unit_configs,
                result['cost'], "Report we just made", console
            )

            if ask_user:
                update_database = questionary.confirm(
                    "Would you like to update the database with these new rent estimates?",
                    default=False,
                ).ask()
            else:
                update_database = True

            if update_database:
                update_success = researcher._update_rent_estimates_in_db(
                    property_id, unit_configs, estimates
                )

                if update_success:
                    console.print("\n[bold green]✅ Database updated successfully![/bold green]")
                else:
                    console.print("\n[bold red]❌ Database update failed. See details above.[/bold red]")
        else:
            console.print(f"[red]Failed to generate estimates: {result['error']}[/red]")

    except Exception as e:
        console.print(f"[red]Error generating estimates: {str(e)}[/red]")

    if is_single_family:
        console.print("\n[bold cyan]🏠 Single Family Home Detected[/bold cyan]")
        console.print("You can also generate property-wide rent research to compare traditional rental vs roommate strategy.\n")

        if ask_user:
            do_property_wide = questionary.confirm(
                "Generate property-wide rent research (GPT-5)?",
                default=False
            ).ask()
        else:
            do_property_wide = True

        if do_property_wide:
            property_wide_report_id = researcher.generate_property_wide_research(property_id)

            if property_wide_report_id:
                property_wide_result = researcher.extract_property_wide_estimates(property_wide_report_id)

                if property_wide_result:
                    console.print("\n[bold green]✅ Property-wide rent estimates saved to properties table![/bold green]")
                else:
                    console.print("\n[bold red]❌ Failed to extract property-wide estimates.[/bold red]")
            else:
                console.print("\n[bold red]❌ Property-wide research generation failed.[/bold red]")


def handle_scrape_neighborhood_from_findneighborhoods(property_id: str, supabase, console, scraper, ask_user):
    """
    Scrape neighborhood data from FindNeighborhoods.dsm.city for a property.

    Args:
        property_id: Property address (address1)
        supabase: Supabase client
        console: Rich console for output
        scraper: NeighborhoodScraper instance
        ask_user: Whether or not the handler should ask the user before saving to db
    """
    try:
        property_response = supabase.table("properties").select("full_address").eq("address1", property_id).single().execute()

        if not property_response.data:
            console.print("[red]❌ Property not found[/red]")
            return

        full_address = property_response.data['full_address']
        console.print(f"\n[bold cyan]Scraping neighborhood for:[/bold cyan] {full_address}")

        neighborhood = scraper.get_neighborhood_by_address(full_address)
        console.print(f"\n[bold green]🏘️  Scraped Neighborhood:[/bold green] [bold]{neighborhood}[/bold]")

        neighborhood_client = NeighborhoodsClient(supabase_client=supabase, console=console)
        current_neighborhood = neighborhood_client.get_neighborhood_for_property(address1=property_id, supabase=supabase)

        if current_neighborhood:
            console.print(f"[dim]Current neighborhood in database:[/dim] {current_neighborhood}")

        if ask_user:
            save_to_db = questionary.confirm(
                f"Would you like to save '{neighborhood}' as the neighborhood for this property?"
            ).ask()
        else:
            save_to_db = True

        if save_to_db:
            neighborhood_id, was_created = neighborhood_client.get_or_create_neighborhood(neighborhood_name=neighborhood, supabase=supabase)
            res = neighborhood_client.assign_neighborhood_to_property(property_id=property_id, neighborhood_id=neighborhood_id)

            if was_created:
                console.print(f"[green]✅ Neighborhood '{neighborhood}' was newly added to database[/green]")

            if res == "NEWLY_ASSIGNED":
                console.print(f"[green]✅ Neighborhood updated to '{neighborhood}' in database[/green]")
            elif res == "ALREADY_ASSIGNED":
                console.print(f"[green]✅ Neighborhood was already assigned to '{neighborhood}' in database[/green]")
        else:
            console.print("[yellow]Skipped saving to database[/yellow]")

    except Exception as e:
        console.print(f"[red]❌ Error during neighborhood scraping: {str(e)}[/red]")
