from itertools import zip_longest
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
import pandas as pd
from helpers import (
    calculate_additional_room_rent,
    calculate_quintile_colors_for_metrics,
    express_percent_as_months_and_days,
    format_currency,
    format_number,
    format_percentage,
)

def get_higher_is_better_color(value, p40, p60):
    """Return color based on 40th/60th percentile (higher values = better = greener)"""
    if pd.isna(value) or value is None:
        return "dim white"
    if value >= p60:
        return "green"
    elif value >= p40:
        return "yellow"
    else:
        return "red"

def display_all_properties(
    console,
    df,
    properties_df,
    title,
    show_status=False,
    show_min_rent_data=False,
    show_prop_type=False,
    show_has_mr=False,
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
    coc_y1_40th = dataframe["CoC_y1"].quantile(0.40)
    coc_y1_60th = dataframe["CoC_y1"].quantile(0.60)
    coc_y2_40th = dataframe["CoC_y2"].quantile(0.40)
    coc_y2_60th = dataframe["CoC_y2"].quantile(0.60)

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
    table.add_column("CC %", justify="right")
    table.add_column("Costs/mo", justify="right", style="yellow")
    table.add_column("CF", justify="right", no_wrap=True)
    table.add_column("MR_CFY1", justify="right")
    table.add_column("MR_CFY2", justify="right")
    table.add_column("CoC_Y1", justify="right")
    table.add_column("CoC_Y2", justify="right")
    table.add_column("Cost/Inc", justify="right", style="bold white")
    table.add_column("MGR_PP", justify="right")
    table.add_column("OpEx_Rent", justify="right")
    table.add_column("DSCR", justify="right")
    table.add_column("NPV10", justify="right")

    if show_has_mr:
        table.add_column("Has MR", justify="center", style="bold white")

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
        
        def get_color(amount):
            return "green" if amount >= 0 else "red"

        mrcfy1 = row['mr_monthly_cash_flow_y1']
        mrcfy2 = row['mr_monthly_cash_flow_y2']
        coc_y1_style = get_higher_is_better_color(row["CoC_y1"], coc_y1_40th, coc_y1_60th)
        coc_y2_style = get_higher_is_better_color(row["CoC_y2"], coc_y2_40th, coc_y2_60th)

        row_args.extend(
            [
                f"[{price_style}]{format_currency(row['purchase_price'])}[/{price_style}]",
                f"[{cash_style}]{format_currency(row['cash_needed'])}[/{cash_style}]",
                f"[green]{format_percentage(row['closing_costs_prcnt'])}[/green]",
                format_currency(row["total_monthly_cost"]),
                f"[{cf_style}]{format_currency(row['monthly_cash_flow'])}[/{cf_style}]",
                f"[{get_color(mrcfy1)}]{format_currency(mrcfy1)}[/{get_color(mrcfy1)}]",
                f"[{get_color(mrcfy2)}]{format_currency(mrcfy2)}[/{get_color(mrcfy2)}]",
                f"[{coc_y1_style}]{format_percentage(row['CoC_y1'])}[/{coc_y1_style}]",
                f"[{coc_y2_style}]{format_percentage(row['CoC_y2'])}[/{coc_y2_style}]",
                f"[{costs_to_income_style}]{format_percentage(row['costs_to_income'])}[/{costs_to_income_style}]",
                f"{format_percentage(row["MGR_PP"])}",
                f"{format_percentage(row["OpEx_Rent"])}",
                f"{format_percentage(row["DSCR"])}",
                f"{format_currency(row["npv_10yr"])}"
            ]
        )

        if show_has_mr:
            color = "green" if row['has_market_research'] else "red"
            row_args.append(f"[{color}]{"YES" if row['has_market_research'] else "NO"}[/{color}]")

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

def display_phase0_qualifiers_lacking_research(console, dataframe):
    """Display Phase 0 qualifying properties that lack market research data."""
    # Handle empty dataframe case
    if len(dataframe) == 0:
        console.print("[dim]All Phase 0 properties have market research![/dim]")
        return

    # Create table
    table = Table(
        title="Phase 0 Qualifiers - Need Market Research",
        show_header=True,
        header_style="bold magenta"
    )

    # Add columns
    table.add_column("Address", style="cyan", no_wrap=True)
    table.add_column("Purchase Price", justify="right")
    table.add_column("Monthly CF", justify="right")
    table.add_column("MR CF Y1", justify="right")
    table.add_column("MR CF Y2", justify="right")

    # Add rows
    for _, row in dataframe.iterrows():
        # Determine cash flow color
        cf_style = "red" if row["monthly_cash_flow"] < 0 else "green"

        # Build row with formatted values
        table.add_row(
            str(row["address1"]),
            format_currency(row["purchase_price"]),
            f"[{cf_style}]{format_currency(row['monthly_cash_flow'])}[/{cf_style}]",
            "[yellow]Missing[/yellow]",
            "[yellow]Missing[/yellow]"
        )

    console.print(table)

def display_all_phase1_qualifying_properties(console, df, current, contingent, creative, phase0_df):
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

    display_phase0_qualifiers_lacking_research(console, phase0_df)


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
    dataframe = get_combined_phase1_qualifiers()

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
    table.add_column("MRCF1", justify="right")
    table.add_column("MRCF2", justify="right")
    table.add_column("Cash", justify="right")
    table.add_column("Price", justify="right")
    table.add_column("Est Value", justify="right")
    table.add_column("Type", justify="center")
    table.add_column("Qual", justify="center")
    table.add_column("Status", justify="center")
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
    est_price_25 = df['est_price'].quantile(0.25)
    est_price_75 = df['est_price'].quantile(0.75)

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

        mrcf1_value = row['mr_monthly_cash_flow_y1']
        if mrcf1_value < 0:
            mrcf1_value = f"[red]{format_currency(mrcf1_value)}[/red]"
        else:
            mrcf1_value = f"[green]{format_currency(mrcf1_value)}[/green]"
        
        mrcf2_value = row["mr_monthly_cash_flow_y2"]
        if mrcf2_value < 0:
            mrcf2_value = f"[red]{format_currency(mrcf2_value)}[/red]"
        else:
            mrcf2_value = f"[green]{format_currency(mrcf2_value)}[/green]"

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

        est_price_value = row.get('est_price')
        if pd.notna(est_price_value) and est_price_value > 0:
            if est_price_value >= est_price_75:
                est_price_display = f"[green]{format_currency(est_price_value)}[/green]"
            elif est_price_value >= est_price_25:
                est_price_display = f"[yellow]{format_currency(est_price_value)}[/yellow]"
            else:
                est_price_display = f"[red]{format_currency(est_price_value)}[/red]"
        else:
            est_price_display = "N/A"

        grade = row['neighborhood_letter_grade'] if pd.notna(row['neighborhood_letter_grade']) else 'N/A'
        niche_grade = row['niche_com_letter_grade'] if pd.notna(row['niche_com_letter_grade']) else 'N/A'
        neighborhood = row['neighborhood'] if pd.notna(row['neighborhood']) else 'N/A'
        neighborhood_display = f"{grade}/{niche_grade} - {neighborhood}"

        cost_inc_value = row['costs_to_income']
        if cost_inc_value <= cost_inc_25:
            cost_inc_display = f"[green]{format_percentage(cost_inc_value)}[/green]"
        elif cost_inc_value <= cost_inc_75:
            cost_inc_display = f"[yellow]{format_percentage(cost_inc_value)}[/yellow]"
        else:
            cost_inc_display = f"[red]{format_percentage(cost_inc_value)}[/red]"

        # Format qualification type
        qual_type = row.get('qualification_type', '')
        if qual_type == 'current':
            qual_type_display = "CUR"
        elif qual_type == 'contingent':
            qual_type_display = "CON"
        elif qual_type == 'creative':
            qual_type_display = "CRE"
        else:
            qual_type_display = qual_type

        # Format status
        status = row.get('status', '')
        if status == 'pending sale':
            status_display = "pending"
        else:
            status_display = status

        table.add_row(
            row['address1'],
            neighborhood_display,
            cf_display,
            mrcf1_value,
            mrcf2_value,
            cash_display,
            price_display,
            est_price_display,
            prop_type,
            qual_type_display,
            status_display,
            f"{row['square_ft']}",
            config,
            cost_inc_display
        )

    return table


def display_phase1_research_list(console, qualified_df, unqualified_df):
    tour_list = qualified_df.sort_values(by='neighborhood')
    not_on_tour = unqualified_df.sort_values(by='neighborhood')

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
                colorize(format_currency(row['after_tax_cash_flow_y1']), 'after_tax_cash_flow_y1'),
                colorize(format_currency(row['after_tax_cash_flow_y2']), 'after_tax_cash_flow_y2'),
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
):
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


def display_property_value_comparison(console, properties_data):
    """
    Display property value comparison table with purchase price vs estimated price.

    Args:
        console: Rich Console instance
        properties_data: List of dicts with keys: address1, purchase_price, est_price, est_price_low, est_price_high
    """
    if not properties_data:
        console.print("[dim]No property data to display[/dim]")
        return

    # Calculate differences and sort by absolute percent difference
    for prop in properties_data:
        purchase_price = prop.get('purchase_price', 0)
        est_price = prop.get('est_price', 0)

        if purchase_price and purchase_price > 0 and est_price and est_price > 0:
            prop['difference_dollar'] = est_price - purchase_price
            prop['difference_percent'] = (est_price - purchase_price) / purchase_price
            prop['abs_difference_percent'] = abs(prop['difference_percent'])
        else:
            prop['difference_dollar'] = None
            prop['difference_percent'] = None
            prop['abs_difference_percent'] = 0

    # Sort by largest absolute percent difference first
    sorted_data = sorted(properties_data, key=lambda x: x['abs_difference_percent'], reverse=True)

    # Create Rich table
    table = Table(
        title=f"Property Value Comparison ({len(sorted_data)} properties)",
        show_header=True,
        header_style="bold magenta"
    )

    # Add columns
    table.add_column("Address", style="cyan", no_wrap=False)
    table.add_column("Purchase Price", justify="right")
    table.add_column("Est Price", justify="right")
    table.add_column("Est Range", justify="right", style="dim")
    table.add_column("Difference $", justify="right")
    table.add_column("Difference %", justify="right")

    # Add rows
    for prop in sorted_data:
        address = prop.get('address1', 'N/A')
        purchase_price = prop.get('purchase_price', 0)
        est_price = prop.get('est_price', 0)
        est_price_low = prop.get('est_price_low', 0)
        est_price_high = prop.get('est_price_high', 0)
        difference_dollar = prop.get('difference_dollar')
        difference_percent = prop.get('difference_percent')

        # Format purchase price
        if purchase_price and purchase_price > 0:
            purchase_display = format_currency(purchase_price)
        else:
            purchase_display = "N/A"

        # Format estimated price
        if est_price and est_price > 0:
            est_display = format_currency(est_price)
        else:
            est_display = "N/A"

        # Format range
        if est_price_low and est_price_high:
            range_display = f"{format_currency(est_price_low)} - {format_currency(est_price_high)}"
        else:
            range_display = "N/A"

        # Format differences with color coding
        if difference_dollar is not None and difference_percent is not None:
            # Positive difference = estimated price > purchase price (green)
            # Negative difference = estimated price < purchase price (red)
            if difference_dollar > 0:
                diff_dollar_display = f"[green]+{format_currency(difference_dollar)}[/green]"
                diff_percent_display = f"[green]+{format_percentage(difference_percent)}[/green]"
            elif difference_dollar < 0:
                diff_dollar_display = f"[red]{format_currency(difference_dollar)}[/red]"
                diff_percent_display = f"[red]{format_percentage(difference_percent)}[/red]"
            else:
                diff_dollar_display = format_currency(0)
                diff_percent_display = format_percentage(0)
        else:
            diff_dollar_display = "N/A"
            diff_percent_display = "N/A"

        table.add_row(
            address,
            purchase_display,
            est_display,
            range_display,
            diff_dollar_display,
            diff_percent_display
        )

    console.print("\n")
    console.print(table)


def display_property_details(console, property_details):
    """Display property details in a panel for confirmation"""
    text = ""
    for key in property_details:
        text += f"{key}: {property_details[key]}\n"
    console.print(
        Panel(text, title="Property Details", title_align="center", padding=1)
    )


def display_unit_configs(console, rent_comps):
    """Display unit configurations in a table for confirmation"""
    table = Table(title="Rent Comparables")
    table.add_column("Unit #")
    table.add_column("Configuration", no_wrap=True)
    for comp in rent_comps:
        configuration = f"{comp["beds"]}-beds {comp["baths"]}-baths"
        table.add_row(str(comp["unit_num"]), configuration)
    console.print(table)


def display_property_overview_panel(console, row):
    """
    Display property overview panel with basic information.

    Args:
        console: Rich Console instance
        row: DataFrame row containing property data
    """
    units_value = int(row['units'])
    if units_value == 0:
        property_type_display = "Type: Single Family (Room Rental)"
    elif units_value == 2:
        property_type_display = "Type: Duplex"
    elif units_value == 3:
        property_type_display = "Type: Triplex"
    elif units_value == 4:
        property_type_display = "Type: Fourplex"
    else:
        property_type_display = f"Units: {units_value}"

    console.print(Panel(f"[bold cyan]Property Overview[/bold cyan]\n"
                      f"Address: {row['full_address']}\n"
                      f"Purchase Price: {format_currency(row['purchase_price'])}\n"
                      f"Bedrooms: {int(row['beds'])} | Bathrooms: {int(row['baths'])} | Sq Ft: {format_number(row['square_ft'])}\n"
                      f"Built: {int(row['built_in']) if pd.notna(row['built_in']) else 'N/A'} (Age: {int(row['home_age']) if pd.notna(row['home_age']) else 'N/A'} years)\n"
                      f"{property_type_display}\n"
                      f"Cost per Sq Ft: {format_currency(row['cost_per_sqrft'])}\n"
                      f"Neighborhood: {row['neighborhood']} (rated: {row['neighborhood_letter_grade']})",
                      title="Basic Info"))


def display_property_rent_estimates_table(console, property_rents, is_single_family):
    """
    Display rent estimates table showing unit/room configurations and rents.

    Args:
        console: Rich Console instance
        property_rents: DataFrame subset of rents for this property
        is_single_family: Boolean indicating if property is SFH (affects labels)
    """
    your_unit_index = property_rents['rent_estimate'].idxmin()

    # Use contextual labels for single family vs multi-family
    table_title = "Room Rent Estimates" if is_single_family else "Unit Rent Estimates"
    unit_label = "Room" if is_single_family else "Unit"
    your_unit_label = "[bold red]Your Room[/bold red]" if is_single_family else "[bold red]Your Unit[/bold red]"

    rent_table = Table(title=table_title, show_header=True, header_style="bold green")
    rent_table.add_column(unit_label, style="cyan", justify="center")
    rent_table.add_column("Configuration", style="yellow")
    rent_table.add_column("Monthly Rent", justify="right", style="green")
    rent_table.add_column("Status", style="magenta")

    total_monthly_rent = 0
    for idx, rent_row in property_rents.iterrows():
        is_your_unit = idx == your_unit_index
        unit_config = f"{int(rent_row['beds'])}-bed {int(rent_row['baths'])}-bath"
        status = your_unit_label if is_your_unit else "Rental"
        rent_style = "bold red" if is_your_unit else "green"

        rent_table.add_row(
            str(int(rent_row['unit_num'])),
            unit_config,
            f"[{rent_style}]{format_currency(rent_row['rent_estimate'])}[/{rent_style}]",
            status
        )
        total_monthly_rent += rent_row['rent_estimate']

    rent_table.add_row(
        "[bold]Total[/bold]",
        "",
        f"[bold blue]{format_currency(total_monthly_rent)}[/bold blue]",
        ""
    )

    console.print(rent_table)


def display_property_investment_metrics_table(console, row, is_single_family):
    """
    Display comprehensive investment metrics table with all financial calculations.

    Args:
        console: Rich Console instance
        row: DataFrame row containing all calculated property metrics
        is_single_family: Boolean indicating if property is SFH (affects some displays)
    """
    table = Table(title=f"Property Details: {row['address1']}", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="yellow", no_wrap=True)
    table.add_column("Quick Estimate", justify="right", style="cyan")
    table.add_column("MR Year 1 (Live-in)", justify="right", style="green")
    table.add_column("MR Year 2 (All Rent)", justify="right", style="blue")
    table.add_column("", style="dim white", no_wrap=True)  # Separator/Investment Metric column
    table.add_column("5Y", justify="right", style="magenta")
    table.add_column("10Y", justify="right", style="bright_magenta")
    table.add_column("20Y", justify="right", style="bright_cyan")

    if is_single_family:
        # For single family homes, update table title to clarify the comparison
        table.title = f"Investment Metrics: {row['address1']}"
        table.columns[1].header = "Quick Estimate"
        table.columns[2].header = "MR Year 1 (House Hacking)"
        table.columns[3].header = "MR Year 2 (Full Rental)"

    # Add cost breakdown rows at the top (with investment projections on the right)
    table.add_row("Mortgage Payment",
                  format_currency(row['monthly_mortgage']),
                  format_currency(row['monthly_mortgage']),
                  format_currency(row['monthly_mortgage']),
                  "Investment Gain",
                  format_currency(row['5y_forecast']),
                  format_currency(row['10y_forecast']),
                  format_currency(row['20y_forecast']))
    table.add_row("MIP (Insurance)",
                  format_currency(row['monthly_mip']),
                  format_currency(row['monthly_mip']),
                  format_currency(row['monthly_mip']),
                  "Future Value",
                  format_currency(row['future_value_5yr']),
                  format_currency(row['future_value_10yr']),
                  format_currency(row['future_value_20yr']))
    table.add_row("Property Taxes",
                  format_currency(row['monthly_taxes']),
                  format_currency(row['monthly_taxes']),
                  format_currency(row['monthly_taxes']),
                  "Net Proceeds",
                  format_currency(row['net_proceeds_5yr']),
                  format_currency(row['net_proceeds_10yr']),
                  format_currency(row['net_proceeds_20yr']))
    table.add_row("Home Insurance",
                  format_currency(row['monthly_insurance']),
                  format_currency(row['monthly_insurance']),
                  format_currency(row['monthly_insurance']),
                  "Equity Multiple",
                  format_number(row['equity_multiple_5yr']),
                  format_number(row['equity_multiple_10yr']),
                  format_number(row['equity_multiple_20yr']))
    table.add_row("Vacancy Reserve",
                  format_currency(row['monthly_vacancy_costs']),
                  format_currency(row['mr_monthly_vacancy_costs']),
                  format_currency(row['mr_monthly_vacancy_costs']),
                  "Avg Annual Return %",
                  format_percentage(row['avg_annual_return_5yr'] / 100),
                  format_percentage(row['avg_annual_return_10yr'] / 100),
                  format_percentage(row['avg_annual_return_20yr'] / 100))
    table.add_row("Repair Reserve",
                  format_currency(row['monthly_repair_costs']),
                  format_currency(row['mr_monthly_repair_costs']),
                  format_currency(row['mr_monthly_repair_costs']),
                  "IRR",
                  format_percentage(row['irr_5yr']),
                  format_percentage(row['irr_10yr']),
                  format_percentage(row['irr_20yr']))
    table.add_row("[bold]Total Monthly Cost[/bold]",
                  f"[bold red]{format_currency(row['total_monthly_cost'])}[/bold red]",
                  f"[bold red]{format_currency(row['mr_total_monthly_cost'])}[/bold red]",
                  f"[bold red]{format_currency(row['mr_total_monthly_cost'])}[/bold red]",
                  "NPV",
                  format_currency(row['npv_5yr']),
                  format_currency(row['npv_10yr']),
                  format_currency(row['npv_20yr']))

    # Add common comparison rows
    table.add_row("Annual Rent",
                  format_currency(row['annual_rent']),
                  format_currency(row['mr_annual_rent_y1']),
                  format_currency(row['mr_annual_rent_y2']),
                  "Fair Value",
                  format_currency(row['fair_value_5yr']),
                  format_currency(row['fair_value_10yr']),
                  format_currency(row['fair_value_20yr']))

    table.add_row("Monthly Rent",
                  format_currency(row['total_rent']),
                  format_currency(row['mr_net_rent_y1']) + " (net)" if not is_single_family else format_currency(row['mr_net_rent_y1']),
                  format_currency(row['y2_rent_base']),
                  "Value Gap %",
                  format_percentage(row['value_gap_pct_5yr'] / 100),
                  format_percentage(row['value_gap_pct_10yr'] / 100),
                  format_percentage(row['value_gap_pct_20yr'] / 100))

    table.add_row("Operating Expenses",
                  format_currency(row['operating_expenses']),
                  format_currency(row['mr_operating_expenses']),
                  format_currency(row['mr_operating_expenses']),
                  "", "", "", "")

    # Utilities Breakdown
    table.add_row("",
                  "", "", "", "", "", "", "")  # Blank separator row

    table.add_row("[bold]Utilities Breakdown:[/bold]",
                  "", "", "", "", "", "", "")

    table.add_row("  Electric",
                  format_currency(row['monthly_utility_electric']),
                  format_currency(row['monthly_utility_electric']),
                  format_currency(row['monthly_utility_electric']),
                  "", "", "", "")

    table.add_row("  Gas",
                  format_currency(row['monthly_utility_gas']),
                  format_currency(row['monthly_utility_gas']),
                  format_currency(row['monthly_utility_gas']),
                  "", "", "", "")

    table.add_row("  Water/Sewer",
                  format_currency(row['monthly_utility_water']),
                  format_currency(row['monthly_utility_water']),
                  format_currency(row['monthly_utility_water']),
                  "", "", "", "")

    table.add_row("  Trash",
                  format_currency(row['monthly_utility_trash']),
                  format_currency(row['monthly_utility_trash']),
                  format_currency(row['monthly_utility_trash']),
                  "", "", "", "")

    table.add_row("  Internet",
                  format_currency(row['monthly_utility_internet']),
                  format_currency(row['monthly_utility_internet']),
                  format_currency(row['monthly_utility_internet']),
                  "", "", "", "")

    table.add_row("[bold]Total Utilities[/bold]",
                  f"[bold]{format_currency(row['monthly_utility_total'])}[/bold]",
                  f"[bold]{format_currency(row['monthly_utility_total'])}[/bold]",
                  f"[bold]{format_currency(row['monthly_utility_total'])}[/bold]",
                  "", "", "", "")

    table.add_row("  Roommate Contribution",
                  f"[green]+{format_currency(row['roommate_utilities'])}[/green]",
                  f"[green]+{format_currency(row['roommate_utilities_y1'])}[/green]",
                  f"[green]+{format_currency(row['roommate_utilities_y2'])}[/green]",
                  "", "", "", "")

    table.add_row("  Owner Pays",
                  format_currency(row['owner_utilities']),
                  format_currency(row['owner_utilities_y1']),
                  format_currency(row['owner_utilities_y2']),
                  "", "", "", "")

    table.add_row("",
                  "", "", "", "", "", "", "")  # Blank separator row

    table.add_row("[bold]Monthly Cash Flow[/bold]",
                  f"[bold {'red' if row['monthly_cash_flow'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow'])}[/]",
                  f"[bold {'red' if row['mr_monthly_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['mr_monthly_cash_flow_y1'])}[/]",
                  f"[bold {'red' if row['mr_monthly_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['mr_monthly_cash_flow_y2'])}[/]",
                  "", "", "", "")
    table.add_row("[bold]Annual Cash Flow[/bold]",
                  f"[bold {'red' if row['annual_cash_flow'] < 0 else 'green'}]{format_currency(row['annual_cash_flow'])}[/]",
                  f"[bold {'red' if row['mr_annual_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['mr_annual_cash_flow_y1'])}[/]",
                  f"[bold {'red' if row['mr_annual_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['mr_annual_cash_flow_y2'])}[/]",
                  "", "", "", "")
    table.add_row("Amortization Percent",
                  format_percentage(row['ammoritization_estimate'] / row['monthly_mortgage']),
                  "-",
                  "-",
                  "", "", "", "")
    table.add_row("Amortization $ Applied",
                  format_currency(row['ammoritization_estimate']),
                  "-",
                  "-",
                  "", "", "", "")
    table.add_row("Monthly NOI",
                  "",
                  format_currency(row['mr_monthly_NOI_y1']),
                  format_currency(row['mr_monthly_NOI_y2']),
                  "", "", "", "")
    table.add_row("Annual NOI",
                  "",
                  format_currency(row['mr_annual_NOI_y1']),
                  format_currency(row['mr_annual_NOI_y2']),
                  "", "", "", "")
    table.add_row("After-Tax Cash Flow",
                  "",
                  format_currency(row['after_tax_cash_flow_y1']),
                  format_currency(row['after_tax_cash_flow_y2']),
                  "", "", "", "")
    table.add_row("Cap Rate",
                  "",
                  format_percentage(row['cap_rate_y1']),
                  format_percentage(row['cap_rate_y2']),
                  "", "", "", "")
    table.add_row("Cash on Cash Return",
                  "",
                  format_percentage(row['CoC_y1']),
                  format_percentage(row['CoC_y2']),
                  "", "", "", "")
    table.add_row("Gross Rent Multiplier",
                  "",
                  format_number(row['GRM_y1']),
                  format_number(row['GRM_y2']),
                  "", "", "", "")

    downside_y1_style = "green" if row['cash_flow_y1_downside_10pct'] > 0 else "red"
    downside_y2_style = "green" if row['cash_flow_y2_downside_10pct'] > 0 else "red"
    table.add_row("Cash Flow (10% Rent Drop)",
                  "",
                  f"[{downside_y1_style}]{format_currency(row['cash_flow_y1_downside_10pct'])}[/{downside_y1_style}]",
                  f"[{downside_y2_style}]{format_currency(row['cash_flow_y2_downside_10pct'])}[/{downside_y2_style}]",
                  "", "", "", "")

    # Industry-standard metrics (primarily Y2-based for SFH)
    mgr_pp_style = "green" if row['MGR_PP'] >= 0.01 else "red"
    opex_rent_style = "green" if 0.45 <= row['OpEx_Rent'] <= 0.55 else ("yellow" if 0.35 <= row['OpEx_Rent'] <= 0.65 else "red")
    dscr_style = "green" if row['DSCR'] >= 1.25 else "red"
    fha_style = "green" if row["fha_self_sufficiency_ratio"] >= 1 else "red"

    if is_single_family:
        # For SFH, show OER and break-even for both years
        oer_quick = row['operating_expenses'] / row['total_rent'] if row['total_rent'] > 0 else 0
        oer_y1 = row['mr_operating_expenses'] / row['total_rent'] if row['total_rent'] > 0 else 0
        break_even_quick = row['total_monthly_cost'] / row['total_rent'] if row['total_rent'] > 0 else 0
        break_even_y1 = row['mr_total_monthly_cost'] / row['total_rent'] if row['total_rent'] > 0 else 0
        oer_quick_style = "green" if 0.45 <= oer_quick <= 0.55 else ("yellow" if 0.35 <= oer_quick <= 0.65 else "red")
        oer_y1_style = "green" if 0.45 <= oer_y1 <= 0.55 else ("yellow" if 0.35 <= oer_y1 <= 0.65 else "red")

        table.add_row("Operating Expense Ratio",
                      f"[{oer_quick_style}]{format_percentage(oer_quick)}[/{oer_quick_style}]",
                      f"[{oer_y1_style}]{format_percentage(oer_y1)}[/{oer_y1_style}]",
                      f"[{opex_rent_style}]{format_percentage(row['oer'])}[/{opex_rent_style}]",
                      "", "", "", "")
        table.add_row("Break-Even Occupancy",
                      format_percentage(break_even_quick),
                      format_percentage(break_even_y1),
                      format_percentage(row['break_even_occupancy']),
                      "", "", "", "")
    else:
        table.add_row("Operating Expense Ratio","","",f"[{opex_rent_style}]{format_percentage(row['oer'])}[/{opex_rent_style}]","","","","")
        table.add_row("Break-Even Occupancy","","",format_percentage(row['break_even_occupancy']),"","","","")

    table.add_row("1% Rule (MGR/PP)","","",f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]","","","","")
    table.add_row("50% Rule (OpEx/Rent)","","",f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]","","","","")
    table.add_row("DSCR (Rent/Mortgage)","","",f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]","","","","")
    table.add_row("FHA Self Sufficiency Ratio","","",f"[{fha_style}]{format_percentage(row['fha_self_sufficiency_ratio'])}[/{fha_style}]","","","","")
    table.add_row("Rent Per Sqft","","",format_currency(row['rent_per_sqft']),"","","","")
    table.add_row("Break-Even Vacancy","","",express_percent_as_months_and_days(row["break_even_vacancy"]),"","","","")
    table.add_row("Effective Gross Income","","",format_currency(row['egi']),"","","","")
    table.add_row("Debt Yield","","",format_percentage(row['debt_yield']),"","","","")
    table.add_row("LTV Ratio","","",format_percentage(row['ltv_ratio']),"","","","")
    price_per_label = "Price Per Bedroom" if is_single_family else "Price Per Door"
    table.add_row(price_per_label,"","",format_currency(row['price_per_door']),"","","","")
    table.add_row("Monthly Depreciation Deduction","","",format_currency(row['monthly_depreciation']),"","","","")
    table.add_row("Monthly Tax Savings","","",format_currency(row['tax_savings_monthly']),"","","","")
    table.add_row("Return on Equity (ROE) Y2","","",format_percentage(row['roe_y2']),"","","","")
    table.add_row("Leverage Benefit","","",format_percentage(row['leverage_benefit']),"","","","")
    payback_display = f"{row['payback_period_years']:.1f} years" if row['payback_period_years'] != float('inf') else "Never"
    table.add_row("Payback Period","","",payback_display,"","","","")
    console.print(table)


def display_investment_requirements_panel(console, row, assumptions, loan):
    """
    Display investment requirements panel showing upfront cash needed.

    Args:
        console: Rich Console instance
        row: DataFrame row containing property financial data
        assumptions: ASSUMPTIONS dict with ia_fhb_prog settings
        loan: LOAN dict with upfront_discounts
    """
    investment_summary = (
        f"[bold green]Investment Summary[/bold green]\n"
        f"Down Payment: {format_currency(row['down_payment'])}\n"
        f"Closing Costs: {format_currency(row['closing_costs'])}\n"
        f"Lender Discounts: {format_currency(loan['upfront_discounts'])}\n"
        f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
        f"Loan Amount: {format_currency(row['loan_amount'])}\n"
        f"[bold green]Purchase Price: {format_currency(row['purchase_price'])}[/bold green]"
    )

    if assumptions['using_ia_fhb_prog'] and assumptions['ia_fhb_prog_upfront_option'] == "LOAN" and row["units"] == 0:
        investment_summary += (
            f"\n\n[bold yellow]Iowa First-Time Homebuyer Program:[/bold yellow]\n"
            f"5% Forgivable Loan: {format_currency(row['5_pct_loan'])}\n"
            f"Primary Mortgage: {format_currency(row['loan_amount'])}\n"
            f"Total Financing: {format_currency(row['loan_amount'] + row['5_pct_loan'])}\n"
            f"[dim](5% loan due at sale or refinance)[/dim]"
        )

    console.print(Panel(investment_summary, title="Investment Requirements"))

def display_homestyle_overview_panel(console, row):
    """
    Display Fannie Mae HomeStyle Renovation loan overview for a property.

    Args:
        console: Rich console instance
        row: Property DataFrame row with HomeStyle calculations
    """
    # Extract values
    purchase_price = row.get("purchase_price", 0)
    renovation_cost = row.get("hs_renovation_cost", 0)
    total_project_cost = row.get("hs_total_project_cost", 0)
    arv = row.get("hs_arv", 0)
    max_loan = row.get("hs_max_loan_amount", 0)
    cash_needed = row.get("hs_cash_needed", 0)
    built_in_equity = row.get("hs_built_in_equity", 0)
    equity_pct = row.get("hs_equity_pct", 0)
    renovation_roi = row.get("hs_renovation_roi", 0)
    is_feasible = row.get("hs_is_feasible", False)
    deal_score = row.get("hs_deal_score", 0)
    condition_score = row.get("property_condition_score", 3)

    # Color coding
    equity_color = "green" if equity_pct > 0.15 else "yellow" if equity_pct > 0.05 else "red"
    roi_color = "green" if renovation_roi > 1.3 else "yellow" if renovation_roi > 1.1 else "red"
    score_color = "green" if deal_score > 60 else "yellow" if deal_score > 40 else "red"
    feasibility_text = "[green]✓ Feasible[/green]" if is_feasible else "[red]✗ Not Feasible[/red]"

    # Condition score description
    condition_map = {
        1: "Complete Overhaul",
        2: "Heavy Renovation",
        3: "Moderate Updates",
        4: "Cosmetic Refresh",
        5: "Minor Touchups"
    }
    condition_desc = condition_map.get(int(condition_score), "Unknown")

    # Color coding for borrowing gap
    borrowing_gap = row.get("hs_borrowing_gap", 0)
    gap_color = "green" if borrowing_gap == 0 else "yellow" if borrowing_gap < 10000 else "red"

    # Calculate financing coverage percentage
    reno_financed = row.get("hs_max_renovation_financing", 0)
    financing_coverage = (reno_financed / renovation_cost * 100) if renovation_cost > 0 else 0

    panel_content = f"""
[bold cyan]Fannie Mae HomeStyle Renovation Loan Analysis - Primary Residence (97% LTV)[/bold cyan]

[bold]Property Condition:[/bold]
  Condition Score:       {int(condition_score)} - {condition_desc}

[bold]Project Costs:[/bold]
  Purchase Price:        {format_currency(purchase_price)}
  Renovation Cost:       {format_currency(renovation_cost)}
  Total Project Cost:    {format_currency(total_project_cost)}

[bold]After Repair Value (ARV):[/bold]
  Estimated ARV:         {format_currency(arv)}
  ARV per Sqft:          {format_currency(row.get("hs_arv_per_sqft", 0))}

[bold]Loan Details:[/bold]
  Max Loan Amount:       {format_currency(max_loan)}
  LTV Ratio:             97.0%
  Down Payment (3%):     {format_currency(row.get("hs_down_payment", 0))}

[bold]Renovation Financing Breakdown:[/bold]
  Total Renovation:      {format_currency(renovation_cost)}
  Amount Financed:       {format_currency(reno_financed)}
  Out-of-Pocket Reno:    {format_currency(row.get("hs_out_of_pocket_renovation", 0))}
  Financing Coverage:    {financing_coverage:.1f}%

[bold]Total Cash Requirements:[/bold]
  Down Payment:          {format_currency(row.get("hs_down_payment", 0))}
  Out-of-Pocket Reno:    {format_currency(row.get("hs_out_of_pocket_renovation", 0))}
  ─────────────────────────────────────
  Total Cash Needed:     {format_currency(cash_needed)}
  Borrowing Gap:         [{gap_color}]{format_currency(borrowing_gap)}[/{gap_color}]

[bold]Value Creation:[/bold]
  Built-in Equity:       [{equity_color}]{format_currency(built_in_equity)}[/{equity_color}]
  Equity %:              [{equity_color}]{format_percentage(equity_pct)}[/{equity_color}]
  Renovation ROI:        [{roi_color}]{renovation_roi:.2f}x[/{roi_color}]
  Value Add:             {format_currency(row.get("hs_renovation_value_add", 0))}

[bold]Deal Assessment:[/bold]
  Deal Score:            [{score_color}]{deal_score:.1f}/100[/{score_color}]
  Feasibility:           {feasibility_text}
"""

    console.print(Panel(
        panel_content,
        title=f"🏗️  HomeStyle Analysis - {row.get('address1', 'Unknown')}",
        border_style="cyan",
        padding=(1, 2)
    ))

def display_all_properties_homestyle_analysis(console, df, properties_df=None):
    """
    Display all properties with comprehensive HomeStyle renovation analysis.

    Args:
        console: Rich console instance
        df: Properties DataFrame with HomeStyle calculations
        properties_df: Optional filtered DataFrame to display
    """
    dataframe = df if properties_df is None else properties_df
    
    # Sort by deal score descending
    dataframe = dataframe.sort_values("hs_deal_score", ascending=False)

    table = Table(
        title=f"All Properties - HomeStyle Renovation Analysis - PRIMARY RESIDENCE (97% LTV) ({len(dataframe)} properties)",
        show_header=True,
        header_style="bold cyan"
    )

    # Add columns
    # Property basics
    table.add_column("Address", style="cyan", no_wrap=False)
    table.add_column("Price", justify="right")
    table.add_column("PCS", justify="center")

    # Costs & Values
    table.add_column("Reno Cost", justify="right")
    table.add_column("Total", justify="right")
    table.add_column("ARV", justify="right")

    # Financing
    table.add_column("Max Loan (97%)", justify="right")
    table.add_column("Down Payment (3%)", justify="right")

    # Renovation Breakdown
    table.add_column("Reno Financed", justify="right")
    table.add_column("Reno Out-of-Pocket", justify="right")

    # Cash Requirements
    table.add_column("Total Cash Required", justify="right")
    table.add_column("Borrowing Gap", justify="right")

    # Deal Metrics
    table.add_column("Built-in Equity", justify="right")
    table.add_column("Equity %", justify="right")
    table.add_column("ROI", justify="center")
    table.add_column("Deal Score", justify="center")
    table.add_column("Feasible", justify="center")

    # Add rows
    for _, row in dataframe.iterrows():
        address = row.get("address1", "N/A")
        purchase_price = row.get("purchase_price", 0)
        condition = int(row.get("property_condition_score", 3))
        reno_cost = row.get("hs_renovation_cost", 0)
        total_project = row.get("hs_total_project_cost", 0)
        arv = row.get("hs_arv", 0)
        max_loan = row.get("hs_max_loan_amount", 0)
        cash_needed = row.get("hs_cash_needed", 0)
        equity = row.get("hs_built_in_equity", 0)
        equity_pct = row.get("hs_equity_pct", 0)
        roi = row.get("hs_renovation_roi", 0)
        score = row.get("hs_deal_score", 0)
        is_feasible = row.get("hs_is_feasible", False)
        down_payment = row.get("hs_down_payment", 0)
        reno_financed = row.get("hs_max_renovation_financing", 0)
        reno_out_of_pocket = row.get("hs_out_of_pocket_renovation", 0)
        borrowing_gap = row.get("hs_borrowing_gap", 0)

        # Color coding for equity
        if equity_pct > 0.15:
            equity_color = "green"
        elif equity_pct > 0.05:
            equity_color = "yellow"
        else:
            equity_color = "red"

        # Color coding for ROI
        if roi > 1.3:
            roi_color = "green"
        elif roi > 1.1:
            roi_color = "yellow"
        else:
            roi_color = "red"

        # Color coding for deal score
        if score > 60:
            score_color = "green"
        elif score > 40:
            score_color = "yellow"
        else:
            score_color = "red"

        feasible_text = "[green]✓[/green]" if is_feasible else "[red]✗[/red]"

        # Color coding for borrowing gap
        if borrowing_gap == 0:
            gap_color = "green"
        elif borrowing_gap < 10000:
            gap_color = "yellow"
        else:
            gap_color = "red"

        table.add_row(
            address,
            format_currency(purchase_price),
            str(condition),
            format_currency(reno_cost),
            format_currency(total_project),
            format_currency(arv),
            format_currency(max_loan),
            format_currency(down_payment),
            format_currency(reno_financed),
            format_currency(reno_out_of_pocket),
            format_currency(cash_needed),
            f"[{gap_color}]{format_currency(borrowing_gap)}[/{gap_color}]",
            f"[{equity_color}]{format_currency(equity)}[/{equity_color}]",
            f"[{equity_color}]{format_percentage(equity_pct)}[/{equity_color}]",
            f"[{roi_color}]{roi:.2f}x[/{roi_color}]",
            f"[{score_color}]{score:.0f}[/{score_color}]",
            feasible_text
        )

    console.print(table)

def display_loans(console, loans):
    if not loans:
        console.print("[red]Loans could not be fetched![/red]")
        return

    table = Table(
        title="Available Loans", show_header=True, header_style="bold magenta"
    )

    table.add_column("Name", style="cyan", no_wrap=True)
    table.add_column("interest Rate", justify="right", style="green")
    table.add_column("APR Rate", justify="right", style="green")
    table.add_column("Down Payment", justify="right", style="yellow")
    table.add_column("Term (Years)", justify="right", style="blue")
    table.add_column("MIP Upfront", justify="right", style="orange3")
    table.add_column("MIP Annual", justify="right", style="orange3")
    table.add_column("Fees", justify="right", style="red")
    table.add_column("Upfront Discounts", justify="right", style="red")
    table.add_column("Preapproved Amount", justify="right", style="purple")
    table.add_column("Expiration Date", style="white")

    for loan in loans:
        preapproved_amount = loan.preapproved_amount or 0.0

        table.add_row(
            str(loan.name),
            f"{loan.interest_rate * 100:.2f}%",
            f"{loan.apr_rate * 100:.2f}%",
            f"{loan.down_payment_rate * 100:.1f}%",
            str(loan.years),
            f"{loan.mip_upfront_rate * 100:.2f}%",
            f"{loan.mip_annual_rate * 100:.2f}%",
            format_currency(loan.lender_fees),
            f"${loan.upfront_discounts:,.2f}",
            f"${preapproved_amount:,}",
            str(loan.expiration_date),
        )

    console.print(table)

def display_current_context_panel(console, loan_name, assumptions_description):
    """Display a panel showing current loan and assumptions names."""
    panel_content = (
        f"[bold cyan]Loan:[/bold cyan] {loan_name}\n"
        f"[bold cyan]Assumptions:[/bold cyan] {assumptions_description}"
    )
    console.print(Panel(
        panel_content,
        title="Current Configuration",
        border_style="cyan"
    ))

def _format_overall_metrics(summary):
    """Format overall metrics section."""
    total = summary.get('properties_count', 0)
    active = summary.get('active_properties_count', 0)
    inactive = summary.get('inactive_properties_count', 0)

    return (
        f"[bold cyan]OVERALL[/bold cyan]\n"
        f"Total Properties: {total}    Active: {active}    Inactive: {inactive}"
    )


def _format_phase0_metrics(summary):
    """Format Phase 0 metrics section."""
    count = summary.get('phase0_count', 0)
    avg_cf_qe = summary.get('phase0_avg_cashflow_qe', 0)
    avg_cf_y1 = summary.get('phase0_avg_cashflow_y1', 0)
    avg_cf_y2 = summary.get('phase0_avg_cashflow_y2', 0)
    avg_cash_needed = summary.get('phase0_avg_cash_needed', 0)
    avg_price = summary.get('phase0_avg_price', 0)
    missing_mr = summary.get('phase0_missing_mr_count', 0)

    # Color code cash flows
    cf_qe_color = "green" if avg_cf_qe >= 0 else "red"
    cf_y1_color = "green" if avg_cf_y1 >= 0 else "red"
    cf_y2_color = "green" if avg_cf_y2 >= 0 else "red"

    result = (
        f"[bold cyan]PHASE 0 - Initial Screening[/bold cyan]\n"
        f"Qualifiers: {count}    "
        f"Avg Cash Flow (QE): [{cf_qe_color}]{format_currency(avg_cf_qe)}[/{cf_qe_color}]\n"
        f"Avg CF (Y1): [{cf_y1_color}]{format_currency(avg_cf_y1)}[/{cf_y1_color}]    "
        f"Avg CF (Y2): [{cf_y2_color}]{format_currency(avg_cf_y2)}[/{cf_y2_color}]\n"
        f"Avg Cash Needed: {format_currency(avg_cash_needed)}    "
        f"Avg Price: {format_currency(avg_price)}"
    )

    if missing_mr > 0:
        result += f"\n[yellow]Missing Market Research: {missing_mr} properties[/yellow]"

    return result


def _format_phase1_metrics(summary):
    """Format Phase 1 metrics section."""
    cur = summary.get('phase1_cur_count', 0)
    con = summary.get('phase1_con_count', 0)
    cre = summary.get('phase1_cre_count', 0)
    avg_cf_qe = summary.get('phase1_avg_cashflow_qe', 0)
    avg_cf_y1 = summary.get('phase1_avg_cashflow_y1', 0)
    avg_cf_y2 = summary.get('phase1_avg_cashflow_y2', 0)
    avg_cash_needed = summary.get('phase1_avg_cash_needed', 0)
    avg_price = summary.get('phase1_avg_price', 0)
    missing_est = summary.get('phase1_missing_est_price', 0)
    missing_nbhd = summary.get('phase1_missing_neighborhood', 0)
    missing_grade = summary.get('phase1_missing_neighborhood_grade', 0)
    missing_niche = summary.get('phase1_missing_neighborhood_niche_grade', 0)

    # Color code cash flows
    cf_qe_color = "green" if avg_cf_qe >= 0 else "red"
    cf_y1_color = "green" if avg_cf_y1 >= 0 else "red"
    cf_y2_color = "green" if avg_cf_y2 >= 0 else "red"

    result = (
        f"[bold cyan]PHASE 1 - Financial Viability[/bold cyan]\n"
        f"Current: {cur}    Contingent: {con}    Creative: {cre}\n"
        f"Avg CF (QE): [{cf_qe_color}]{format_currency(avg_cf_qe)}[/{cf_qe_color}]    "
        f"Avg CF (Y1): [{cf_y1_color}]{format_currency(avg_cf_y1)}[/{cf_y1_color}]    "
        f"Avg CF (Y2): [{cf_y2_color}]{format_currency(avg_cf_y2)}[/{cf_y2_color}]\n"
        f"Avg Cash Needed: {format_currency(avg_cash_needed)}    "
        f"Avg Price: {format_currency(avg_price)}"
    )

    # Add missing data warnings
    missing_items = []
    if missing_est > 0:
        missing_items.append(f"Est Price ({missing_est})")
    if missing_nbhd > 0:
        missing_items.append(f"Neighborhood ({missing_nbhd})")
    if missing_grade > 0:
        missing_items.append(f"Grade ({missing_grade})")
    if missing_niche > 0:
        missing_items.append(f"Niche Grade ({missing_niche})")

    if missing_items:
        result += f"\n[yellow]Missing: {' | '.join(missing_items)}[/yellow]"

    return result


def _format_phase15_metrics(summary):
    """Format Phase 1.5 metrics section."""
    touring = summary.get('touring_count', 0)
    nontouring = summary.get('nontouring_count', 0)
    avg_cf_qe = summary.get('touring_avg_cashflow_qe', 0)
    avg_cf_y1 = summary.get('touring_avg_cashflow_y1', 0)
    avg_cf_y2 = summary.get('touring_avg_cashflow_y2', 0)
    avg_cash_needed = summary.get('touring_avg_cash_needed', 0)
    avg_price = summary.get('touring_avg_price', 0)
    missing_est_value = summary.get('touring_missing_est_value', 0)
    missing_tours = summary.get('touring_missing_tours_count', 0)

    # Color code cash flows
    cf_qe_color = "green" if avg_cf_qe >= 0 else "red"
    cf_y1_color = "green" if avg_cf_y1 >= 0 else "red"
    cf_y2_color = "green" if avg_cf_y2 >= 0 else "red"

    result = (
        f"[bold cyan]PHASE 1.5 - Touring List[/bold cyan]\n"
        f"Touring: {touring}    Non-touring: {nontouring}    "
        f"Missing Tours: {missing_tours}\n"
        f"Avg CF (QE): [{cf_qe_color}]{format_currency(avg_cf_qe)}[/{cf_qe_color}]    "
        f"Avg CF (Y1): [{cf_y1_color}]{format_currency(avg_cf_y1)}[/{cf_y1_color}]    "
        f"Avg CF (Y2): [{cf_y2_color}]{format_currency(avg_cf_y2)}[/{cf_y2_color}]\n"
        f"Avg Cash Needed: {format_currency(avg_cash_needed)}    "
        f"Avg Price: {format_currency(avg_price)}"
    )

    if missing_est_value > 0:
        result += f"\n[yellow]Missing Est Value: {missing_est_value} properties[/yellow]"

    return result


def _format_phase2_metrics(summary):
    """Format Phase 2 metrics section."""
    count = summary.get('phase2_count', 0)

    return (
        f"[bold cyan]PHASE 2 - Final Qualification[/bold cyan]\n"
        f"Qualified: {count} properties"
    )


def _format_tasks_section(summary):
    """Format tasks section as a Rich Table with 3 columns for task categories."""

    # Get task lists from summary
    phase0_missing = summary.get('phase0_missing_mr_list', [])
    touring_missing_assessments = summary.get('touring_missing_assessments_list', [])
    touring_missing_tours = summary.get('touring_missing_tours_list', [])

    # Create table with title and headers
    table = Table(
        title="TASKS",
        show_header=True,
        header_style="bold yellow",
        padding=(0, 1)  # Minimal padding for compact display
    )

    # Add columns with counts in headers
    col1_header = f"Phase 0 - Missing MR ([red]{len(phase0_missing)}[/red])"
    col2_header = f"Phase 1.5 - Missing Assessments ([red]{len(touring_missing_assessments)}[/red])"
    col3_header = f"Phase 1.5 - Missing Tours ([red]{len(touring_missing_tours)}[/red])"

    table.add_column(col1_header, style="cyan", no_wrap=False)
    table.add_column(col2_header, style="cyan", no_wrap=False)
    table.add_column(col3_header, style="cyan", no_wrap=False)

    # Handle case when all lists are empty
    if not any([phase0_missing, touring_missing_assessments, touring_missing_tours]):
        table.add_row(
            "[green]✓ All completed[/green]",
            "[green]✓ All completed[/green]",
            "[green]✓ All completed[/green]"
        )
        return table

    # Add rows using zip_longest to handle variable-length lists
    for item0, item_assess, item_tour in zip_longest(
        phase0_missing,
        touring_missing_assessments,
        touring_missing_tours,
        fillvalue=None
    ):
        row_cells = [
            f"☐ {item0}" if item0 else "",
            f"☐ {item_assess}" if item_assess else "",
            f"☐ {item_tour}" if item_tour else ""
        ]
        table.add_row(*row_cells)

    return table


def display_start_screen_summary(console, summary):
    """Display start screen dashboard with metrics and tasks."""
    # Build metrics sections (all return strings)
    overall_section = _format_overall_metrics(summary)
    phase0_section = _format_phase0_metrics(summary)
    phase1_section = _format_phase1_metrics(summary)
    phase15_section = _format_phase15_metrics(summary)
    phase2_section = _format_phase2_metrics(summary)

    # Build tasks table (returns Table object)
    tasks_table = _format_tasks_section(summary)

    # Create metrics content as formatted string (Group handles Rich markup in strings)
    metrics_content = f"""
{overall_section}

{phase0_section}

{phase1_section}

{phase15_section}

{phase2_section}

{'─' * 70}

"""

    # Combine metrics string and tasks table using Group
    panel_content = Group(metrics_content, tasks_table)

    # Display in panel
    console.print(Panel(
        panel_content,
        title="Investment Pipeline Dashboard",
        border_style="cyan",
        padding=(1, 2)
    ))