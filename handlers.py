import questionary
from InquirerPy import inquirer
from rent_research import RentResearcher
from loans import LoansProvider
from property_assessment import RiskAssessmentClient
from property_summary import PropertySummaryClient
from rich.markdown import Markdown
from display import display_rent_estimates_comparison
from add_property import get_or_create_neighborhood

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

            update_database = display_rent_estimates_comparison(
                property_id, estimates, existing_estimates, unit_configs,
                result['cost'], selected
            )

            if update_database:
                console.print("\n[bold yellow]⚠️  This will overwrite the current estimates in the database.[/bold yellow]")
                final_confirm = questionary.confirm(
                    "Are you sure you want to proceed with the database update?",
                    default=False
                ).ask()

                if final_confirm:
                    update_success = researcher._update_rent_estimates_in_db(
                        property_id, unit_configs, estimates
                    )

                    if update_success:
                        console.print("\n[bold green]✅ Database updated successfully![/bold green]")
                    else:
                        console.print("\n[bold red]❌ Database update failed. See details above.[/bold red]")
                else:
                    console.print("\n[yellow]Database update cancelled.[/yellow]")
            else:
                console.print("\n[blue]Database update skipped. Estimates are displayed above for review only.[/blue]")
        else:
            console.print(f"[red]Failed to generate estimates: {result['error']}[/red]")

    except Exception as e:
        console.print(f"[red]Error generating estimates: {str(e)}[/red]")

def handle_rent_research_after_add(property_id: str, supabase, console, neighborhoods):
    """Handle rent research workflow after adding a new property"""
    # Prompt for neighborhood assignment (optional)
    console.print("\n[bold cyan]🏘️  Neighborhood Assignment[/bold cyan]")
    neighborhood_input = questionary.text(
        "Enter neighborhood name (or press Enter to skip):",
        default=""
    ).ask()

    if neighborhood_input and neighborhood_input.strip():
        # User provided a neighborhood - assign and analyze it
        neighborhood_name = neighborhood_input.strip()

        # Get or create the neighborhood in the database
        neighborhood_id, was_created = get_or_create_neighborhood(neighborhood_name, supabase)

        if neighborhood_id:
            # Assign neighborhood to property via junction table
            try:
                # Check if already assigned
                existing_assignment = (
                    supabase.table("property_neighborhood")
                    .select("*")
                    .eq("address1", property_id)
                    .eq("neighborhood_id", neighborhood_id)
                    .execute()
                )

                if not existing_assignment.data or len(existing_assignment.data) == 0:
                    # Insert new assignment
                    supabase.table("property_neighborhood").insert({
                        "address1": property_id,
                        "neighborhood_id": neighborhood_id
                    }).execute()

                    if was_created:
                        console.print(f"[green]✓ Created and assigned neighborhood: {neighborhood_name}[/green]")
                    else:
                        console.print(f"[green]✓ Assigned existing neighborhood: {neighborhood_name}[/green]")
                else:
                    console.print(f"[yellow]Neighborhood '{neighborhood_name}' already assigned to this property[/yellow]")

                # Automatically run neighborhood analysis
                console.print("\n[cyan]Running neighborhood analysis...[/cyan]")
                handle_neighborhood_analysis(property_id, console, neighborhoods)

            except Exception as e:
                console.print(f"[red]Error assigning neighborhood: {str(e)}[/red]")
        else:
            console.print(f"[red]Failed to create/find neighborhood '{neighborhood_name}'[/red]")

    researcher = RentResearcher(supabase, console)

    # Fetch property data to check if it's single family
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

    # For single family homes, offer property-wide research option
    if is_single_family:
        console.print("\n[bold cyan]🏠 Single Family Home Detected[/bold cyan]")
        console.print("You can also generate property-wide rent research to compare traditional rental vs roommate strategy.\n")

        do_property_wide = questionary.confirm(
            "Generate property-wide rent research (GPT-5)?",
            default=False
        ).ask()

        if do_property_wide:
            # Generate property-wide research
            property_wide_report_id = researcher.generate_property_wide_research(property_id)

            if property_wide_report_id:
                # Extract estimates from property-wide research
                property_wide_result = researcher.extract_property_wide_estimates(property_wide_report_id)

                if property_wide_result:
                    console.print("\n[bold green]✅ Property-wide rent estimates saved to properties table![/bold green]")
                else:
                    console.print("\n[bold red]❌ Failed to extract property-wide estimates.[/bold red]")
            else:
                console.print("\n[bold red]❌ Property-wide research generation failed.[/bold red]")
