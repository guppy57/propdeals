import os

import pandas as pd
import questionary
from dotenv import load_dotenv
from InquirerPy import inquirer
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from supabase import Client, create_client

from add_property import run_add_property
from helpers import (
  calculate_mortgage,
  format_currency,
  format_number,
  format_percentage,
)
from loans import LoansProvider
from rent_research import RentResearcher
from inspections import InspectionsClient

load_dotenv()

console = Console() 
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections = InspectionsClient(supabase_client=supabase)

white_style = Style([
    ('qmark', 'fg:white bold'),           # question mark
    ('question', 'fg:white'),             # question text
    ('answer', 'fg:white bold'),          # submitted answer
    ('text', 'fg:white'),                 # input text
    ('completion-menu', 'fg:white'),      # autocomplete menu
    ('completion-menu.completion', 'fg:white'),  # autocomplete items
    ('completion-menu.completion.current', 'fg:white bg:blue'),  # selected item
    ('', 'fg:white')                      # fallback
])

def load_assumptions():
  global appreciation_rate, rent_appreciation_rate, property_tax_rate, home_insurance_rate, vacancy_rate, repair_savings_rate, closing_costs_rate, live_in_unit_setting
  console.print("[yellow]Reloading assumptions...[/yellow]")
  assumptions_get_response = supabase.table('assumptions').select('*').eq('id', 1).limit(1).single().execute()
  appreciation_rate = float(assumptions_get_response.data["appreciation_rate"])
  rent_appreciation_rate = float(assumptions_get_response.data["rent_appreciation_rate"])
  property_tax_rate = float(assumptions_get_response.data["property_tax_rate"])
  home_insurance_rate = float(assumptions_get_response.data["home_insurance_rate"])
  vacancy_rate = float(assumptions_get_response.data["vacancy_rate"])
  repair_savings_rate = float(assumptions_get_response.data["repair_savings_rate"])
  closing_costs_rate = float(assumptions_get_response.data["closing_costs_rate"])
  live_in_unit_setting = assumptions_get_response.data["live_in_unit_setting"]
  console.print(f"[green]Assumption set '{assumptions_get_response.data['description']}' reloaded successfully![/green]")

def load_loan(loan_id):
  global interest_rate, apr_rate, down_payment_rate, loan_length_years, mip_upfront_rate, mip_annual_rate, lender_fees
  console.print("[yellow]Reloading FHA loan data...[/yellow]")
  loan_provider = LoansProvider(supabase_client=supabase, console=console)
  loan = loan_provider.get_loan_by_id(loan_id)
  interest_rate = loan.interest_rate
  apr_rate = loan.apr_rate
  down_payment_rate = loan.down_payment_rate
  loan_length_years = loan.years
  mip_upfront_rate = loan.mip_upfront_rate
  mip_annual_rate = loan.mip_annual_rate
  lender_fees = loan.lender_fees
  console.print("[green]FHA loan data reloaded successfully![/green]")

def deal_score_property(row):
    score = 0
    score += (3 if row["monthly_cash_flow_y2"] > 500 else 
              2 if row["monthly_cash_flow_y2"] > 400 else 
              1 if row["monthly_cash_flow_y2"] > 200 else 0)
    score += (3 if row["monthly_cash_flow_y1"] > 0 else 2 if row["monthly_cash_flow_y1"] > -350 else 0)  # House-hacking bonus
    score += (3 if row["CoC_y2"] > 0.15 else 
              2 if row["CoC_y2"] > 0.12 else 
              1 if row["CoC_y2"] > 0.08 else 0)
    score += (1 if row["cap_rate_y2"] > 0.06 else 0)
    score += (2 if row["MGR_PP"] >= 0.01 else 1 if row["MGR_PP"] >= 0.008 else 0)  # 1% rule
    score += (2 if 0.4 <= row["OpEx_Rent"] <= 0.6 else 1 if 0.3 <= row["OpEx_Rent"] <= 0.7 else 0)  # 50% rule  
    score += (2 if row["DSCR"] >= 1.25 else 1 if row["DSCR"] >= 1.1 else 0)
    score += (2 if row["cash_needed"] < 20000 else 1 if row["cash_needed"] < 30000 else 0)
    score += (1 if row["GRM_y2"] < 12 else 0)  # Lower GRM is better
    score += (2 if row["cost_per_sqrft"] < 100 else 1 if row["cost_per_sqrft"] < 150 else 0)
    score += (2 if row["home_age"] < 20 else 0)
    return score

def mobility_score(row):
    score = (row["walk_score"] * 0.6) + (row["transit_score"] * 0.30) + (row["bike_score"] * 0.10)
    return score

def get_expected_gains(row, length_years):
    current_home_value = row["purchase_price"]
    loan_amount = row["loan_amount"]
    y1_cashflow = row["annual_cash_flow_y1"]
    y2_cashflow = row["annual_cash_flow_y2"]

    y1_cashflow_grown = y1_cashflow * (1 + rent_appreciation_rate)
    cumulative_cashflow = y1_cashflow_grown
    for year in range(2, length_years + 1):
        yearly_cashflow = y2_cashflow * ((1 + rent_appreciation_rate) ** (year - 1))
        cumulative_cashflow += yearly_cashflow

    appreciation_gains = current_home_value * ((1 + appreciation_rate) ** length_years - 1)
    monthly_rate = apr_rate / 12
    num_payments = loan_length_years * 12
    total_payments_in_period = length_years * 12
    remaining_balance = loan_amount * (
        ((1 + monthly_rate) ** num_payments - (1 + monthly_rate) ** total_payments_in_period) /
        ((1 + monthly_rate) ** num_payments - 1)
    )
    equity_gains = loan_amount - remaining_balance
    return cumulative_cashflow + appreciation_gains + equity_gains

def set_monthly_taxes(row):
    annual_tax = row.get('annual_tax_amount')
    if pd.notna(annual_tax) and annual_tax is not None:
        return annual_tax / 12
    return (row["purchase_price"] * property_tax_rate) / 12

def reload_dataframe():
    """Reload and recalculate all property data from supabase"""
    global df, rents
    console.print("[yellow]Reloading property data...[/yellow]")
    properties_get_response = supabase.table('properties').select('*').execute()
    df = pd.DataFrame(properties_get_response.data)
    df = df.drop(["zillow_link", "full_address"], axis=1)
    
    cols = ["walk_score", "transit_score", "bike_score"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    df[cols] = df[cols].fillna(0)
    df["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"]
    df["home_age"] = 2025 - df["built_in"]
    df["closing_costs"] = (df["purchase_price"] * closing_costs_rate) + lender_fees
    df["down_payment"] = df["purchase_price"] * down_payment_rate
    df["loan_amount"] = df["purchase_price"] - df["down_payment"] + (df["purchase_price"] * mip_upfront_rate)
    df["monthly_mortgage"] = df["loan_amount"].apply(lambda x: calculate_mortgage(x, apr_rate, loan_length_years))
    df["monthly_mip"] = (df["loan_amount"] * mip_annual_rate) / 12
    df["monthly_taxes"] = df.apply(set_monthly_taxes, axis=1)
    df["monthly_insurance"] = (df["purchase_price"] * home_insurance_rate) / 12
    df["cash_needed"] = df["closing_costs"] + df["down_payment"]

    rents_get_response = supabase.table('rent_estimates').select('*').execute()
    rents = pd.DataFrame(rents_get_response.data)
    rents = rents.drop(['id'], axis=1)
    rent_summary = rents.groupby("address1")["rent_estimate"].agg(["sum", "min"]).reset_index()
    rent_summary.columns = ["address1", "total_rent", "min_rent"]
    min_rent_indices = rents.groupby("address1")["rent_estimate"].idxmin()
    min_rent_units = rents.loc[min_rent_indices, ["address1", "unit_num", "beds"]].reset_index(drop=True)
    min_rent_units.columns = ["address1", "min_rent_unit", "min_rent_unit_beds"]
    rent_summary = rent_summary.merge(min_rent_units, on="address1", how="left")
    rent_summary["net_rent_y1"] = rent_summary["total_rent"] - rent_summary["min_rent"]

    df = df.merge(rent_summary, on="address1", how="left")
    df["annual_rent_y1"] = df["net_rent_y1"] * 12
    df["annual_rent_y2"] = df["total_rent"] * 12
    df["monthly_vacancy_costs"] = df["total_rent"] * vacancy_rate
    df["monthly_repair_costs"] = df["total_rent"] * repair_savings_rate
    df["operating_expenses"] = df["monthly_vacancy_costs"] + df["monthly_repair_costs"] + df["monthly_taxes"] + df["monthly_insurance"]
    df["total_monthly_cost"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses"]
    df["monthly_NOI"] = df["total_rent"] - df["operating_expenses"]
    df["annual_NOI_y1"] = (df["net_rent_y1"] - df["operating_expenses"]) * 12
    df["annual_NOI_y2"] = df["monthly_NOI"] * 12
    df["monthly_cash_flow_y1"] = df["net_rent_y1"] - df["total_monthly_cost"]
    df["monthly_cash_flow_y2"] = df["total_rent"] - df["total_monthly_cost"]
    df["annual_cash_flow_y1"] = df["monthly_cash_flow_y1"] * 12
    df["annual_cash_flow_y2"] = df["monthly_cash_flow_y2"] * 12
    df["cap_rate_y1"] = df["annual_NOI_y1"] / df["purchase_price"]
    df["cap_rate_y2"] = df["annual_NOI_y2"] / df["purchase_price"]
    df["CoC_y1"] = df["annual_cash_flow_y1"] / df["cash_needed"]
    df["CoC_y2"] = df["annual_cash_flow_y2"] / df["cash_needed"]
    df["GRM_y1"] = df["purchase_price"] / df["annual_rent_y1"] # Gross Rent Multiplier (lower = better)
    df["GRM_y2"] = df["purchase_price"] / df["annual_rent_y2"]
    df["MGR_PP"] = df["total_rent"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
    df["OpEx_Rent"] = df["operating_expenses"] / df["total_rent"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
    df["DSCR"] = df["total_rent"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25
    df["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5,))
    df["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10,))
    df["deal_score"] = df.apply(deal_score_property, axis=1)
    df["mobility_score"] = df.apply(mobility_score, axis=1)
  
    console.print("[green]Property data reloaded successfully![/green]")

load_assumptions()
load_loan(1)
reload_dataframe()

def display_all_properties(properties_df, title, show_status=False, show_min_rent_data=False):
    dataframe = df if properties_df is None else properties_df
    table = Table(title=title, show_header=True, header_style="bold magenta")
    mobility_75th_percentile = df["mobility_score"].quantile(0.75)
    mobility_25th_percentile = df["mobility_score"].quantile(0.25)
    forecast_10y_75th_percentile = df["10y_forecast"].quantile(0.75)
    forecast_10y_25th_percentile = df["10y_forecast"].quantile(0.25)
    price_20th = dataframe["purchase_price"].quantile(0.20)
    price_40th = dataframe["purchase_price"].quantile(0.40)
    price_60th = dataframe["purchase_price"].quantile(0.60)
    price_80th = dataframe["purchase_price"].quantile(0.80)
    cash_20th = dataframe["cash_needed"].quantile(0.20)
    cash_40th = dataframe["cash_needed"].quantile(0.40)
    cash_60th = dataframe["cash_needed"].quantile(0.60)
    cash_80th = dataframe["cash_needed"].quantile(0.80)

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

    table.add_column("Address", style="cyan", no_wrap=True)
    table.add_column("Price", justify="right", no_wrap=True)
    table.add_column("Cash Needed", justify="right")
    table.add_column("Costs/mo", justify="right", style="yellow")
    table.add_column("CF/mo Y1", justify="right", no_wrap=True)
    table.add_column("CF/mo Y2", justify="right", no_wrap=True)
    table.add_column("NOI Y2", justify="right", style="yellow")
    table.add_column("CapR Y1", justify="right", style="blue")
    table.add_column("CapR Y2", justify="right", style="blue")
    table.add_column("CoC Y2", justify="right", style="purple")
    table.add_column("1% Rule", justify="right", style="cyan")
    table.add_column("50% Rule", justify="right", style="magenta")
    table.add_column("DSCR", justify="right", style="blue")
    table.add_column("DS", justify="right", style="bold white")  # deal score
    table.add_column("MS", justify="right", style="bold white")  # mobility score
    table.add_column(
        "10Y", justify="right", style="bold white"
    )  # 10 year investment growth

    if show_status:
        table.add_column("Status", justify="right", style="bold white")

    if show_min_rent_data:
        table.add_column("MinR Unit Beds", justify="right", style="bold white")
        table.add_column("Add. Beds", justify="right", style="bold white")
        table.add_column("Add. Rent", justify="right", style="bold white")

    for _, row in dataframe.iterrows():
        cf_y1_style = "red" if row["monthly_cash_flow_y1"] < 0 else "green"
        cf_y2_style = "red" if row["monthly_cash_flow_y2"] < 0 else "green"

        noi_style = "red" if row["monthly_NOI"] < 0 else "green"

        opex_rent_style = (
            "green"
            if 0.45 <= row["OpEx_Rent"] <= 0.55
            else ("yellow" if 0.35 <= row["OpEx_Rent"] <= 0.65 else "red")
        )
        dscr_style = "green" if row["DSCR"] >= 1.25 else "red"
        mgr_pp_style = "green" if row["MGR_PP"] >= 0.01 else "red"

        deal_score_style = (
            "green"
            if row["deal_score"] >= 15
            else ("yellow" if row["deal_score"] >= 12 else "red")
        )

        mobility_score_style = (
            "green"
            if row["mobility_score"] >= mobility_75th_percentile
            else ("yellow" if row["mobility_score"] >= mobility_25th_percentile else "red")
        )

        forecast_10y_style = (
            "green"
            if row["10y_forecast"] >= forecast_10y_75th_percentile
            else ("yellow" if row["10y_forecast"] >= forecast_10y_25th_percentile else "red")
        )

        price_style = get_quintile_color(
            row["purchase_price"], price_20th, price_40th, price_60th, price_80th
        )
        cash_style = get_quintile_color(
            row["cash_needed"], cash_20th, cash_40th, cash_60th, cash_80th
        )

        row_args = [
            str(row["address1"]),
            f"[{price_style}]{format_currency(row['purchase_price'])}[/{price_style}]",
            f"[{cash_style}]{format_currency(row['cash_needed'])}[/{cash_style}]",
            format_currency(row["total_monthly_cost"]),
            f"[{cf_y1_style}]{format_currency(row['monthly_cash_flow_y1'])}[/{cf_y1_style}]",
            f"[{cf_y2_style}]{format_currency(row['monthly_cash_flow_y2'])}[/{cf_y2_style}]",
            f"[{noi_style}]{format_currency(row['monthly_NOI'])}[/{noi_style}]",
            format_percentage(row["cap_rate_y1"]),
            format_percentage(row["cap_rate_y2"]),
            format_percentage(row["CoC_y2"]),
            f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]",
            f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]",
            f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]",
            f"[{deal_score_style}]{int(row['deal_score'])}/24[/{deal_score_style}]",
            f"[{mobility_score_style}]{int(row['mobility_score'])}[/{mobility_score_style}]",
            f"[{forecast_10y_style}]{format_currency(row['10y_forecast'])}[/{forecast_10y_style}]"
        ]
        
        if show_status:
            row_args.append(row["status"])
        
        if show_min_rent_data:
            row_args.append(str(row["min_rent_unit_beds"]))
            row_args.append(str(int(row["min_rent_unit_beds"] - 1)))
            row_args.append(str(calculate_additional_room_rent(row)))
            
        table.add_row(*row_args)

    console.print(table)

def get_all_phase1_qualifying_properties(active=True):
    """
    This method filters all properties based on our criteria for what is a financially viable property
    Current criteria:
      - status = 'active'
      - 1% rule (monthly gross rent must be 1% or more of purchase price)
      - 50% rule (operating expenses must be 50% or lower than gross rent)
      - Cash needed must be below $25,000
      - Debt Service Coverage Ratio should be above 1.25
      - Monthly Cashflow with cheapest unit not rented above -400 (house hacking)
      - Fully rented monthly cashflow above 400
    """
    status_criteria = "status == 'active'" if active else "status != 'active'"
    criteria = f"{status_criteria} & MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & cash_needed <= 25000 & monthly_cash_flow_y1 >= -400 & monthly_cash_flow_y2 >= 400"

    filtered_df = df.copy()
    filtered_df = filtered_df.query(criteria)

    qualifier_address1s = []

    for _, row in filtered_df.iterrows():
      qualifier_address1s.append(row["address1"])

    reduced_df = get_reduced_pp_df(0.10)
    reduced_df = reduced_df.query(criteria)

    for address1 in qualifier_address1s:
      reduced_df = reduced_df.drop(reduced_df[reduced_df['address1'] == address1].index)

    creative_df = get_additional_room_rental_df()
    creative_df = creative_df.query(criteria)
    
    return filtered_df, reduced_df, creative_df 

def display_all_phase1_qualifying_properties():
    current, contingent, creative = get_all_phase1_qualifying_properties()

    display_all_properties(
        properties_df=current, title="Phase 1 Criteria Qualifiers - Current Prices"
    )

    display_all_properties(
        properties_df=contingent,
        title="Phase 1 Criteria Qualifiers - Contingent on 10% Price Reduction",
    )

    display_all_properties(
      properties_df=creative,
      title="Phase 1 Criteria Qualifiers - If we rent out additional rooms in our unit",
      show_min_rent_data=True
    )
  
def display_creative_pricing_all_properties():
    creative_df = get_additional_room_rental_df()
    display_all_properties(
      properties_df=creative_df,
      title="All properties with additional rooms rented",
      show_min_rent_data=True
    )

def calculate_additional_room_rent(row):
    return int(row['min_rent_unit_beds'] - 1) * 400

def get_additional_room_rental_df():
    dataframe = df.copy()
    df2 = dataframe.query('min_rent_unit_beds > 1').copy()
    df2["additional_room_rent"] = df2.apply(calculate_additional_room_rent, axis=1)
    df2["net_rent_y1"] = df2["net_rent_y1"] + df2["additional_room_rent"]
    df2["monthly_cash_flow_y1"] = df2["net_rent_y1"] - df2["total_monthly_cost"]
    df2["annual_cash_flow_y1"] = df2["monthly_cash_flow_y1"] * 12
    df2["annual_NOI_y1"] = (df2["net_rent_y1"] - df2["operating_expenses"]) * 12
    df2["cap_rate_y1"] = df2["annual_NOI_y1"] / df2["purchase_price"]
    df2["CoC_y1"] = df2["annual_cash_flow_y1"] / df2["cash_needed"]
    df2["GRM_y1"] = df2["purchase_price"] / df2["annual_rent_y1"]
    df2["deal_score"] = df2.apply(deal_score_property, axis=1)
    return df2

def get_reduced_pp_df(reduction_factor):
    dataframe = df.copy()
    dataframe["original_price"] = dataframe["purchase_price"]
    dataframe["purchase_price"] = dataframe["purchase_price"] * (1 - reduction_factor) # new purchase price
    dataframe["cost_per_sqrft"] = dataframe["purchase_price"] / dataframe["square_ft"]
    dataframe["closing_costs"] = dataframe["purchase_price"] * closing_costs_rate
    dataframe["down_payment"] = dataframe["purchase_price"] * down_payment_rate
    dataframe["loan_amount"] = dataframe["purchase_price"] - dataframe["down_payment"] + (dataframe["purchase_price"] * mip_upfront_rate)
    dataframe["monthly_mortgage"] = dataframe["loan_amount"].apply(lambda x: calculate_mortgage(x, apr_rate, loan_length_years))
    dataframe["monthly_mip"] = (dataframe["loan_amount"] * mip_annual_rate) / 12
    dataframe["monthly_taxes"] = (dataframe["purchase_price"] * property_tax_rate) / 12
    dataframe["monthly_insurance"] = (dataframe["purchase_price"] * home_insurance_rate) / 12
    dataframe["cash_needed"] = dataframe["closing_costs"] + dataframe["down_payment"]
    dataframe["operating_expenses"] = dataframe["monthly_vacancy_costs"] + dataframe["monthly_repair_costs"] + dataframe["monthly_taxes"] + dataframe["monthly_insurance"]
    dataframe["total_monthly_cost"] = dataframe["monthly_mortgage"] + dataframe["monthly_mip"] + dataframe["operating_expenses"]
    dataframe["monthly_cash_flow_y1"] = dataframe["net_rent_y1"] - dataframe["total_monthly_cost"]
    dataframe["monthly_cash_flow_y2"] = dataframe["total_rent"] - dataframe["total_monthly_cost"]
    dataframe["annual_cash_flow_y1"] = dataframe["monthly_cash_flow_y1"] * 12
    dataframe["annual_cash_flow_y2"] = dataframe["monthly_cash_flow_y2"] * 12
    dataframe["monthly_NOI"] = dataframe["total_rent"] - dataframe["operating_expenses"]
    dataframe["annual_NOI_y1"] = (dataframe["net_rent_y1"] - dataframe["operating_expenses"]) * 12
    dataframe["annual_NOI_y2"] = dataframe["monthly_NOI"] * 12
    dataframe["cap_rate_y1"] = dataframe["annual_NOI_y1"] / dataframe["purchase_price"]
    dataframe["cap_rate_y2"] = dataframe["annual_NOI_y2"] / dataframe["purchase_price"]
    dataframe["CoC_y1"] = dataframe["annual_cash_flow_y1"] / dataframe["cash_needed"]
    dataframe["CoC_y2"] = dataframe["annual_cash_flow_y2"] / dataframe["cash_needed"]
    dataframe["GRM_y1"] = dataframe["purchase_price"] / dataframe["annual_rent_y1"]
    dataframe["GRM_y2"] = dataframe["purchase_price"] / dataframe["annual_rent_y2"]
    dataframe["MGR_PP"] = dataframe["total_rent"] / dataframe["purchase_price"]
    dataframe["OpEx_Rent"] = dataframe["operating_expenses"] / dataframe["total_rent"]
    dataframe["DSCR"] = dataframe["total_rent"] / dataframe["monthly_mortgage"]
    dataframe["5y_forecast"] = dataframe.apply(get_expected_gains, axis=1, args=(5,))
    dataframe["10y_forecast"] = dataframe.apply(get_expected_gains, axis=1, args=(10,))
    dataframe["deal_score"] = dataframe.apply(deal_score_property, axis=1)
    return dataframe

def display_all_properties_info(properties_df):
    """Display all properties with basic info: address, sqft, age, units, mobility scores, and electricity cost"""
    dataframe = df if properties_df is None else properties_df
    table = Table(
        title="Properties Basic Information",
        show_header=True,
        header_style="bold magenta",
    )

    built_75th_percentile = dataframe["built_in"].quantile(0.75)
    built_25th_percentile = dataframe["built_in"].quantile(0.25)
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
        if units_value == 2:
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
            if row["home_age"] <= built_25th_percentile
            else ("yellow" if row["home_age"] <= built_75th_percentile else "red")
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
            f"[{built_in_style}]{int(row['built_in'])}[/{built_in_style}]",
            units_display,
            f"[{walk_style}]{int(row['walk_score'])}[/{walk_style}]",
            f"[{transit_style}]{int(row['transit_score'])}[/{transit_style}]",
            f"[{bike_style}]{int(row['bike_score'])}[/{bike_style}]",
            f"[{elec_style}]{format_currency(row['annual_electricity_cost_est'])}[/{elec_style}]",
            row['listed_date'],
            str(row["has_reduced_price"]),
            str(row["has_tenants"]),
        )

    console.print(table)

def analyze_property(property_id):
    """Display detailed analysis for a single property"""
    row = df[df['address1'] == property_id].iloc[0]
    
    table = Table(title=f"Property Details: {property_id}", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="yellow", no_wrap=True)
    table.add_column("Year 1 (Live-in)", justify="right", style="green")
    table.add_column("Year 2 (All Rent)", justify="right", style="blue")
    
    console.print(Panel(f"[bold cyan]Property Overview[/bold cyan]\n"
                      f"Address: {row['address1']}\n"
                      f"Purchase Price: {format_currency(row['purchase_price'])}\n"
                      f"Bedrooms: {int(row['beds'])} | Bathrooms: {int(row['baths'])} | Sq Ft: {format_number(row['square_ft'])}\n"
                      f"Built: {int(row['built_in'])} (Age: {int(row['home_age'])} years)\n"
                      f"Units: {int(row['units'])}\n"
                      f"Cost per Sq Ft: {format_currency(row['cost_per_sqrft'])}", 
                      title="Basic Info"))
    
    property_rents = rents[rents['address1'] == property_id]
    your_unit_index = property_rents['rent_estimate'].idxmin()
    rent_table = Table(title="Unit Rent Estimates", show_header=True, header_style="bold green")
    rent_table.add_column("Unit", style="cyan", justify="center")
    rent_table.add_column("Configuration", style="yellow")
    rent_table.add_column("Monthly Rent", justify="right", style="green")
    rent_table.add_column("Status", style="magenta")
    
    total_monthly_rent = 0
    for idx, rent_row in property_rents.iterrows():
        is_your_unit = idx == your_unit_index
        unit_config = f"{int(rent_row['beds'])}-bed {int(rent_row['baths'])}-bath"
        status = "[bold red]Your Unit[/bold red]" if is_your_unit else "Rental"
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
    
    console.print(Panel(f"[bold blue]Rental Income Summary[/bold blue]\n"
                      f"Total Monthly Rent (All Units): {format_currency(row['total_rent'])}\n"
                      f"Your Unit Rent (Not Collected): {format_currency(row['min_rent'])}\n"
                      f"[bold]Net Monthly Income (Year 1): {format_currency(row['net_rent_y1'])}[/bold]\n"
                      f"[bold]Full Rental Income (Year 2): {format_currency(row['total_rent'])}[/bold]\n\n"
                      f"[bold yellow]Operating Expenses:[/bold yellow]\n"
                      f"Monthly Operating Expenses: {format_currency(row['operating_expenses'])} ({format_currency(row['operating_expenses'] * 12)} annually)\n\n"
                      f"[bold green]Net Operating Income (NOI):[/bold green]\n"
                      f"NOI Year 1 (Live-in): {format_currency(row['net_rent_y1'] - row['operating_expenses'])} ({format_currency(row['annual_NOI_y1'])} annually)\n"
                      f"NOI Year 2 (All Rent): {format_currency(row['monthly_NOI'])} ({format_currency(row['annual_NOI_y2'])} annually)", 
                      title="Income Breakdown"))
    
    table.add_row("Monthly Cash Flow", 
                  f"[{'red' if row['monthly_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y1'])}[/]",
                  f"[{'red' if row['monthly_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y2'])}[/]")
    table.add_row("Annual Cash Flow",
                  f"[{'red' if row['annual_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y1'])}[/]",
                  f"[{'red' if row['annual_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y2'])}[/]")
    table.add_row("Cap Rate", 
                  format_percentage(row['cap_rate_y1']),
                  format_percentage(row['cap_rate_y2']))
    table.add_row("Cash on Cash Return",
                  format_percentage(row['CoC_y1']),
                  format_percentage(row['CoC_y2']))
    table.add_row("Gross Rent Multiplier",
                  format_number(row['GRM_y1']),
                  format_number(row['GRM_y2']))
    table.add_row("Annual Rent",
                  format_currency(row['annual_rent_y1']),
                  format_currency(row['annual_rent_y2']))
    table.add_row("5-Year Investment Gain",
                  format_currency(row['5y_forecast']),
                  format_currency(row['5y_forecast']))
    table.add_row("10-Year Investment Gain",
                  format_currency(row['10y_forecast']),
                  format_currency(row['10y_forecast']))
    
    mgr_pp_style = "green" if row['MGR_PP'] >= 0.01 else "red"
    opex_rent_style = "green" if 0.45 <= row['OpEx_Rent'] <= 0.55 else ("yellow" if 0.35 <= row['OpEx_Rent'] <= 0.65 else "red")
    dscr_style = "green" if row['DSCR'] >= 1.25 else "red"
    
    table.add_row("1% Rule (MGR/PP)",
                  f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]",
                  f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]")
    table.add_row("50% Rule (OpEx/Rent)",
                  f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]",
                  f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]")
    table.add_row("DSCR (Rent/Mortgage)",
                  f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]",
                  f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]")
    
    console.print(table)
    
    criteria_table = Table(title="Investment Criteria Breakdown", show_header=True, header_style="bold magenta")
    criteria_table.add_column("Criteria", style="yellow", width=25)
    criteria_table.add_column("Score", justify="right", style="white", width=8)
    criteria_table.add_column("Max", justify="right", style="dim white", width=5)
    criteria_table.add_column("Details", style="dim cyan")
    
    cf_y2_score = (3 if row["monthly_cash_flow_y2"] > 500 else 2 if row["monthly_cash_flow_y2"] > 400 else 1 if row["monthly_cash_flow_y2"] > 200 else 0)
    cf_y1_bonus = (3 if row["monthly_cash_flow_y1"] > 0 else 2 if row["monthly_cash_flow_y1"] > -350 else 0)
    coc_score = (3 if row["CoC_y2"] > 0.15 else 2 if row["CoC_y2"] > 0.12 else 1 if row["CoC_y2"] > 0.08 else 0)
    cap_score = (1 if row["cap_rate_y2"] > 0.06 else 0)
    mgr_score = (2 if row["MGR_PP"] >= 0.01 else 1 if row["MGR_PP"] >= 0.008 else 0)
    opex_score = (2 if 0.4 <= row["OpEx_Rent"] <= 0.6 else 1 if 0.3 <= row["OpEx_Rent"] <= 0.7 else 0)
    dscr_score = (2 if row["DSCR"] >= 1.25 else 1 if row["DSCR"] >= 1.1 else 0)
    cash_score = (2 if row["cash_needed"] < 20000 else 1 if row["cash_needed"] < 30000 else 0)
    grm_score = (1 if row["GRM_y2"] < 12 else 0)
    sqft_score = (2 if row["cost_per_sqrft"] < 100 else 1 if row["cost_per_sqrft"] < 150 else 0)
    age_score = (2 if row["home_age"] < 20 else 0)
    
    deal_score_style = ("green" if row['deal_score'] >= 15 else "yellow" if row['deal_score'] >= 12 else "red")
    
    criteria_table.add_row("Cash Flow Y2", f"[white]{cf_y2_score}[/white]", "3", f"${row['monthly_cash_flow_y2']:.0f}/month")
    criteria_table.add_row("Cash Flow Y1 Bonus", f"[white]{cf_y1_bonus}[/white]", "3", f"${row['monthly_cash_flow_y1']:.0f}/month")
    criteria_table.add_row("Cash-on-Cash Return", f"[white]{coc_score}[/white]", "3", f"{row['CoC_y2']:.1%}")
    criteria_table.add_row("Cap Rate", f"[white]{cap_score}[/white]", "1", f"{row['cap_rate_y2']:.1%}")
    criteria_table.add_row("1% Rule", f"[white]{mgr_score}[/white]", "2", f"{row['MGR_PP']:.2%}")
    criteria_table.add_row("50% Rule", f"[white]{opex_score}[/white]", "2", f"{row['OpEx_Rent']:.1%}")
    criteria_table.add_row("DSCR", f"[white]{dscr_score}[/white]", "2", f"{row['DSCR']:.2f}")
    criteria_table.add_row("Cash Needed", f"[white]{cash_score}[/white]", "2", f"${row['cash_needed']:,.0f}")
    criteria_table.add_row("GRM", f"[white]{grm_score}[/white]", "1", f"{row['GRM_y2']:.1f}")
    criteria_table.add_row("Cost per Sqft", f"[white]{sqft_score}[/white]", "2", f"${row['cost_per_sqrft']:.0f}")
    criteria_table.add_row("Property Age", f"[white]{age_score}[/white]", "2", f"{row['home_age']:.0f} years")
    criteria_table.add_row("[bold]TOTAL SCORE[/bold]", f"[bold {deal_score_style}]{int(row['deal_score'])}[/bold {deal_score_style}]", "[bold]24[/bold]", 
                          f"[bold {deal_score_style}]{'Excellent' if row['deal_score'] >= 15 else 'Good' if row['deal_score'] >= 12 else 'Poor'}[/bold {deal_score_style}]")
    
    console.print(criteria_table)

    mobility_table = Table(title="Mobility Score Breakdown", show_header=True, header_style="bold magenta")
    mobility_table.add_column("Metric", style="yellow", width=25)
    mobility_table.add_column("Score", justify="right", style="white", width=8)
    mobility_table.add_column("Max", justify="right", style="dim white", width=5)
    mobility_table.add_column("Weight", justify="right", style="white", width=8)
    mobility_table.add_column("Result", justify="right", style="white", width=8)

    walk_score = row['walk_score']
    transit_score = row['transit_score']
    bike_score = row['bike_score']
    
    walk_weight = 0.6
    transit_weight = 0.3
    bike_weight = 0.1

    walk_result = walk_score * walk_weight
    transit_result = transit_score * transit_weight
    bike_result = bike_score * bike_weight

    total_mobility_score = row['mobility_score']
    mobility_score_style = ("green" if total_mobility_score >= 75 else "yellow" if total_mobility_score >= 50 else "red")

    mobility_table.add_row("Walk Score", f"{walk_score:.0f}", "100", f"{walk_weight:.0%}", f"{walk_result:.2f}")
    mobility_table.add_row("Transit Score", f"{transit_score:.0f}", "100", f"{transit_weight:.0%}", f"{transit_result:.2f}")
    mobility_table.add_row("Bike Score", f"{bike_score:.0f}", "100", f"{bike_weight:.0%}", f"{bike_result:.2f}")
    mobility_table.add_row("[bold]TOTAL SCORE[/bold]", f"[{mobility_score_style}]{total_mobility_score:.2f}[/{mobility_score_style}]", "[bold]100[/bold]", "", f"[{mobility_score_style}]{total_mobility_score:.2f}[/{mobility_score_style}]")

    console.print(mobility_table)
    
    cost_table = Table(title="Cost Breakdown", show_header=True, header_style="bold red")
    cost_table.add_column("Cost Type", style="yellow")
    cost_table.add_column("Monthly Amount", justify="right", style="red")
    cost_table.add_column("Annual Amount", justify="right", style="red")
    
    cost_table.add_row("Mortgage Payment", format_currency(row['monthly_mortgage']), format_currency(row['monthly_mortgage'] * 12))
    cost_table.add_row("MIP (Insurance)", format_currency(row['monthly_mip']), format_currency(row['monthly_mip'] * 12))
    cost_table.add_row("Property Taxes", format_currency(row['monthly_taxes']), format_currency(row['monthly_taxes'] * 12))
    cost_table.add_row("Home Insurance", format_currency(row['monthly_insurance']), format_currency(row['monthly_insurance'] * 12))
    cost_table.add_row("Vacancy Reserve", format_currency(row['monthly_vacancy_costs']), format_currency(row['monthly_vacancy_costs'] * 12))
    cost_table.add_row("Repair Reserve", format_currency(row['monthly_repair_costs']), format_currency(row['monthly_repair_costs'] * 12))
    cost_table.add_row("[bold]Total Monthly Cost[/bold]", f"[bold red]{format_currency(row['total_monthly_cost'])}[/bold red]", f"[bold red]{format_currency(row['total_monthly_cost'] * 12)}[/bold red]")
    cost_table.add_row("Electricity (est.)", format_currency(row['annual_electricity_cost_est']), format_currency(row['annual_electricity_cost_est'] / 12))
    
    console.print(cost_table)
    
    console.print(Panel(f"[bold green]Investment Summary[/bold green]\n"
                      f"Down Payment: {format_currency(row['down_payment'])}\n"
                      f"Closing Costs: {format_currency(row['closing_costs'])}\n"
                      f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
                      f"Loan Amount: {format_currency(row['loan_amount'])}", 
                      title="Investment Requirements"))
    
    console.print("\n")
    research_choice = questionary.select(
        "Would you like to generate or view rental market research for this property?",
        choices=[
            "Generate new rent research (AI-powered)",
            "View existing research reports", 
            "Generate rent estimates from report",
            "Skip - return to main menu"
        ]
    ).ask()
    
    if research_choice == "Generate new rent research (AI-powered)":
        handle_rent_research_generation(property_id)
    elif research_choice == "View existing research reports":
        handle_view_research_reports(property_id)
    elif research_choice == "Generate rent estimates from report":
        handle_generate_rent_estimates(property_id)

def handle_rent_research_generation(property_id: str):
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
        else:
            console.print("[red]❌ Research generation failed.[/red]")
            
    except Exception as e:
        console.print(f"[red]Error during research generation: {str(e)}[/red]")

def handle_view_research_reports(property_id: str):
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

def display_rent_estimates_comparison(property_id: str, estimates: dict, existing_estimates: dict, 
                                    unit_configs: list, result_cost: float, selected_report_info: str) -> bool:
    """
    Display detailed comparison between current and new rent estimates.
    
    Returns True if user wants to update database, False otherwise.
    """
    estimates_table = Table(title=f"Rent Estimate Comparison for {property_id}", 
                          show_header=True, header_style="bold green")
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
        for unit in config['units']:
            unit_num = unit['unit_num']
            config_key = config['config_key']
            base_name = f"unit_{unit_num}_{config_key}"
            
            new_low = estimates.get(f"{base_name}_rent_estimate_low", 0)
            new_primary = estimates.get(f"{base_name}_rent_estimate", 0)
            new_high = estimates.get(f"{base_name}_rent_estimate_high", 0)
            existing_data = existing_estimates.get(base_name, {})
            current_primary = existing_data.get('rent_estimate', 0)
            difference = new_primary - current_primary
            change_percent = (difference / current_primary * 100) if current_primary > 0 else 0
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
                f"[{change_style}]{change_percent_formatted}[/{change_style}]"
            )
    
    total_difference = total_new_primary - total_current_primary
    total_change_percent = (total_difference / total_current_primary * 100) if total_current_primary > 0 else 0
    
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
        f"[bold {total_change_style}]{total_change_percent_formatted}[/bold {total_change_style}]"
    )
    
    console.print("\n")
    console.print(estimates_table)
    
    range_amount = total_new_high - total_new_low
    range_percent = (range_amount / total_new_primary * 100) if total_new_primary > 0 else 0
    unit_count = sum(len(config['units']) for config in unit_configs)
    
    console.print(Panel(
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
        border_style="cyan"
    ))
    
    console.print("\n")
    update_database = questionary.confirm(
        "Would you like to update the database with these new rent estimates?",
        default=False
    ).ask()
    
    return update_database

def is_property_maps_done(row) -> bool:
    places = ['gas_station', 'school', 'university', 'grocery_or_supermarket', 'hospital', 'park', 'transit_station']
    is_done = True

    for place in places:
        distance = row.get(f'{place}_distance_miles')
        count = row.get(f'{place}_count_5mi')

        if pd.isna(distance) and distance is None:
            is_done = False
        if pd.isna(count) and count is None:
            is_done = False

    return is_done

def display_phase2_data_checklist():
    filtered_df, reduced_df, creative_df = get_all_phase1_qualifying_properties()
    combined_df = pd.concat(
        [filtered_df, reduced_df, creative_df], ignore_index=True
    ).drop_duplicates(subset=["address1"], keep="first")

    table = Table(title="Phase 2 Data Checklist", show_header=True, header_style="bold green")

    table.add_column("Address", style="cyan")
    table.add_column("DATE", style="white")
    table.add_column("INSP", style="white")
    table.add_column("MAPS", style="white")
    table.add_column("SCHL", style="white")
    table.add_column("RENT", style="white")
    table.add_column("NGBH", style="white")
    table.add_column("TAXS", style="white")

    for _, row in combined_df.iterrows():
        has_listing = "[green]done[/green]" if row["listed_date"] else "[dim]none[/dim]"
        has_inspection_done = "[green]done[/green]" if inspections.is_property_inspection_done(row["address1"]) else "[dim]none[/dim]"
        has_maps_data = "[green]done[/green]" if is_property_maps_done(row) else "[dim]none[/dim]"
        has_school_district = "[green]done[/green]" if row["school_district"] else "[dim]none[/dim]"
        has_rent_dd = "[green]done[/green]" if row["rent_dd_completed"] else "[dim]none[/dim]"
        has_neighborhood_dd = "[green]done[/green]" if row["neighborhood_dd_completed"] else "[dim]none[/dim]"
        has_taxes = "[green]done[/green]" if row.get("annual_tax_amount") else "[dim]none[/dim]"

        table.add_row(
            row["address1"],
            has_listing,
            has_inspection_done,
            has_maps_data,
            has_school_district,
            has_rent_dd,
            has_neighborhood_dd,
            has_taxes,
        )

    console.print(table)

def handle_generate_rent_estimates(property_id: str):
    """Handle generating rent estimates from an existing research report"""
    researcher = RentResearcher(supabase, console)
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
    
    selected_id = None
    for report in reports:
        if report['id'][:8] in selected:
            selected_id = report['id']
            break
    
    if not selected_id:
        console.print("[red]Error: Could not identify selected report.[/red]")
        return
    
    try:
        result = researcher.generate_rent_estimates_from_report(selected_id)
        
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

                    reload_dataframe()
                    
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

def handle_rent_research_after_add(property_id):
    researcher = RentResearcher(supabase, console)
    property_id = property_details['address1']
    report_id = researcher.generate_rent_research(property_id)

    try:
        result = researcher.generate_rent_estimates_from_report(report_id)
        
        if result["success"]:
            estimates = result["estimates"]
            existing_estimates = result.get("existing_estimates", {})
            unit_configs = result.get("unit_configs", [])
            
            display_rent_estimates_comparison(
                property_id, estimates, existing_estimates, unit_configs, 
                result['cost'], "Report we just made" 
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

def handle_changing_loan():
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

  load_loan(selected_loan_id)
  reload_dataframe()

using_application = True

def run_all_properties_options():
    using_all_properties = True
    choices = [
        "Phase 1 - Qualifiers",
        "Phase 2 - Data Checklist",
        "Phase 2 - Qualifiers",
        "All properties - Active (FHA)",
        "All properties - Reduce price and recalculate",
        "All properties - Property Info",
        "All properties - Creative Pricing",
        "All properties - Sold / Passed (FHA)",
        "Go back",
    ]

    while using_all_properties:
        option = questionary.select(
            "What would you like to display?", choices=choices
        ).ask()

        if option == "Go back":
            using_all_properties = False
        elif option == "All properties - Active (FHA)":
            dataframe = df.query("status == 'active'")
            display_all_properties(
                properties_df=dataframe, title="All active properties using FHA"
            )
        elif option == "Phase 1 - Qualifiers":
            display_all_phase1_qualifying_properties()
        elif option == "All properties - Reduce price and recalculate":
            percent = questionary.text(
                "Enter a percent to reduce purchase price by"
            ).ask()
            converted = float(int(percent)) / 100.0
            reduced_df = get_reduced_pp_df(reduction_factor=converted)
            display_all_properties(properties_df=reduced_df, title=f"{converted}% Price Reduction")
        elif option == "All properties - Property Info":
            display_all_properties_info(properties_df=df)
        elif option == "All properties - Creative Pricing":
            display_creative_pricing_all_properties()
        elif option == "All properties - Sold / Passed (FHA)":
            dataframe = df.query("status != 'active'")
            display_all_properties(
                properties_df=dataframe,
                title="All inactive properties using FHA",
                show_status=True,
            )
        elif option == "Phase 2 - Data Checklist":
            display_phase2_data_checklist()
        elif option == "Phase 2 - Qualifiers":
            pass

def run_loans_options():
  using_loans = True
  choices = ["Go back", "Add new loan", "View loans", "Change loans for session"]
  loans_provider = LoansProvider(supabase, console)

  while using_loans:
    option = questionary.select("Select an option", choices=choices).ask()
    if option == "Go back":
      using_loans = False
    elif option == "Add new loan":
      console.print("Let's add a new loan", style="bold blue")
      proceed = False
      while not proceed:
        loan_details = loans_provider.collect_loan_details()
        console.print(Panel(f"Loan Name: {loan_details.name}\n"
                          f"Interest Rate: {loan_details.interest_rate * 100:.2f}%\n"
                          f"APR Rate: {loan_details.apr_rate * 100:.2f}%\n"
                          f"Down Payment: {loan_details.down_payment_rate * 100:.1f}%\n"
                          f"Term: {loan_details.years} years\n"
                          f"MIP Upfront: {loan_details.mip_upfront_rate * 100:.2f}%\n"
                          f"MIP Annual: {loan_details.mip_annual_rate * 100:.2f}%\n"
                          f"Upfront Discounts: ${loan_details.upfront_discounts:,.2f}\n"
                          f"Preapproved Amount: ${loan_details.preapproved_amount:,}\n"
                          f"Expiration Date: {loan_details.expiration_date}",
                          title="Loan Details Review"))
        proceed = questionary.confirm("Does everything look correct?").ask()
        
        if not proceed:
          console.print("Please enter the loan details again", style="bold blue")
      success = loans_provider.add_loan(loan_details)
      if success:
        console.print("[green]Loan added successfully![/green]")
      else:
        console.print("[red]Failed to add loan[/red]")
    elif option == "View loans":
      loans_provider.display_loans()
    elif option == "Change loans for session":
      handle_changing_loan()

if __name__ == "__main__":
  while using_application:
    choices = ['All properties', 'One property', "Add new property", "Loans", "Refresh data", "Quit"]
    option = questionary.select("What would you like to analyze?", choices=choices).ask()

    if option == "Quit":
      using_application = False
    elif option == "All properties":
      run_all_properties_options()
    elif option == "One property":
      property_ids = []
      properties_get_response = supabase.table('properties').select('address1').execute()
      for row in properties_get_response.data:
        property_ids.append(row['address1'])
      property_id = inquirer.fuzzy(
          message="Type to search properties",
          choices=property_ids,
          default="",
          multiselect=False,
          validate=None,
          invalid_message="Invalid input"
      ).execute()
      analyze_property(property_id)
    elif option == "Add new property":
      property_details = run_add_property(supabase_client=supabase)
      handle_rent_research_after_add(property_details['address1'])
      reload_dataframe()
    elif option == "Loans":
      run_loans_options()
    elif option == "Refresh data":
      reload_dataframe()
