from rich.table import Table
from rich.panel import Panel
import pandas as pd
import questionary
from helpers import (
    calculate_additional_room_rent,
    calculate_quintile_colors_for_metrics,
    express_percent_as_months_and_days,
    format_currency,
    format_number,
    format_percentage,
)

def display_all_properties(
    console,
    df,
    properties_df,
    title,
    show_status=False,
    show_min_rent_data=False,
    show_prop_type=False,
    sort_by="units",
):
    dataframe = df if properties_df is None else properties_df
    if sort_by == "units":
        dataframe = dataframe.sort_values(by="units")
    elif sort_by == "y2_cf":
        dataframe = dataframe.sort_values(by="monthly_cash_flow")
    table = Table(title=title, show_header=True, header_style="bold magenta")
    price_20th = dataframe["purchase_price"].quantile(0.20)
    price_40th = dataframe["purchase_price"].quantile(0.40)
    price_60th = dataframe["purchase_price"].quantile(0.60)
    price_80th = dataframe["purchase_price"].quantile(0.80)
    cash_20th = dataframe["cash_needed"].quantile(0.20)
    cash_40th = dataframe["cash_needed"].quantile(0.40)
    cash_60th = dataframe["cash_needed"].quantile(0.60)
    cash_80th = dataframe["cash_needed"].quantile(0.80)
    costs_to_income_75th_percentile = dataframe["costs_to_income"].quantile(0.75)
    costs_to_income_25th_percentile = dataframe["costs_to_income"].quantile(0.25)

    def get_quintile_color(value, p20, p40, p60, p80):
        """Return color based on quintile position (lower values = better = greener)"""
        if value <= p20:
            return "bright_green"
        elif value <= p40:
            return "green"
        elif value <= p60:
            return "yellow"
        elif value <= p80:
            return "orange3"
        else:
            return "red"

    table.add_column(f"Property ({len(properties_df)})", style="cyan", no_wrap=True)

    if show_prop_type:
        table.add_column("Type", justify="right", style="bold white")

    table.add_column("Price", justify="right", no_wrap=True)
    table.add_column("Cash Needed", justify="right")
    table.add_column("Costs/mo", justify="right", style="yellow")
    table.add_column("CF", justify="right", no_wrap=True)
    table.add_column("Cost/Inc", justify="right", style="bold white")
    table.add_column("MGR_PP", justify="right")
    table.add_column("OpEx_Rent", justify="right")
    table.add_column("DSCR", justify="right")
    table.add_column("NPV10", justify="right")

    if show_status:
        table.add_column("Status", justify="right", style="bold white")

    if show_min_rent_data:
        table.add_column("MinR Unit Beds", justify="right", style="bold white")
        table.add_column("Add. Beds", justify="right", style="bold white")
        table.add_column("Add. Rent", justify="right", style="bold white")

    for _, row in dataframe.iterrows():
        cf_style = "red" if row["monthly_cash_flow"] < 0 else "green"

        price_style = get_quintile_color(
            row["purchase_price"], price_20th, price_40th, price_60th, price_80th
        )
        cash_style = get_quintile_color(
            row["cash_needed"], cash_20th, cash_40th, cash_60th, cash_80th
        )

        costs_to_income_style = (
            "green"
            if row["costs_to_income"] <= costs_to_income_25th_percentile
            else (
                "yellow"
                if row["costs_to_income"] <= costs_to_income_75th_percentile
                else "red"
            )
        )

        prop_types = {0: "SFH", 2: "2PX", 3: "3PX", 4: "4PX"}
        prop_type_styles = {0: "yellow", 2: "red", 3: "blue", 4: "green"}

        row_args = [str(row["address1"])]

        if show_prop_type:
            pt_style = prop_type_styles[row["units"]]
            row_args.append(f"[{pt_style}]{prop_types[row['units']]}[/{pt_style}]")

        row_args.extend(
            [
                f"[{price_style}]{format_currency(row['purchase_price'])}[/{price_style}]",
                f"[{cash_style}]{format_currency(row['cash_needed'])}[/{cash_style}]",
                format_currency(row["total_monthly_cost"]),
                f"[{cf_style}]{format_currency(row['monthly_cash_flow'])}[/{cf_style}]",
                f"[{costs_to_income_style}]{format_percentage(row['costs_to_income'])}[/{costs_to_income_style}]",
                f"{format_percentage(row["MGR_PP"])}",
                f"{format_percentage(row["OpEx_Rent"])}",
                f"{format_percentage(row["DSCR"])}",
                f"{format_currency(row["npv_10yr"])}"
            ]
        )

        if show_status:
            row_args.append(row["status"])

        if show_min_rent_data:
            row_args.append(str(row["min_rent_unit_beds"]))
            row_args.append(str(int(row["min_rent_unit_beds"] - 1)))
            row_args.append(str(calculate_additional_room_rent(row)))

        table.add_row(*row_args)

    console.print(table)


def display_y2_calculations(console, df, properties_df=None):
    """Display property options table with Y2 financial calculations"""
    dataframe = df if properties_df is None else properties_df
    dataframe = dataframe.sort_values(by="units")  # Default sort

    table = Table(title="Property Calculations (without Market Rent)", show_header=True, header_style="bold magenta")

    # Add columns
    table.add_column("Address", style="cyan", no_wrap=True)
    table.add_column("Purchase Price", justify="right")
    table.add_column("Down Payment", justify="right", style="yellow")
    table.add_column("Closing Costs", justify="right", style="yellow")
    table.add_column("Total Rent", justify="right", style="green")
    table.add_column("Monthly Mortgage", justify="right", style="red")
    table.add_column("Monthly MIP", justify="right", style="red")
    table.add_column("Monthly Taxes", justify="right", style="red")
    table.add_column("Monthly Insurance", justify="right", style="red")
    table.add_column("Repair Cost", justify="right", style="yellow")
    table.add_column("Vacancy Reserve", justify="right", style="yellow")
    table.add_column("Monthly CF", justify="right")

    # Iterate and add rows
    for _, row in dataframe.iterrows():
        # Determine cashflow color
        cf_style = "red" if row["monthly_cash_flow"] < 0 else "green"

        # Build row with formatted values
        row_args = [
            str(row["address1"]),
            format_currency(row["purchase_price"]),
            format_currency(row["down_payment"]),
            format_currency(row["closing_costs"]),
            format_currency(row["total_rent"]),
            format_currency(row["monthly_mortgage"]),
            format_currency(row["monthly_mip"]),
            format_currency(row["monthly_taxes"]),
            format_currency(row["monthly_insurance"]),
            format_currency(row["monthly_repair_costs"]),
            format_currency(row["monthly_vacancy_costs"]),
            f"[{cf_style}]{format_currency(row['monthly_cash_flow'])}[/{cf_style}]"
        ]

        table.add_row(*row_args)

    console.print(table)


def display_new_property_qualification(console, address1, get_all_phase1_qualifying_properties):
    current, contingent, creative = get_all_phase1_qualifying_properties()

    current_result = current.query(f'address1 == "{address1}"')
    contingent_result = contingent.query(f'address1 == "{address1}"')
    creative_result = creative.query(f'address1 == "{address1}"')

    current_msg = "Disqualified: Phase 1 Current" if current_result.empty else "Qualified: Phase 1 Current"
    contingent_msg = "Disqualified: Phase 1 Contingent" if contingent_result.empty else "Qualified: Phase 1 Contingent"
    creative_msg = "Disqualified: Phase 1 Creative" if creative_result.empty else "Qualified: Phase 1 Creative"
    cur_style = "red" if current_result.empty else "green"
    con_style = "red" if contingent_result.empty else "green"
    cre_style = "red" if creative_result.empty else "green"

    console.print(Panel(
        f"[{cur_style}]{current_msg}[/{cur_style}]\n"
        f"[{con_style}]{contingent_msg}[/{con_style}]\n"
        f"[{cre_style}]{creative_msg}[/{cre_style}]",
        title="Phase 1 Qualification Results"
    ))


def display_all_phase1_qualifying_properties(console, df, get_all_phase1_qualifying_properties):
    current, contingent, creative = get_all_phase1_qualifying_properties()

    display_all_properties(
        properties_df=current, df=df, title="Phase 1 Criteria Qualifiers - Current Prices", console=console,
    )

    display_all_properties(
        properties_df=contingent,
        df=df,
        title="Phase 1 Criteria Qualifiers - Contingent on 10% Price Reduction",
        console=console
    )

    display_all_properties(
      properties_df=creative,
      df=df,
      title="Phase 1 Criteria Qualifiers - If we rent out additional rooms in our unit",
      show_min_rent_data=True,
      console=console
    )


def display_all_phase2_qualifying_properties(console, df, get_all_phase2_properties):
    dfs = get_all_phase2_properties()

    if len(dfs['incomplete_data']) == 0:
      console.print("[dim]All properties have complete data![/dim]")
    else:
        display_all_properties(console=console, properties_df=dfs["incomplete_data"], df=df, title="Need more data")

    if len(dfs['qualifiers']) == 0:
      console.print("[dim]No properties qualify[/dim]")
    else:
      display_all_properties(console=console, properties_df=dfs["qualifiers"], df=df, title="Phase 2 Qualifiers")

    if len(dfs["disqualifiers"]) == 0:
      console.print('[dim]No properties are disqualified[/dim]')
    else:
      display_all_properties(console=console, properties_df=dfs["disqualifiers"], df=df, title="Phase 2 Disqualifiers")


def display_all_properties_info(console, df, properties_df):
    """Display all properties with basic info: address, sqft, age, units, mobility scores, and electricity cost"""
    dataframe = df if properties_df is None else properties_df
    table = Table(
        title="Properties Basic Information",
        show_header=True,
        header_style="bold magenta",
    )

    built_75th_percentile = dataframe["built_in"].quantile(0.75, skipna=True)
    built_25th_percentile = dataframe["built_in"].quantile(0.25, skipna=True)
    sqft_75th_percentile = dataframe["square_ft"].quantile(0.75)
    sqft_25th_percentile = dataframe["square_ft"].quantile(0.25)
    walk_75th_percentile = dataframe["walk_score"].quantile(0.75)
    walk_25th_percentile = dataframe["walk_score"].quantile(0.25)
    transit_75th_percentile = dataframe["transit_score"].quantile(0.75)
    transit_25th_percentile = dataframe["transit_score"].quantile(0.25)
    bike_75th_percentile = dataframe["bike_score"].quantile(0.75)
    bike_25th_percentile = dataframe["bike_score"].quantile(0.25)
    elec_75th_percentile = dataframe["annual_electricity_cost_est"].quantile(0.75)
    elec_25th_percentile = dataframe["annual_electricity_cost_est"].quantile(0.25)

    table.add_column("Address", style="cyan", no_wrap=True)
    table.add_column("County", style="cyan", no_wrap=True)
    table.add_column("Schl Dst", style="cyan", no_wrap=True)
    table.add_column("Sqrft", justify="right", style="green")
    table.add_column("Built", justify="right", style="yellow")
    table.add_column("Units", justify="center", style="blue")
    table.add_column("Walk", justify="right", style="orange3")
    table.add_column("Transit", justify="right", style="orange3")
    table.add_column("Bike", justify="right", style="orange3")
    table.add_column("Elec.", justify="right", style="red")
    table.add_column("Listed", justify="right", style="white")
    table.add_column("Reduced Price?", justify="right", style="white")
    table.add_column("Has tenants?", justify="right", style="white")

    for _, row in dataframe.iterrows():
        units_value = int(row["units"])
        if units_value == 0:
            units_display = "SFH"
        elif units_value == 2:
            units_display = "duplex"
        elif units_value == 3:
            units_display = "triplex"
        elif units_value == 4:
            units_display = "fourplex"
        else:
            units_display = str(units_value)

        sqft_style = ("green" if row["square_ft"] >= sqft_75th_percentile else "yellow" if row["square_ft"] >= sqft_25th_percentile else "red")

        built_in_style = (
            "green"
            if pd.notna(row["home_age"]) and row["home_age"] <= built_25th_percentile
            else ("yellow" if pd.notna(row["home_age"]) and row["home_age"] <= built_75th_percentile else "red")
        )
        walk_style = (
            "green"
            if row["walk_score"] >= walk_75th_percentile
            else ("yellow" if row["walk_score"] >= walk_25th_percentile else "red")
        )

        transit_style = (
            "green"
            if row["transit_score"] >= transit_75th_percentile
            else ("yellow" if row["transit_score"] >= transit_25th_percentile else "red")
        )

        bike_style = (
            "green"
            if row["bike_score"] >= bike_75th_percentile
            else ("yellow" if row["bike_score"] >= bike_25th_percentile else "red")
        )

        elec_style = (
            "green"
            if row["annual_electricity_cost_est"] <= elec_25th_percentile
            else ("yellow" if row["annual_electricity_cost_est"] <= elec_75th_percentile else "red")
        )

        table.add_row(
            str(row["address1"]),
            row["county"],
            row["school_district"],
            f"[{sqft_style}]{int(row['square_ft']):,}[/{sqft_style}]",
            f"[{built_in_style}]{int(row['built_in']) if pd.notna(row['built_in']) else 'N/A'}[/{built_in_style}]",
            units_display,
            f"[{walk_style}]{int(row['walk_score'])}[/{walk_style}]",
            f"[{transit_style}]{int(row['transit_score'])}[/{transit_style}]",
            f"[{bike_style}]{int(row['bike_score'])}[/{bike_style}]",
            f"[{elec_style}]{format_currency(row['annual_electricity_cost_est'])}[/{elec_style}]",
            row['listed_date'] if pd.notna(row['listed_date']) else 'N/A',
            str(row["has_reduced_price"]),
            str(row["has_tenants"]),
        )

    console.print(table)


def display_phase1_total_rent_differences(console, get_combined_phase1_qualifiers):
    """
    Display comparison between quick rent estimate and detailed market estimate
    for Phase 1 properties.

    Green = market estimate higher (conservative quick estimate)
    Red = market estimate lower (optimistic quick estimate)
    """
    # Get Phase 1 qualifiers
    dataframe = get_combined_phase1_qualifiers(active=True)

    # Handle empty case
    if len(dataframe) == 0:
        console.print("[dim]No Phase 1 qualifying properties found[/dim]")
        return

    # Add calculated columns
    dataframe['rent_difference'] = dataframe['market_total_rent_estimate'] - dataframe['total_rent']
    dataframe['rent_difference_percent'] = dataframe.apply(
        lambda row: row['rent_difference'] / row['total_rent']
                    if pd.notna(row['total_rent']) and row['total_rent'] != 0
                    else 0,
        axis=1
    )

    dataframe['adjusted_cf'] = dataframe['monthly_cash_flow'] + dataframe['rent_difference']

    # Sort by percent difference descending (biggest positive differences first)
    dataframe = dataframe.sort_values(by='rent_difference_percent', ascending=False)

    # Create Rich table
    table = Table(
        title=f"Phase 1 Rent Estimate Comparison ({len(dataframe)} properties)",
        show_header=True,
        header_style="bold magenta"
    )

    # Add columns
    table.add_column("Address", style="cyan", no_wrap=False)
    table.add_column("Purchase Price", justify="right")
    table.add_column("Cash Needed", justify="right")
    table.add_column("Quick Estimate", justify="right")
    table.add_column("Market Estimate", justify="right")
    table.add_column("Difference", justify="right")
    table.add_column("Percent", justify="right")
    table.add_column("CF", justify="right")
    table.add_column('Adjusted CF', justify="right")

    # Iterate and add rows with color coding
    for _, row in dataframe.iterrows():
        diff_value = row['rent_difference']
        percent_value = row['rent_difference_percent']

        # Color code: green for positive, red for negative
        if diff_value > 0:
            diff_display = f"[green]{format_currency(diff_value)}[/green]"
            percent_display = f"[green]{format_percentage(percent_value)}[/green]"
        elif diff_value < 0:
            diff_display = f"[red]{format_currency(diff_value)}[/red]"
            percent_display = f"[red]{format_percentage(percent_value)}[/red]"
        else:
            diff_display = format_currency(diff_value)
            percent_display = format_percentage(percent_value)

        adj_cf_color = "green" if row['adjusted_cf'] > 0 else "red"
        cf_color = "green" if row['monthly_cash_flow'] > 0 else "red"

        table.add_row(
            str(row['address1']),
            format_currency(row['purchase_price']),
            format_currency(row['cash_needed']),
            format_currency(row['total_rent']),
            format_currency(row['market_total_rent_estimate']),
            diff_display,
            percent_display,
            f"[{cf_color}]{format_currency(row['monthly_cash_flow'])}[/{cf_color}]",
            f"[{adj_cf_color}]{format_currency(row['adjusted_cf'])}[/{adj_cf_color}]"
        )

    console.print(table)


def create_phase1_research_list_table(df, title):
    """Creates a simplified table for phase 1 tour list display with color styling"""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    # Add columns with short names
    table.add_column(f"Address ({len(df)})", style="cyan", no_wrap=False)
    table.add_column("Neighborhood", style="dim")
    table.add_column("CF", justify="right")
    table.add_column("Cash", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Type", justify="center")
    table.add_column("SqFt", justify="right")
    table.add_column("Config", justify="center")
    table.add_column("Cost/Inc", justify="right")

    # Calculate percentiles for price and cash_needed (for styling)
    price_25 = df['purchase_price'].quantile(0.25)
    price_75 = df['purchase_price'].quantile(0.75)
    cash_25 = df['cash_needed'].quantile(0.25)
    cash_75 = df['cash_needed'].quantile(0.75)

    # Calculate percentiles for new columns (for styling)
    cost_inc_25 = df['costs_to_income'].quantile(0.25)
    cost_inc_75 = df['costs_to_income'].quantile(0.75)

    # Add rows
    for _, row in df.iterrows():
        # Determine property type
        units = row['units']
        if units == 0:
            prop_type = "SFH"
        elif units == 2:
            prop_type = "Duplex"
        elif units == 3:
            prop_type = "Triplex"
        elif units == 4:
            prop_type = "Fourplex"
        else:
            prop_type = f"{units}U"

        beds = int(row['beds']) if pd.notna(row['beds']) else 0
        baths = int(row['baths']) if pd.notna(row['baths']) else 0
        config = f"{beds}BR/{baths}BA"

        cf_value = row['monthly_cash_flow']
        if cf_value < 0:
            cf_display = f"[red]{format_currency(cf_value)}[/red]"
        else:
            cf_display = f"[green]{format_currency(cf_value)}[/green]"

        cash_value = row['cash_needed']
        if cash_value <= cash_25:
            cash_display = f"[green]{format_currency(cash_value)}[/green]"
        elif cash_value <= cash_75:
            cash_display = f"[yellow]{format_currency(cash_value)}[/yellow]"
        else:
            cash_display = f"[red]{format_currency(cash_value)}[/red]"

        price_value = row['purchase_price']
        if price_value <= price_25:
            price_display = f"[green]{format_currency(price_value)}[/green]"
        elif price_value <= price_75:
            price_display = f"[yellow]{format_currency(price_value)}[/yellow]"
        else:
            price_display = f"[red]{format_currency(price_value)}[/red]"

        grade = row['neighborhood_letter_grade'] if pd.notna(row['neighborhood_letter_grade']) else 'N/A'
        neighborhood = row['neighborhood'] if pd.notna(row['neighborhood']) else 'N/A'
        neighborhood_display = f"{grade} - {neighborhood}"

        cost_inc_value = row['costs_to_income']
        if cost_inc_value <= cost_inc_25:
            cost_inc_display = f"[green]{format_percentage(cost_inc_value)}[/green]"
        elif cost_inc_value <= cost_inc_75:
            cost_inc_display = f"[yellow]{format_percentage(cost_inc_value)}[/yellow]"
        else:
            cost_inc_display = f"[red]{format_percentage(cost_inc_value)}[/red]"

        table.add_row(
            row['address1'],
            neighborhood_display,
            cf_display,
            cash_display,
            price_display,
            prop_type,
            f"{row['square_ft']}",
            config,
            cost_inc_display
        )

    return table


def display_phase1_research_list(console, get_phase1_research_list, get_combined_phase1_qualifiers):
    tour_list = get_phase1_research_list()
    all_qualifiers = get_combined_phase1_qualifiers()
    tour_addresses = tour_list['address1'].tolist()
    not_on_tour = all_qualifiers[~all_qualifiers['address1'].isin(tour_addresses)].copy()
    tour_list = tour_list.sort_values(by='neighborhood')
    not_on_tour = not_on_tour.sort_values(by='neighborhood')

    if len(tour_list) == 0:
        console.print("[dim]No properties on the tour list yet[/dim]\n")
    else:
        table1 = create_phase1_research_list_table(tour_list, "Phase 1 Tour List")
        console.print(table1)
        console.print()
    if len(not_on_tour) == 0:
        console.print("[dim]All qualifying properties are on the tour list[/dim]\n")
    else:
        table2 = create_phase1_research_list_table(not_on_tour, "Phase 1 Qualifying Properties - Not on Tour List")
        console.print(table2)
        console.print()


def display_property_metrics(console, df, get_combined_phase1_qualifiers, properties_df=None):
    dataframe = df if properties_df is None else properties_df
    console.print("\n[bold]Column Key:[/bold]")
    key_items = [
        ("ADDR", "Address", "Property location identifier", ""),
        ("P/DR", "Price Per Door", "Purchase price divided by number of units; measures value per unit", "(lower = better)"),
        ("R/SF", "Rent Per Sqft", "Monthly rent per square foot; indicates rent efficiency", "(higher = better)"),
        ("BRKE", "Break-Even Occupancy", "Minimum occupancy % needed to cover all expenses", "(lower = better)"),
        ("BRKV", "Break-Even Vacancy", "Maximum vacant days while still covering all expenses", "(higher = better)"),
        ("OER", "Operating Expense Ratio", "Operating expenses as % of revenue; measures efficiency", "(lower = better)"),
        ("EGI", "Effective Gross Income", "Total annual rental income after vacancy losses", "(higher = better)"),
        ("DYLD", "Debt Yield", "NOI divided by loan amount; measures lender risk", "(higher = better)"),
        ("DEPR", "Monthly Depreciation", "Tax deduction from property depreciation over 27.5 years", "(higher = better)"),
        ("TAXS", "Monthly Tax Savings", "Tax savings from depreciation and expense deductions", "(higher = better)"),
        ("ATCY1", "After-Tax Cash Flow Y1", "Monthly cash flow after tax benefits in Year 1", "(higher = better)"),
        ("ATCY2", "After-Tax Cash Flow Y2", "Monthly cash flow after tax benefits in Year 2", "(higher = better)"),
        ("FV10", "Future Value 10yr", "Estimated property value after 10 years of appreciation", "(higher = better)"),
        ("NP10", "Net Proceeds 10yr", "Cash from sale after closing costs, loan payoff, and taxes", "(higher = better)"),
        ("EM10", "Equity Multiple 10yr", "Total return as multiple of initial cash invested", "(higher = better)"),
        ("AR10", "Avg Annual Return 10yr", "Average yearly return percentage over 10 years", "(higher = better)"),
        ("ROE", "Return on Equity Y2", "Annual return on equity investment in Year 2", "(higher = better)"),
        ("LEVB", "Leverage Benefit", "Return boost from using debt financing vs all-cash purchase", "(higher = better)"),
        ("PAYB", "Payback Period", "Years needed to recover initial cash investment", "(lower = better)"),
        ("IR10", "IRR 10yr", "Internal rate of return accounting for cash flows and sale proceeds", "(higher = better)"),
        ("NPV10", "NPV 10yr", "Net present value at discount rate; answers: does this beat market returns?", "(positive = beats market)"),
        ("CFDN", "Cash Flow Y2 Downside 10%", "Monthly cash flow if rents drop 10%; tests resilience", "(positive = resilient)")
    ]

    for code, name, description, direction in key_items:
        direction_text = f" [yellow]{direction}[/yellow]" if direction else ""
        console.print(f"  [red]{code}[/red] - [bold]{name}[/bold]: [dim cyan]{description}[/dim cyan]{direction_text}")

    table = Table(title="Investment Metrics Comparison", show_header=True, header_style="bold magenta")
    table.add_column("ADDR", style="cyan")
    table.add_column("P/DR", justify="right")
    table.add_column("R/SF", justify="right")
    table.add_column("BRKE", justify="right")
    table.add_column("BRKV", justify="right")
    table.add_column("OER", justify="right")
    table.add_column("EGI", justify="right")
    table.add_column("DYLD", justify="right")
    table.add_column("DEPR", justify="right")
    table.add_column("TAXS", justify="right")
    table.add_column("ATCY1", justify="right")
    table.add_column("ATCY2", justify="right")
    table.add_column("FV10", justify="right")
    table.add_column("NP10", justify="right")
    table.add_column("EM10", justify="right")
    table.add_column("AR10", justify="right")
    table.add_column("ROE", justify="right")
    table.add_column("LEVB", justify="right")
    table.add_column("PAYB", justify="right")
    table.add_column("IR10", justify="right")
    table.add_column("NPV10", justify="right")
    table.add_column("CFDN", justify="right")

    # Calculate quintile colors for ALL properties
    color_map = calculate_quintile_colors_for_metrics(dataframe)

    phase1 = get_combined_phase1_qualifiers()
    not_phase1 = dataframe[~dataframe['address1'].isin(phase1['address1'])]

    def add_rows(given_table, given_df):
        for _, row in given_df.iterrows():
            address = row["address1"]

            # Helper function to apply color to a value
            def colorize(value, metric_name):
                color = color_map.get((address, metric_name), 'white')
                return f"[{color}]{value}[/{color}]"

            # Format values (same as before)
            payback_display = f"{row['payback_period_years']:.1f} yr" if row['payback_period_years'] != float('inf') else "Never"
            break_even_display = format_percentage(row["break_even_occupancy"]) if row["break_even_occupancy"] < 1 else "---"
            break_v_display = express_percent_as_months_and_days(row["break_even_vacancy"]) if row["break_even_occupancy"] < 1 else "---"

            # Add row with colored values
            given_table.add_row(
                str(address),
                colorize(format_currency(row['price_per_door']), 'price_per_door'),
                colorize(format_currency(row['rent_per_sqft']), 'rent_per_sqft'),
                colorize(break_even_display, 'break_even_occupancy'),
                colorize(break_v_display, 'break_even_vacancy'),
                colorize(format_percentage(row['oer']), 'oer'),
                colorize(format_currency(row['egi']), 'egi'),
                colorize(format_percentage(row['debt_yield']), 'debt_yield'),
                colorize(format_currency(row['monthly_depreciation']), 'monthly_depreciation'),
                colorize(format_currency(row['tax_savings_monthly']), 'tax_savings_monthly'),
                colorize(format_currency(row['mr_after_tax_cash_flow_y1']), 'mr_after_tax_cash_flow_y1'),
                colorize(format_currency(row['mr_after_tax_cash_flow_y2']), 'mr_after_tax_cash_flow_y2'),
                colorize(format_currency(row['future_value_10yr']), 'future_value_10yr'),
                colorize(format_currency(row['net_proceeds_10yr']), 'net_proceeds_10yr'),
                colorize(format_number(row['equity_multiple_10yr']), 'equity_multiple_10yr'),
                colorize(format_percentage(row['avg_annual_return_10yr'] / 100), 'avg_annual_return_10yr'),
                colorize(format_percentage(row['roe_y2']), 'roe_y2'),
                colorize(format_percentage(row['leverage_benefit']), 'leverage_benefit'),
                colorize(payback_display, 'payback_period_years'),
                colorize(format_percentage(row['irr_10yr']), 'irr_10yr'),
                colorize(format_currency(row['npv_10yr']), 'npv_10yr'),
                colorize(format_currency(row['cash_flow_y2_downside_10pct']), 'cash_flow_y2_downside_10pct')
            )

    table.add_row("[white]PHASE 1 QUALIFIERS[/white]")
    add_rows(given_table=table, given_df=phase1)
    table.add_section()
    table.add_row("[white]PHASE 1 DISQUALIFIED[/white]")
    add_rows(given_table=table, given_df=not_phase1)
    console.print(table)

def display_rent_estimates_comparison(
    property_id: str,
    estimates: dict,
    existing_estimates: dict,
    unit_configs: list,
    result_cost: float,
    selected_report_info: str,
    console,
) -> bool:
    """
    Display detailed comparison between current and new rent estimates.

    Returns True if user wants to update database, False otherwise.
    """
    estimates_table = Table(
        title=f"Rent Estimate Comparison for {property_id}",
        show_header=True,
        header_style="bold green",
    )
    estimates_table.add_column("Unit", style="cyan", width=6)
    estimates_table.add_column("Config", style="yellow", width=12)
    estimates_table.add_column("Current Rent", justify="right", style="white", width=12)
    estimates_table.add_column("New Primary", justify="right", style="green", width=12)
    estimates_table.add_column("New Range", justify="right", style="blue", width=15)
    estimates_table.add_column("Difference", justify="right", style="bold", width=12)
    estimates_table.add_column("Change %", justify="right", style="bold", width=10)

    total_current_primary = 0
    total_new_low = 0
    total_new_primary = 0
    total_new_high = 0

    for config in unit_configs:
        for unit in config["units"]:
            unit_num = unit["unit_num"]
            config_key = config["config_key"]
            base_name = f"unit_{unit_num}_{config_key}"

            new_low = estimates.get(f"{base_name}_rent_estimate_low", 0)
            new_primary = estimates.get(f"{base_name}_rent_estimate", 0)
            new_high = estimates.get(f"{base_name}_rent_estimate_high", 0)
            existing_data = existing_estimates.get(base_name, {})
            current_primary = existing_data.get("rent_estimate", 0)
            difference = new_primary - current_primary
            change_percent = (
                (difference / current_primary * 100) if current_primary > 0 else 0
            )
            total_current_primary += current_primary
            total_new_low += new_low
            total_new_primary += new_primary
            total_new_high += new_high

            config_display = f"{config['beds']}b{config['baths']}b"

            if difference > 0:
                diff_style = "green"
                diff_symbol = "+"
                change_style = "green"
                change_percent_formatted = f"+{change_percent:.1f}%"
            elif difference < 0:
                diff_style = "red"
                diff_symbol = ""
                change_style = "red"
                change_percent_formatted = f"{change_percent:.1f}%"
            else:
                diff_style = "white"
                diff_symbol = ""
                change_style = "white"
                change_percent_formatted = f"{change_percent:.1f}%"

            estimates_table.add_row(
                f"Unit {unit_num}",
                config_display,
                f"${current_primary:,.0f}",
                f"[bold]${new_primary:,.0f}[/bold]",
                f"${new_low:,.0f}-{new_high:,.0f}",
                f"[{diff_style}]{diff_symbol}${abs(difference):,.0f}[/{diff_style}]",
                f"[{change_style}]{change_percent_formatted}[/{change_style}]",
            )

    total_difference = total_new_primary - total_current_primary
    total_change_percent = (
        (total_difference / total_current_primary * 100)
        if total_current_primary > 0
        else 0
    )

    if total_difference > 0:
        total_diff_style = "green"
        total_diff_symbol = "+"
        total_change_style = "green"
        total_change_percent_formatted = f"+{total_change_percent:.1f}%"
    elif total_difference < 0:
        total_diff_style = "red"
        total_diff_symbol = ""
        total_change_style = "red"
        total_change_percent_formatted = f"{total_change_percent:.1f}%"
    else:
        total_diff_style = "white"
        total_diff_symbol = ""
        total_change_style = "white"
        total_change_percent_formatted = f"{total_change_percent:.1f}%"

    estimates_table.add_section()
    estimates_table.add_row(
        "[bold]TOTAL[/bold]",
        "[bold]All[/bold]",
        f"[bold]${total_current_primary:,.0f}[/bold]",
        f"[bold green]${total_new_primary:,.0f}[/bold green]",
        f"[bold]${total_new_low:,.0f}-{total_new_high:,.0f}[/bold]",
        f"[bold {total_diff_style}]{total_diff_symbol}${abs(total_difference):,.0f}[/bold {total_diff_style}]",
        f"[bold {total_change_style}]{total_change_percent_formatted}[/bold {total_change_style}]",
    )

    console.print("\n")
    console.print(estimates_table)

    range_amount = total_new_high - total_new_low
    range_percent = (
        (range_amount / total_new_primary * 100) if total_new_primary > 0 else 0
    )
    unit_count = sum(len(config["units"]) for config in unit_configs)

    console.print(
        Panel(
            f"[bold cyan]Rent Estimate Analysis Summary[/bold cyan]\n\n"
            f"Total Units Analyzed: {unit_count}\n"
            f"Current Total Rent: ${total_current_primary:,.0f}/month\n"
            f"New Total Range: ${total_new_low:,.0f} - ${total_new_high:,.0f}\n"
            f"New Primary Estimate: ${total_new_primary:,.0f}/month\n"
            f"Total Monthly Change: {total_diff_symbol}${abs(total_difference):,.0f} ({total_diff_symbol}{total_change_percent:.1f}%)\n"
            f"Range Spread: ${range_amount:,.0f} ({range_percent:.1f}%)\n"
            f"Based on Report: {selected_report_info[:50]}...\n"
            f"Generation Cost: ${result_cost:.4f}",
            title="Comparison Summary",
            border_style="cyan",
        )
    )

    console.print("\n")
    update_database = questionary.confirm(
        "Would you like to update the database with these new rent estimates?",
        default=False,
    ).ask()

    return update_database