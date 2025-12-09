import math
import os
from datetime import datetime

import pandas as pd
import questionary
from dotenv import load_dotenv
from InquirerPy import inquirer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from supabase import Client, create_client

from add_property import get_or_create_neighborhood, run_add_property
from exporter import export_property_analysis
from helpers import (
    calculate_monthly_take_home,
    calculate_mortgage,
    express_percent_as_months_and_days,
    format_currency,
    format_number,
    format_percentage,
    is_property_assessment_done_vectorized,
    is_property_maps_done_vectorized,
    get_expected_gains,
    calculate_payback_period,
    get_state_tax_rate,
    calculate_net_proceeds,
    calculate_irr,
    calculate_additional_room_rent,
    calculate_npv,
    calculate_quintile_colors_for_metrics,
    calculate_roe
)
from inspections import InspectionsClient
from loans import LoansProvider
from neighborhood_assessment import edit_neighborhood_assessment
from neighborhoods import NeighborhoodsClient
from property_assessment import RiskAssessmentClient, edit_property_assessment
from property_summary import PropertySummaryClient
from rent_research import RentResearcher

load_dotenv()

console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections = InspectionsClient(supabase_client=supabase)
neighborhoods = NeighborhoodsClient(supabase_client=supabase, console=console)

LAST_USED_LOAN = 2
LAND_VALUE_PCT = 0.20  # 20% of purchase price is land (non-depreciable)
FEDERAL_TAX_RATE = 0.22  # 22% federal tax bracket
SELLING_COSTS_RATE = 0.07  # 7% selling costs (6% agent commission + 1% closing)
CAPITAL_GAINS_RATE = 0.15  # 15% long-term capital gains tax
DEPRECIATION_YEARS = 27.5  # Residential property depreciation period
IA_FIRSTHOME_GRANT_AMT = 2500

def load_assumptions():
    global ASSUMPTIONS 
    console.print("[yellow]Reloading assumptions...[/yellow]")
    assumptions_get_response = supabase.table("assumptions").select("*").eq("id", 1).limit(1).single().execute()
    ASSUMPTIONS = {
        "appreciation_rate": float(assumptions_get_response.data["appreciation_rate"]),
        "mf_appreciation_rate": float(assumptions_get_response.data["appreciation_rate"]) - 0.01,
        "rent_appreciation_rate": float(assumptions_get_response.data["rent_appreciation_rate"]),
        "property_tax_rate": float(assumptions_get_response.data["property_tax_rate"]),
        "home_insurance_rate": float(assumptions_get_response.data["home_insurance_rate"]),
        "vacancy_rate": float(assumptions_get_response.data["vacancy_rate"]),
        "repair_savings_rate": float(assumptions_get_response.data["repair_savings_rate"]),
        "closing_costs_rate": float(assumptions_get_response.data["closing_costs_rate"]),
        "live_in_unit_setting": assumptions_get_response.data["live_in_unit_setting"],
        "gross_annual_income": assumptions_get_response.data["gross_annual_income"],
        "state_tax_code": assumptions_get_response.data["state_tax_code"],
        "after_tax_monthly_income": calculate_monthly_take_home(
            assumptions_get_response.data["gross_annual_income"],
            assumptions_get_response.data["state_tax_code"]
        ),
        "discount_rate": assumptions_get_response.data["discount_rate"],
        "using_ia_fhb_prog": assumptions_get_response.data["using_ia_fhb_prog"],
        "ia_fhb_prog_upfront_option": assumptions_get_response.data["ia_fhb_prog_upfront_option"]
    }
    console.print(
        f"[green]Assumption set '{assumptions_get_response.data['description']}' reloaded successfully![/green]"
    )

def load_loan(loan_id):
    global LOAN
    console.print("[yellow]Reloading FHA loan data...[/yellow]")
    loan_provider = LoansProvider(supabase_client=supabase, console=console)
    loan = loan_provider.get_loan_by_id(loan_id)
    LOAN = {
        "interest_rate": loan.interest_rate,
        "apr_rate": loan.apr_rate,
        "down_payment_rate": loan.down_payment_rate,
        "loan_length_years": loan.years,
        "mip_upfront_rate": loan.mip_upfront_rate,
        "mip_annual_rate": loan.mip_annual_rate,
        "upfront_discounts": loan.upfront_discounts
    }
    console.print("[green]Loan data reloaded successfully![/green]")

def apply_calculations_on_dataframe(df):
    state_rate = get_state_tax_rate(ASSUMPTIONS['state_tax_code'])
    combined_tax_rate = FEDERAL_TAX_RATE + state_rate
    cols = ["walk_score", "transit_score", "bike_score"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    df[cols] = df[cols].fillna(0)
    df["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"]
    df["home_age"] = 2025 - df["built_in"].fillna(2025)
    df["down_payment"] = df["purchase_price"] * LOAN['down_payment_rate'] 
    df["5_pct_loan"] = df["purchase_price"] * 0.05
    df["loan_amount"] = df["purchase_price"] - df["down_payment"] + (df["purchase_price"] * LOAN['mip_upfront_rate'])
    df["monthly_mortgage"] = df["loan_amount"].apply(lambda x: calculate_mortgage(x, LOAN['apr_rate'], LOAN['loan_length_years']))
    df["monthly_mip"] = (df["loan_amount"] * LOAN['mip_annual_rate']) / 12
    df["monthly_taxes"] = (df["purchase_price"] * ASSUMPTIONS['property_tax_rate']) / 12
    df["monthly_insurance"] = (df["purchase_price"] * ASSUMPTIONS['home_insurance_rate']) / 12
    df["closing_costs"] = df["purchase_price"] * ASSUMPTIONS['closing_costs_rate']
    df["cash_needed"] = df["closing_costs"] + df["down_payment"] - LOAN['upfront_discounts'] - (IA_FIRSTHOME_GRANT_AMT if (ASSUMPTIONS['ia_fhb_prog_upfront_option'] == "GRANT" and ASSUMPTIONS['using_ia_fhb_prog']) else 0)
    df["quick_monthly_rent_estimate"] = (df["purchase_price"] + df["closing_costs"]) * 0.0075
    df['ammoritization_estimate'] = (df['loan_amount'] * 0.017) / 12
    df["total_rent"] = df['quick_monthly_rent_estimate']
    df["my_rent"] = df['quick_monthly_rent_estimate'] * 0.25 # quick and dirty calculation
    df["net_rent_y1"] = df['total_rent'] - df['my_rent']
    df["annual_rent_y1"] = df["net_rent_y1"] * 12
    # Year 1 operating expenses (before changing total_rent for SFH)
    # For SFH: uses aggregated per-room rent (house-hacking scenario)
    # For multi-family: uses total rent from all units
    df["monthly_vacancy_costs_y1"] = df["total_rent"] * ASSUMPTIONS['vacancy_rate']
    df["monthly_repair_costs_y1"] = df["total_rent"] * ASSUMPTIONS['repair_savings_rate']
    df["operating_expenses_y1"] = df["monthly_vacancy_costs_y1"] + df["monthly_repair_costs_y1"] + df["monthly_taxes"] + df["monthly_insurance"]
    # For single family homes (units == 0): switch total_rent from aggregated per-room to whole-property rent
    # This affects all Year 2 calculations and Y2-based metrics below
    # Only update where rent_estimate is not null; otherwise keep aggregated per-room rent
    # mask = (df["units"] == 0) & (df["rent_estimate"].notna())
    # df.loc[mask, "total_rent"] = df.loc[mask, "rent_estimate"].astype(float)
    df["annual_rent_y2"] = df["total_rent"] * 12
    # Year 2 operating expenses (after changing total_rent for SFH)
    # For SFH: uses whole-property rent (full rental scenario)
    # For multi-family: uses total rent from all units (same as Y1)
    df["monthly_vacancy_costs_y2"] = df["total_rent"] * ASSUMPTIONS['vacancy_rate']
    df["monthly_repair_costs_y2"] = df["total_rent"] * ASSUMPTIONS['repair_savings_rate']
    df["operating_expenses_y2"] = df["monthly_vacancy_costs_y2"] + df["monthly_repair_costs_y2"] + df["monthly_taxes"] + df["monthly_insurance"]
    # Total monthly cost uses Y2 operating expenses (conservative for Y1, accurate for Y2)
    df["total_monthly_cost_y1"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses_y1"]
    df["total_monthly_cost_y2"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses_y2"]
    df["monthly_NOI_y2"] = df["total_rent"] - df["operating_expenses_y2"]
    df["monthly_NOI_y1"] = df["net_rent_y1"] - df["operating_expenses_y1"]
    df["annual_NOI_y1"] = df["monthly_NOI_y1"] * 12
    df["annual_NOI_y2"] = df["monthly_NOI_y2"] * 12
    df["monthly_cash_flow_y1"] = df["net_rent_y1"] - df["total_monthly_cost_y1"] + df['ammoritization_estimate']
    df["monthly_cash_flow_y2"] = df["total_rent"] - df["total_monthly_cost_y2"] + df['ammoritization_estimate']
    df["annual_cash_flow_y1"] = df["monthly_cash_flow_y1"] * 12
    df["annual_cash_flow_y2"] = df["monthly_cash_flow_y2"] * 12


    # all of these calculations for investmentment metrics are useful if you use the quick and dirty rent estimate
    # so instead, these have to use the ESTIMATED MARKET RENT

    df["cap_rate_y1"] = df["annual_NOI_y1"] / df["purchase_price"]
    df["cap_rate_y2"] = df["annual_NOI_y2"] / df["purchase_price"]
    df["CoC_y1"] = df["annual_cash_flow_y1"] / df["cash_needed"]
    df["CoC_y2"] = df["annual_cash_flow_y2"] / df["cash_needed"]
    df["GRM_y1"] = df["purchase_price"] / df["annual_rent_y1"] # Gross Rent Multiplier (lower = better)
    df["GRM_y2"] = df["purchase_price"] / df["annual_rent_y2"]
    # Industry-standard metrics using Year 2 assumptions (whole-property rent for SFH, total units for multi-family)
    # These are used for property evaluation, lender analysis, and market comparisons
    df["MGR_PP"] = df["total_rent"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
    df["OpEx_Rent"] = df["operating_expenses_y2"] / df["total_rent"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
    df["DSCR"] = df["total_rent"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25
    df["ltv_ratio"] = df["loan_amount"] / df["purchase_price"] # Loan-to-Value ratio
    df["price_per_door"] = df.apply(
        lambda row: row["purchase_price"] / row["beds"] if row["units"] == 0 else row["purchase_price"] / row["units"],
        axis=1
    ) # Price per unit/door (or per bedroom for single family)
    df["rent_per_sqft"] = df["total_rent"] / df["square_ft"] # Monthly rent per square foot (Y2 for SFH)
    df["break_even_occupancy"] = df["total_monthly_cost_y2"] / df["total_rent"] # Break-even occupancy rate
    df["break_even_vacancy"] = 1.0 - df["break_even_occupancy"]
    df["oer"] = df["operating_expenses_y2"] / df["total_rent"] # Operating Expense Ratio (standard industry metric)
    df["egi"] = df["total_rent"] - df["monthly_vacancy_costs_y2"] # Effective Gross Income
    df["debt_yield"] = df["annual_NOI_y2"] / df["loan_amount"] # Debt Yield (lender metric)
    df["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5,ASSUMPTIONS,LOAN,))
    df["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10,ASSUMPTIONS,LOAN,))
    df["20y_forecast"] = df.apply(get_expected_gains, axis=1, args=(20,ASSUMPTIONS,LOAN,))
    df["mobility_score"] = (df["walk_score"] * 0.6) + (df["transit_score"] * 0.30) + (df["bike_score"] * 0.10)
    df["piti"] = df['monthly_mortgage'] + df['monthly_mip'] + df['monthly_taxes'] + df['monthly_insurance']
    df['costs_to_income'] = df["piti"] / ASSUMPTIONS['after_tax_monthly_income']
    df["monthly_depreciation"] = (df["purchase_price"] * (1 - LAND_VALUE_PCT)) / DEPRECIATION_YEARS / 12
    df["tax_savings_monthly"] = df["monthly_depreciation"] * combined_tax_rate
    df["after_tax_cash_flow_y1"] = df["monthly_cash_flow_y1"] + df["tax_savings_monthly"]
    df["after_tax_cash_flow_y2"] = df["monthly_cash_flow_y2"] + df["tax_savings_monthly"]
    df["future_value_5yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (ASSUMPTIONS['appreciation_rate'] if row["units"] == 0 else ASSUMPTIONS['mf_appreciation_rate'])) ** 5),
        axis=1
    )
    df["future_value_10yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (ASSUMPTIONS['appreciation_rate'] if row["units"] == 0 else ASSUMPTIONS['mf_appreciation_rate'])) ** 10),
        axis=1
    )
    df["future_value_20yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (ASSUMPTIONS['appreciation_rate'] if row["units"] == 0 else ASSUMPTIONS['mf_appreciation_rate'])) ** 20),
        axis=1
    )
    df["net_proceeds_5yr"] = df.apply(calculate_net_proceeds, axis=1, args=(5, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE, ASSUMPTIONS, LOAN))
    df["net_proceeds_10yr"] = df.apply(calculate_net_proceeds, axis=1, args=(10, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE, ASSUMPTIONS, LOAN))
    df["net_proceeds_20yr"] = df.apply(calculate_net_proceeds, axis=1, args=(20, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE, ASSUMPTIONS, LOAN))
    df["equity_multiple_5yr"] = (df["5y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    df["equity_multiple_10yr"] = (df["10y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    df["equity_multiple_20yr"] = (df["20y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    df["avg_annual_return_5yr"] = ((df["5y_forecast"] / df["cash_needed"]) / 5) * 100
    df["avg_annual_return_10yr"] = ((df["10y_forecast"] / df["cash_needed"]) / 10) * 100
    df["avg_annual_return_20yr"] = ((df["20y_forecast"] / df["cash_needed"]) / 20) * 100
    df["roe_y2"] = df.apply(calculate_roe, axis=1, args=[LOAN,])
    df["leverage_benefit"] = df["CoC_y2"] - (df["annual_NOI_y2"] / df["purchase_price"])
    df["payback_period_years"] = df.apply(calculate_payback_period, axis=1)
    df["irr_5yr"] = df.apply(calculate_irr, axis=1, args=(5,ASSUMPTIONS))
    df["irr_10yr"] = df.apply(calculate_irr, axis=1, args=(10,ASSUMPTIONS))
    df["irr_20yr"] = df.apply(calculate_irr, axis=1, args=(20,ASSUMPTIONS))
    df["npv_5yr"] = df.apply(calculate_npv, axis=1, args=(5,ASSUMPTIONS))
    df["npv_10yr"] = df.apply(calculate_npv, axis=1, args=(10,ASSUMPTIONS))
    df["npv_20yr"] = df.apply(calculate_npv, axis=1, args=(20,ASSUMPTIONS))
    df["fair_value_5yr"] = df["purchase_price"] + df["npv_5yr"]
    df["fair_value_10yr"] = df["purchase_price"] + df["npv_10yr"]
    df["fair_value_20yr"] = df["purchase_price"] + df["npv_20yr"]
    df["value_gap_pct_5yr"] = (df["npv_5yr"] / df["cash_needed"]) * 100
    df["value_gap_pct_10yr"] = (df["npv_10yr"] / df["cash_needed"]) * 100
    df["value_gap_pct_20yr"] = (df["npv_20yr"] / df["cash_needed"]) * 100
    df["beats_market"] = df["npv_10yr"] > 0
    df["cash_flow_y1_downside_10pct"] = (df["net_rent_y1"] * 0.9) - df["total_monthly_cost_y1"]
    df["cash_flow_y2_downside_10pct"] = (df["total_rent"] * 0.9) - df["total_monthly_cost_y2"]
    df["fha_self_sufficiency_ratio"] = (df["total_rent"] * 0.75) / df["piti"]  # Uses Y2 rent (whole-property for SFH)
    return df

def reload_dataframe():
    global df, rents
    console.print("[yellow]Reloading property data...[/yellow]")
    properties_get_response = supabase.table('properties').select('*').limit(10000).execute()
    df = pd.DataFrame(properties_get_response.data)
    rents_get_response = supabase.table('rent_estimates').select('*').limit(10000).execute()
    rents = pd.DataFrame(rents_get_response.data)
    rents = rents.drop(['id'], axis=1)
    rent_summary = rents.groupby("address1")["rent_estimate"].agg(["sum", "min"]).reset_index()
    rent_summary.columns = ["address1", "market_total_rent_estimate", "min_rent"]
    min_rent_indices = rents.groupby("address1")["rent_estimate"].idxmin()
    min_rent_units = rents.loc[min_rent_indices, ["address1", "unit_num", "beds"]].reset_index(drop=True)
    min_rent_units.columns = ["address1", "min_rent_unit", "min_rent_unit_beds"]
    rent_summary = rent_summary.merge(min_rent_units, on="address1", how="left")
    rent_summary["market_estimate_net_rent_y1"] = rent_summary["market_total_rent_estimate"] - rent_summary["min_rent"]
    df = df.merge(rent_summary, on="address1", how="left")
    neighborhoods_df = neighborhoods.get_neighborhoods_dataframe(supabase)
    df = df.merge(neighborhoods_df, on="address1", how="left")
    df = apply_calculations_on_dataframe(df=df)
    console.print("[green]Property data reloaded successfully![/green]")

load_assumptions()
load_loan(LAST_USED_LOAN)
reload_dataframe()

def display_all_properties(properties_df, title, show_status=False, show_min_rent_data=False, show_prop_type=False, sort_by="units"):
    dataframe = df if properties_df is None else properties_df
    if sort_by == "units":
        dataframe = dataframe.sort_values(by="units")
    elif sort_by == "y2_cf":
        dataframe = dataframe.sort_values(by="monthly_cash_flow_y2")
    table = Table(title=title, show_header=True, header_style="bold magenta")
    mobility_75th_percentile = df["mobility_score"].quantile(0.75)
    mobility_25th_percentile = df["mobility_score"].quantile(0.25)
    forecast_10y_75th_percentile = df["10y_forecast"].quantile(0.75)
    forecast_10y_25th_percentile = df["10y_forecast"].quantile(0.25)
    irr_10yr_75th_percentile = df["irr_10yr"].quantile(0.75)
    irr_10yr_25th_percentile = df["irr_10yr"].quantile(0.25)
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
    table.add_column("CF/mo Y1", justify="right", no_wrap=True)
    table.add_column("CF/mo Y2", justify="right", no_wrap=True)
    # table.add_column("NOI Y2", justify="right", style="yellow")
    # table.add_column("CapR Y1", justify="right", style="blue")
    # table.add_column("CapR Y2", justify="right", style="blue")
    # table.add_column("CoC Y2", justify="right", style="purple")
    # table.add_column("1% Rule", justify="right", style="cyan")
    # table.add_column("50% Rule", justify="right", style="magenta")
    # table.add_column("DSCR", justify="right", style="blue")
    table.add_column("Cost/Inc", justify="right", style="bold white")
    # table.add_column("DS", justify="right", style="bold white")  # deal score
    # table.add_column("MS", justify="right", style="bold white")  # mobility score
    # table.add_column("10Y", justify="right", style="bold white")  # 10 year investment growth
    table.add_column("IRR 10Y", justify="right", style="bold white")  
    # table.add_column("NPV10Y", justify="right", style="bold white") # Net present value 10 years

    if show_status:
        table.add_column("Status", justify="right", style="bold white")

    if show_min_rent_data:
        table.add_column("MinR Unit Beds", justify="right", style="bold white")
        table.add_column("Add. Beds", justify="right", style="bold white")
        table.add_column("Add. Rent", justify="right", style="bold white")

    for _, row in dataframe.iterrows():
        cf_y1_style = "red" if row["monthly_cash_flow_y1"] < 0 else "green"
        cf_y2_style = "red" if row["monthly_cash_flow_y2"] < 0 else "green"

        noi_style = "red" if row["monthly_NOI_y2"] < 0 else "green"

        opex_rent_style = (
            "green"
            if 0.45 <= row["OpEx_Rent"] <= 0.55
            else ("yellow" if 0.35 <= row["OpEx_Rent"] <= 0.65 else "red")
        )
        dscr_style = "green" if row["DSCR"] >= 1.25 else "red"
        mgr_pp_style = "green" if row["MGR_PP"] >= 0.01 else "red"

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

        irr_10yr_style = (
            "green"
            if row["irr_10yr"] >= irr_10yr_75th_percentile
            else ("yellow" if row["irr_10yr"] >= irr_10yr_25th_percentile else "red")
        )

        price_style = get_quintile_color(
            row["purchase_price"], price_20th, price_40th, price_60th, price_80th
        )
        cash_style = get_quintile_color(
            row["cash_needed"], cash_20th, cash_40th, cash_60th, cash_80th
        )

        costs_to_income_style = (
            "green"
            if row["costs_to_income"] <= costs_to_income_25th_percentile
            else ("yellow" if row["costs_to_income"] <= costs_to_income_75th_percentile else "red")
        )

        npv_style = "red" if row["npv_10yr"] <= 0 else "green" 

        prop_types = { 0: "SFH", 2: "2PX", 3: "3PX", 4: "4PX" }
        prop_type_styles = { 0: "yellow", 2: "red", 3: "blue", 4: "green" } 

        row_args = [str(row["address1"])]

        if show_prop_type:
            pt_style = prop_type_styles[row["units"]]
            row_args.append(f"[{pt_style}]{prop_types[row["units"]]}[/{pt_style}]")

        row_args.extend([
            f"[{price_style}]{format_currency(row['purchase_price'])}[/{price_style}]",
            f"[{cash_style}]{format_currency(row['cash_needed'])}[/{cash_style}]",
            format_currency(row["total_monthly_cost_y2"]),
            f"[{cf_y1_style}]{format_currency(row['monthly_cash_flow_y1'])}[/{cf_y1_style}]",
            f"[{cf_y2_style}]{format_currency(row['monthly_cash_flow_y2'])}[/{cf_y2_style}]",
            # f"[{noi_style}]{format_currency(row['monthly_NOI_y2'])}[/{noi_style}]",
            # format_percentage(row["cap_rate_y1"]),
            # format_percentage(row["cap_rate_y2"]),
            # format_percentage(row["CoC_y2"]),
            # f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]",
            # f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]",
            # f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]",
            f"[{costs_to_income_style}]{format_percentage(row['costs_to_income'])}[/{costs_to_income_style}]",
            # f"[{mobility_score_style}]{int(row['mobility_score'])}[/{mobility_score_style}]",
            # f"[{forecast_10y_style}]{format_currency(row['10y_forecast'])}[/{forecast_10y_style}]",
            f"[{irr_10yr_style}]{format_percentage(row['irr_10yr'])}[/{irr_10yr_style}]",
            # f"[{npv_style}]{format_currency(row["npv_10yr"])}[/{npv_style}]"
        ])

        if show_status:
            row_args.append(row["status"])
        
        if show_min_rent_data:
            row_args.append(str(row["min_rent_unit_beds"]))
            row_args.append(str(int(row["min_rent_unit_beds"] - 1)))
            row_args.append(str(calculate_additional_room_rent(row)))
            
        table.add_row(*row_args)

    console.print(table)

def display_y2_calculations(properties_df=None):
    """Display property options table with Y2 financial calculations"""
    dataframe = df if properties_df is None else properties_df
    dataframe = dataframe.sort_values(by="units")  # Default sort

    table = Table(title="Y2 Property Calculations", show_header=True, header_style="bold magenta")

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
    table.add_column("Y2 Repair Cost", justify="right", style="yellow")
    table.add_column("Y2 Vacancy Reserve", justify="right", style="yellow")
    table.add_column("Monthly CF Y2", justify="right")

    # Iterate and add rows
    for _, row in dataframe.iterrows():
        # Determine cashflow color
        cf_y2_style = "red" if row["monthly_cash_flow_y2"] < 0 else "green"

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
            format_currency(row["monthly_repair_costs_y2"]),
            format_currency(row["monthly_vacancy_costs_y2"]),
            f"[{cf_y2_style}]{format_currency(row['monthly_cash_flow_y2'])}[/{cf_y2_style}]"
        ]

        table.add_row(*row_args)

    console.print(table)

def display_property_metrics(properties_df=None):
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

def get_all_phase1_qualifying_properties(active=True):
    """
    This method filters all properties based on our criteria for what is a financially viable property
    Current criteria using quick rent estimates:
      - status = 'active'
      - Cash needed must be below $25,000
      - SFH/MF: Monthly Cashflow with cheapest unit not rented above -400 (house hacking)
      - SFH/MF: Fully rented monthly cashflow above -200
      - Square Feet must be greater than or equal to 1000
    Additional criteria when using market rent estimates:
      - 1% rule (monthly gross rent must be 1% or more of purchase price)
      - 50% rule (operating expenses must be 50% or lower than gross rent)
      - Debt Service Coverage Ratio should be above 1.25
      - Triplexes / Fourplexes must pass FHA self-sufficiency test (Gross Rent * 0.75 >= PITI)
      - Net Present Value in 10 years must be positive, thus beating the stock market
    """
    status_criteria = "status == 'active'" if active else "status != 'active'"
    criteria = (
        f"{status_criteria} "
        "& square_ft >= 1000 "
        "& cash_needed <= 25000 "
        "& ((units == 0 & monthly_cash_flow_y2 >= -200) | (units > 0 & monthly_cash_flow_y2 >= -200)) "
        # "& MGR_PP > 0.01 "
        # "& OpEx_Rent < 0.5 "
        # "& DSCR > 1.25 "
        # "& monthly_cash_flow_y1 >= -400 "
        # "& ((units >= 3 & fha_self_sufficiency_ratio >= 1) | (units < 3)) "
        # "& beats_market "
    )

    base_df = df.copy()
    filtered_df = base_df.query(criteria).copy()
    filtered_df["qualification_type"] = "current"
    qualifier_address1s = filtered_df["address1"].tolist()
    reduced_df = get_reduced_pp_df(0.10)
    reduced_df = reduced_df.query(criteria).copy()
    reduced_df["qualification_type"] = "contingent"
    reduced_df = reduced_df[~reduced_df["address1"].isin(qualifier_address1s)].copy()
    creative_df = get_additional_room_rental_df()
    creative_df = creative_df.query(criteria).copy()
    creative_df["qualification_type"] = "creative"
    return filtered_df, reduced_df, creative_df 

def get_combined_phase1_qualifiers(active=True):
    current_df, reduced_df, creative_df = get_all_phase1_qualifying_properties(active=active)
    combined = pd.concat(
        [current_df, reduced_df, creative_df], ignore_index=True
    ).drop_duplicates(subset=["address1"], keep="first") 
    return combined

def get_phase1_research_list():
    """
    Criteria for the research list:
    - Neighborhood letter grade must be C or higher
    - The qualification type must be CURRENT or the property is For Sale Buy Owner
    - Cashflow Year 2 must be above -$50
    """
    current_df, contingent_df, creative_df = get_all_phase1_qualifying_properties()
    combined = pd.concat([current_df, contingent_df, creative_df], ignore_index=True).drop_duplicates(subset=["address1"], keep="first")
    criteria = "(neighborhood_letter_grade in ['A','B','C'] & qualification_type == 'current') | is_fsbo"
    filtered = combined.query(criteria).copy()
    return filtered 

def get_all_phase2_properties():
    """
    This method filters phase 1 qualifiers based property condition, rentability, and affordability 
    Current criteria:
      - property must qualify for phase 1 research list
      - property must not have any 'deal breakers'
      - fixed monthly costs to after tax income ratio must be greater than 0.45
      - Neighborhood Letter Grade must be C or higher
    """
    p1_df = get_combined_phase1_qualifiers()
    checklist = get_phase2_data_checklist()

    bg_research_keys = [
      "has_listing",
      "has_maps_data",
      "has_neighborhood_analysis",
      "has_taxes",
      "has_property_assessment",
      "has_zillow_link",
      "has_built_in_year",
      "has_neighborhood"
    ]

    physical_research_keys = [
        "has_neighborhood_assessment",
        "has_inspection_done",
        "has_seller_circumstances",
        "has_rent_dd",
    ]

    # List 1 - properties that need background research to determine if we TOUR
    research_1 = [
        address for address, checks in checklist.items()
        if not all(checks[key] for key in bg_research_keys)
    ]

    # List 2 - properties that have bg research done but need physical research for Phase 2
    research_2 = [
        address for address, checks in checklist.items()
        if all(checks[key] for key in bg_research_keys) and
          not all(checks[key] for key in physical_research_keys)
    ]

    completed = [
        address for address, checks in checklist.items()
        if all(checks[key] for key in bg_research_keys + physical_research_keys) 
    ]

    research_1_df = p1_df[p1_df['address1'].isin(research_1)].copy()
    research_2_df = p1_df[p1_df['address1'].isin(research_2)].copy()
    completed_df = p1_df[p1_df['address1'].isin(completed)].copy()

    qualifying_df = [] 
    disqualifying_df = [] 

    if not completed_df.empty:
        completed_df['property_condition'] = completed_df.apply(lambda row: inspections.get_property_condition(row), axis=1) # TODO - finish this
        completed_df['has_inspection_dealbreakers'] = completed_df.apply(lambda row: inspections.has_dealbreakers(row), axis=1) # TODO - finish this
        completed_df['total_diy_repair_costs'] = completed_df.apply(lambda row: inspections.get_total_diy_repair_costs(row), axis=1)  # TODO - finish this
        completed_df['total_pro_repair_costs'] = completed_df.apply(lambda row: inspections.get_total_pro_repair_costs(row), axis=1)  # TODO - finish this
        completed_df['est_diy_repair_costs'] = completed_df.apply(lambda row: inspections.get_est_diy_repair_costs(row), axis=1)  # TODO - finish this
        completed_df['est_pro_repair_costs'] = completed_df.apply(lambda row: inspections.get_est_pro_repair_costs(row), axis=1)  # TODO - finish this
        # is_selling_at_loss (using last purchase data)
        # depreciation_rate_per_year (using last purchase data)
        # how long has current owner owned (last purchase date - today), longer = more equity = more price flexibility
        # ^ can be used in seller motivation score

        # STEP 3 - CREATE CRITERIA AND QUERY
        qualifying_criteria = "has_inspection_dealbreakers == False & costs_to_income <= 0.45 & neighborhood_letter_grade in ['A', 'B', 'C']" # todo add more here
        disqualifying_criteria = "has_inspection_dealbreaks == True | costs_to_income >= 0.45" # todo add more here
        qualifying_df = completed_df.query(qualifying_criteria)
        disqualifying_df = completed_df.query(disqualifying_criteria)

    return {
        "qualifiers": qualifying_df,
        "disqualifiers": disqualifying_df,
        "needs_research_1": research_1_df,
        "needs_research_2": research_2_df,
    }

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

def create_phase1_research_list_table(df, title):
    """Creates a simplified table for phase 1 tour list display with color styling"""
    table = Table(title=title, show_header=True, header_style="bold magenta")

    # Add columns with short names
    table.add_column(f"Address ({len(df)})", style="cyan", no_wrap=False)
    table.add_column("Neighborhood", style="dim")
    table.add_column("CFY1", justify="right")
    table.add_column("CFY2", justify="right")
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

        # Format configuration (e.g., "4BR/2BA")
        beds = int(row['beds']) if pd.notna(row['beds']) else 0
        baths = int(row['baths']) if pd.notna(row['baths']) else 0
        config = f"{beds}BR/{baths}BA"

        # Style cashflow Y1 (red if negative, green if positive)
        cfy1_value = row['monthly_cash_flow_y1']
        if cfy1_value < 0:
            cfy1_display = f"[red]{format_currency(cfy1_value)}[/red]"
        else:
            cfy1_display = f"[green]{format_currency(cfy1_value)}[/green]"

        # Style cashflow Y2 (red if negative, green if positive)
        cfy2_value = row['monthly_cash_flow_y2']
        if cfy2_value < 0:
            cfy2_display = f"[red]{format_currency(cfy2_value)}[/red]"
        else:
            cfy2_display = f"[green]{format_currency(cfy2_value)}[/green]"

        # Style cash needed (percentile-based: bottom 25% green, middle yellow, top 25% red)
        cash_value = row['cash_needed']
        if cash_value <= cash_25:
            cash_display = f"[green]{format_currency(cash_value)}[/green]"
        elif cash_value <= cash_75:
            cash_display = f"[yellow]{format_currency(cash_value)}[/yellow]"
        else:
            cash_display = f"[red]{format_currency(cash_value)}[/red]"

        # Style price (percentile-based: bottom 25% green, middle yellow, top 25% red)
        price_value = row['purchase_price']
        if price_value <= price_25:
            price_display = f"[green]{format_currency(price_value)}[/green]"
        elif price_value <= price_75:
            price_display = f"[yellow]{format_currency(price_value)}[/yellow]"
        else:
            price_display = f"[red]{format_currency(price_value)}[/red]"

        # Combine grade and neighborhood
        grade = row['neighborhood_letter_grade'] if pd.notna(row['neighborhood_letter_grade']) else 'N/A'
        neighborhood = row['neighborhood'] if pd.notna(row['neighborhood']) else 'N/A'
        neighborhood_display = f"{grade} - {neighborhood}"

        # Style Cost/Income (lower is better: bottom 25% green, middle yellow, top 25% red)
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
            cfy1_display,
            cfy2_display,
            cash_display,
            price_display,
            prop_type,
            f"{row['square_ft']}",
            config,
            cost_inc_display
        )

    return table

def display_phase1_research_list():
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

def display_phase1_total_rent_differences():
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

    dataframe['adjusted_cfy2'] = dataframe['monthly_cash_flow_y2'] + dataframe['rent_difference']

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
    table.add_column("CFY2", justify="right")
    table.add_column('Adjusted CFY2', justify="right")

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

        adj_cfy2_color = "green" if row['adjusted_cfy2'] > 0 else "red"
        cfy2_color = "green" if row['monthly_cash_flow_y2'] > 0 else "red"

        table.add_row(
            str(row['address1']),
            format_currency(row['purchase_price']),
            format_currency(row['cash_needed']),
            format_currency(row['total_rent']),
            format_currency(row['market_total_rent_estimate']),
            diff_display,
            percent_display,
            f"[{cfy2_color}]{format_currency(row['monthly_cash_flow_y2'])}[/{cfy2_color}]",
            f"[{adj_cfy2_color}]{format_currency(row['adjusted_cfy2'])}[/{adj_cfy2_color}]"
        )

    # Display table
    console.print(table)

def display_all_phase2_qualifying_properties():
    dfs = get_all_phase2_properties()
    
    if len(dfs['incomplete_data']) == 0:
      console.print("[dim]All properties have complete data![/dim]")
    else:
        display_all_properties(properties_df=dfs["incomplete_data"], title="Need more data")

    if len(dfs['qualifiers']) == 0:
      console.print("[dim]No properties qualify[/dim]")
    else:
      display_all_properties(properties_df=dfs["qualifiers"], title="Phase 2 Qualifiers")

    if len(dfs["disqualifiers"]) == 0:
      console.print('[dim]No properties are disqualified[/dim]')
    else:
      display_all_properties(properties_df=dfs["disqualifiers"], title="Phase 2 Disqualifiers")

def get_additional_room_rental_df():
    dataframe = df.copy()
    df2 = dataframe.query('min_rent_unit_beds > 1').copy()
    df2["additional_room_rent"] = df2.apply(calculate_additional_room_rent, axis=1)
    df2["net_rent_y1"] = df2["net_rent_y1"] + df2["additional_room_rent"]
    df2["monthly_cash_flow_y1"] = df2["net_rent_y1"] - df2["total_monthly_cost_y1"]
    df2["annual_cash_flow_y1"] = df2["monthly_cash_flow_y1"] * 12
    df2["annual_NOI_y1"] = (df2["net_rent_y1"] - df2["operating_expenses_y1"]) * 12
    df2["cap_rate_y1"] = df2["annual_NOI_y1"] / df2["purchase_price"]
    df2["CoC_y1"] = df2["annual_cash_flow_y1"] / df2["cash_needed"]
    df2["GRM_y1"] = df2["purchase_price"] / df2["annual_rent_y1"]
    return df2

def get_reduced_pp_df(reduction_factor):
    dataframe = df.copy()
    dataframe["original_price"] = dataframe["purchase_price"]
    dataframe["purchase_price"] = dataframe["purchase_price"] * (1 - reduction_factor) # new purchase price
    dataframe = apply_calculations_on_dataframe(df=dataframe)
    return dataframe

def handle_price_cut(property_id, current_price):
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

def handle_status_change(property_id): 
    options = ["pending sale", "active", "passed", "sold", "off market"]
    new_status = questionary.select("Price cut amount", choices=options).ask()
    try:
      query = supabase.table("properties").update({ "status": new_status }).eq("address1", property_id)
      response = query.execute()
      if hasattr(response, "data"):
          print(f"Updated property data with status: {response.data}")
      else:
          print("Update response has no 'data' attribute")
    except Exception as e:
        print(f"Changing statusfor {property_id} failed: {str(e)}")

def display_all_properties_info(properties_df):
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

def analyze_property(property_id):
    """Display detailed analysis for a single property"""
    row = df[df['address1'] == property_id].iloc[0]
    
    table = Table(title=f"Property Details: {property_id}", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="yellow", no_wrap=True)
    table.add_column("Year 1 (Live-in)", justify="right", style="green")
    table.add_column("Year 2 (All Rent)", justify="right", style="blue")
    
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
                      f"Neighborhood: {row["neighborhood"]} (rated: {row["neighborhood_letter_grade"]})",
                      title="Basic Info"))

    property_rents = rents[rents['address1'] == property_id]

    if property_rents.empty:
        console.print("[red]ERROR: No rent estimates found for this property![/red]")
        console.print("[yellow]This property may need rent estimates to be generated.[/yellow]")
        return

    your_unit_index = property_rents['rent_estimate'].idxmin()

    # Use contextual labels for single family vs multi-family
    is_single_family = units_value == 0
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
    
    console.print(Panel(f"[bold blue]Rental Income Summary[/bold blue]\n"
                      f"Total Monthly Rent (All Units): {format_currency(row['total_rent'])}\n"
                      f"Your Unit Rent (Not Collected): {format_currency(row['min_rent'])}\n"
                      f"[bold]Net Monthly Income (Year 1): {format_currency(row['net_rent_y1'])}[/bold]\n"
                      f"[bold]Full Rental Income (Year 2): {format_currency(row['total_rent'])}[/bold]\n\n"
                      f"[bold yellow]Operating Expenses:[/bold yellow]\n"
                      f"Monthly Operating Expenses Y1: {format_currency(row['operating_expenses_y1'])} ({format_currency(row['operating_expenses_y1'] * 12)} annually)\n"
                      f"Monthly Operating Expenses Y2: {format_currency(row['operating_expenses_y2'])} ({format_currency(row['operating_expenses_y2'] * 12)} annually)\n\n"
                      f"[bold green]Net Operating Income (NOI):[/bold green]\n"
                      f"NOI Year 1 (Live-in): {format_currency(row['monthly_NOI_y1'])} ({format_currency(row['annual_NOI_y1'])} annually)\n"
                      f"NOI Year 2 (All Rent): {format_currency(row['monthly_NOI_y2'])} ({format_currency(row['annual_NOI_y2'])} annually)\n\n"
                      f"[bold cyan]Personal Income & Housing Costs:[/bold cyan]\n"
                      f"After-Tax Monthly Income: {format_currency(after_tax_monthly_income)}\n"
                      f"Housing Cost to Income Ratio: {format_percentage(row['costs_to_income'])}",
                      title="Income Breakdown"))

    if is_single_family:
        # For single family homes, update table title to clarify the comparison
        table.title = f"Investment Metrics: {property_id}"
        table.columns[1].header = "Year 1 (House Hacking)"
        table.columns[2].header = "Year 2 (Full Rental)"

    # Add common comparison rows
    table.add_row("Annual Rent",
                  format_currency(row['annual_rent_y1']),
                  format_currency(row['annual_rent_y2']))

    if is_single_family:
        table.add_row("Monthly Rent",
                      format_currency(row['net_rent_y1']) + " (net)",
                      format_currency(row['total_rent']))

    table.add_row("Operating Expenses",
                  format_currency(row['operating_expenses_y1']),
                  format_currency(row['operating_expenses_y2']))
    table.add_row("Total Monthly Cost",
                  format_currency(row['total_monthly_cost_y1']),
                  format_currency(row['total_monthly_cost_y2']))
    table.add_row("Monthly NOI",
                  format_currency(row['monthly_NOI_y1']),
                  format_currency(row['monthly_NOI_y2']))
    table.add_row("Annual NOI",
                  format_currency(row['annual_NOI_y1']),
                  format_currency(row['annual_NOI_y2']))
    table.add_row("[bold]Monthly Cash Flow[/bold]",
                  f"[bold {'red' if row['monthly_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y1'])}[/]",
                  f"[bold {'red' if row['monthly_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y2'])}[/]")
    table.add_row("[bold]Annual Cash Flow[/bold]",
                  f"[bold {'red' if row['annual_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y1'])}[/]",
                  f"[bold {'red' if row['annual_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y2'])}[/]")
    table.add_row("After-Tax Cash Flow",
                  format_currency(row['after_tax_cash_flow_y1']),
                  format_currency(row['after_tax_cash_flow_y2']))
    table.add_row("Cap Rate",
                  format_percentage(row['cap_rate_y1']),
                  format_percentage(row['cap_rate_y2']))
    table.add_row("Cash on Cash Return",
                  format_percentage(row['CoC_y1']),
                  format_percentage(row['CoC_y2']))
    table.add_row("Gross Rent Multiplier",
                  format_number(row['GRM_y1']),
                  format_number(row['GRM_y2']))

    downside_y1_style = "green" if row['cash_flow_y1_downside_10pct'] > 0 else "red"
    downside_y2_style = "green" if row['cash_flow_y2_downside_10pct'] > 0 else "red"
    table.add_row("Cash Flow (10% Rent Drop)",
                  f"[{downside_y1_style}]{format_currency(row['cash_flow_y1_downside_10pct'])}[/{downside_y1_style}]",
                  f"[{downside_y2_style}]{format_currency(row['cash_flow_y2_downside_10pct'])}[/{downside_y2_style}]")

    # Industry-standard metrics (primarily Y2-based for SFH)
    mgr_pp_style = "green" if row['MGR_PP'] >= 0.01 else "red"
    opex_rent_style = "green" if 0.45 <= row['OpEx_Rent'] <= 0.55 else ("yellow" if 0.35 <= row['OpEx_Rent'] <= 0.65 else "red")
    dscr_style = "green" if row['DSCR'] >= 1.25 else "red"
    fha_style = "green" if row["fha_self_sufficiency_ratio"] >= 1 else "red"

    if is_single_family:
        # For SFH, show OER and break-even for both years
        oer_y1 = row['operating_expenses_y1'] / row['total_rent'] if row['total_rent'] > 0 else 0
        break_even_y1 = row['total_monthly_cost_y1'] / row['total_rent'] if row['total_rent'] > 0 else 0
        oer_y1_style = "green" if 0.45 <= oer_y1 <= 0.55 else ("yellow" if 0.35 <= oer_y1 <= 0.65 else "red")

        table.add_row("Operating Expense Ratio",
                      f"[{oer_y1_style}]{format_percentage(oer_y1)}[/{oer_y1_style}]",
                      f"[{opex_rent_style}]{format_percentage(row['oer'])}[/{opex_rent_style}]")
        table.add_row("Break-Even Occupancy",
                      format_percentage(break_even_y1),
                      format_percentage(row['break_even_occupancy']))
    else:
        table.add_row("Operating Expense Ratio","",f"[{opex_rent_style}]{format_percentage(row['oer'])}[/{opex_rent_style}]")
        table.add_row("Break-Even Occupancy","",format_percentage(row['break_even_occupancy']))

    table.add_row("1% Rule (MGR/PP)","",f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]")
    table.add_row("50% Rule (OpEx/Rent)","",f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]")
    table.add_row("DSCR (Rent/Mortgage)","",f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]")
    table.add_row("FHA Self Sufficiency Ratio","",f"[{fha_style}]{format_percentage(row['fha_self_sufficiency_ratio'])}[/{fha_style}]")
    table.add_row("Rent Per Sqft","",format_currency(row['rent_per_sqft']))
    table.add_row("Break-Even Vacancy","",express_percent_as_months_and_days(row["break_even_vacancy"]))
    table.add_row("Effective Gross Income","",format_currency(row['egi']))
    table.add_row("Debt Yield","",format_percentage(row['debt_yield']))

    # Property-level metrics (same for both years)
    table.add_row("LTV Ratio","",format_percentage(row['ltv_ratio']))
    price_per_label = "Price Per Bedroom" if is_single_family else "Price Per Door"
    table.add_row(price_per_label,"",format_currency(row['price_per_door']))
    table.add_row("Monthly Depreciation Deduction","",format_currency(row['monthly_depreciation']))
    table.add_row("Monthly Tax Savings","",format_currency(row['tax_savings_monthly']))
    table.add_row("Return on Equity (ROE) Y2","",format_percentage(row['roe_y2']))
    table.add_row("Leverage Benefit","",format_percentage(row['leverage_benefit']))
    payback_display = f"{row['payback_period_years']:.1f} years" if row['payback_period_years'] != float('inf') else "Never"
    table.add_row("Payback Period","",payback_display)

    console.print(table)
    projections_table = Table(title="Investment Projections", show_header=True, header_style="bold cyan")
    projections_table.add_column("Metric", style="yellow", no_wrap=True)
    projections_table.add_column("5Y", justify="right", style="green")
    projections_table.add_column("10Y", justify="right", style="blue")
    projections_table.add_column("20Y", justify="right", style="magenta")
    projections_table.add_row(
        "Investment Gain",
        format_currency(row['5y_forecast']),
        format_currency(row['10y_forecast']),
        format_currency(row['20y_forecast'])
    )
    projections_table.add_row(
        "Future Value",
        format_currency(row['future_value_5yr']),
        format_currency(row['future_value_10yr']),
        format_currency(row['future_value_20yr'])
    )
    projections_table.add_row(
        "Net Proceeds",
        format_currency(row['net_proceeds_5yr']),
        format_currency(row['net_proceeds_10yr']),
        format_currency(row['net_proceeds_20yr'])
    )
    projections_table.add_row(
        "Equity Multiple",
        format_number(row['equity_multiple_5yr']),
        format_number(row['equity_multiple_10yr']),
        format_number(row['equity_multiple_20yr'])
    )
    projections_table.add_row(
        "Avg Annual Return %",
        format_percentage(row['avg_annual_return_5yr'] / 100),
        format_percentage(row['avg_annual_return_10yr'] / 100),
        format_percentage(row['avg_annual_return_20yr'] / 100)
    )
    projections_table.add_row(
        "IRR",
        format_percentage(row['irr_5yr']),
        format_percentage(row['irr_10yr']),
        format_percentage(row['irr_20yr'])
    )
    projections_table.add_row(
        "NPV",
        format_currency(row['npv_5yr']),
        format_currency(row['npv_10yr']),
        format_currency(row['npv_20yr'])
    )
    projections_table.add_row(
        "Fair Value",
        format_currency(row['fair_value_5yr']),
        format_currency(row['fair_value_10yr']),
        format_currency(row['fair_value_20yr'])
    )
    projections_table.add_row(
        "Value Gap %",
        format_percentage(row['value_gap_pct_5yr'] / 100),
        format_percentage(row['value_gap_pct_10yr'] / 100),
        format_percentage(row['value_gap_pct_20yr'] / 100)
    )

    console.print(projections_table)

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
    cost_table.add_row("Vacancy Reserve Y1", format_currency(row['monthly_vacancy_costs_y1']), format_currency(row['monthly_vacancy_costs_y1'] * 12))
    cost_table.add_row("Vacancy Reserve Y2", format_currency(row['monthly_vacancy_costs_y2']), format_currency(row['monthly_vacancy_costs_y2'] * 12))
    cost_table.add_row("Repair Reserve Y1", format_currency(row['monthly_repair_costs_y1']), format_currency(row['monthly_repair_costs_y1'] * 12))
    cost_table.add_row("Repair Reserve Y2", format_currency(row['monthly_repair_costs_y2']), format_currency(row['monthly_repair_costs_y2'] * 12))
    cost_table.add_row("[bold]Total Monthly Cost Y1[/bold]", f"[bold red]{format_currency(row['total_monthly_cost_y1'])}[/bold red]", f"[bold red]{format_currency(row['total_monthly_cost_y1'] * 12)}[/bold red]")
    cost_table.add_row("[bold]Total Monthly Cost Y2[/bold]", f"[bold red]{format_currency(row['total_monthly_cost_y2'])}[/bold red]", f"[bold red]{format_currency(row['total_monthly_cost_y2'] * 12)}[/bold red]")
    cost_table.add_row("Electricity (est.)", format_currency(row['annual_electricity_cost_est'] / 12), format_currency(row['annual_electricity_cost_est']))
    
    console.print(cost_table)

    grant = format_currency(IA_FIRSTHOME_GRANT_AMT) if ia_fhb_prog_upfront_option == "GRANT" and using_ia_fhb_prog else "[dim]Not using grant option for Iowa First Home[/dim]"

    investment_summary = (
        f"[bold green]Investment Summary[/bold green]\n"
        f"Down Payment: {format_currency(row['down_payment'])}\n"
        f"Closing Costs: {format_currency(row['closing_costs'])}\n"
        f"Lender Discounts: {format_currency(upfront_discounts)}\n"
        f"IA FirstHome Grant: {grant}\n" 
        f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
        f"Loan Amount: {format_currency(row['loan_amount'])}"
    )

    if using_ia_fhb_prog and ia_fhb_prog_upfront_option == "LOAN" and row["units"] == 0:
        investment_summary += (
            f"\n\n[bold yellow]Iowa First-Time Homebuyer Program:[/bold yellow]\n"
            f"5% Forgivable Loan: {format_currency(row['5_pct_loan'])}\n"
            f"Primary Mortgage: {format_currency(row['loan_amount'])}\n"
            f"Total Financing: {format_currency(row['loan_amount'] + row['5_pct_loan'])}\n"
            f"[dim](5% loan due at sale or refinance)[/dim]"
        )

    console.print(Panel(investment_summary, title="Investment Requirements"))

    console.print("\n")

    # Build menu choices based on property type
    research_menu_choices = [
        "Edit property assessment",
        "View risk assessment report",
        "View property summary",
        "Edit neighborhood assessment",
        "Record price cut",
        "Change status",
        "Generate new rent research",
        "View existing research reports",
        "Generate rent estimates from report",
    ]

    if is_single_family:
        research_menu_choices.append("Generate property-wide rent research")

    research_menu_choices.extend([
        "Run neighborhood analysis",
        "Extract neighborhood letter grade",
        "Export property analysis to PDF",
        "Skip - return to main menu"
    ])

    research_choice = questionary.select(
        "Would you like to generate or view rental market research for this property?",
        choices=research_menu_choices
    ).ask()

    if research_choice == "Edit property assessment":
        edit_property_assessment(property_id, supabase, console)
    elif research_choice == "View risk assessment report":
        handle_risk_assessment(property_id)
    elif research_choice == "View property summary":
        handle_property_summary(property_id)
    elif research_choice == "Edit neighborhood assessment":
        edit_neighborhood_assessment(property_id, supabase, console)
    elif research_choice == "Generate new rent research":
        handle_rent_research_generation(property_id)
    elif research_choice == "View existing research reports":
        handle_view_research_reports(property_id)
    elif research_choice == "Generate rent estimates from report":
        handle_generate_rent_estimates(property_id)
    elif research_choice == "Generate property-wide rent research":
        handle_property_wide_research_generation(property_id)
    elif research_choice == "Run neighborhood analysis":
        handle_neighborhood_analysis(property_id)
    elif research_choice == "Extract neighborhood letter grade":
        handle_extract_neighborhood_grade(property_id)
    elif research_choice == "Record price cut":
        handle_price_cut(property_id, row["purchase_price"])
        reload_dataframe()
        display_new_property_qualification(property_id)
    elif research_choice == "Change status":
        handle_status_change(property_id)
        reload_dataframe()
    elif research_choice == "Export property analysis to PDF":
        downloads_folder = os.getenv("DOWNLOADS_FOLDER", ".")
        safe_address = property_id.replace(' ', '_').replace(',', '').replace('.', '')
        output_path = os.path.join(downloads_folder, f"{safe_address}_analysis.pdf")
        row = df[df['address1'] == property_id].iloc[0]

        loan_info = {
            'interest_rate': LOAN['interest_rate'],
            'apr_rate': LOAN['apr_rate'],
            'down_payment_rate': LOAN['down_payment_rate'],
            'years': LOAN['loan_length_years'],
            'mip_upfront_rate': LOAN['mip_upfront_rate'],
            'mip_annual_rate': LOAN['mip_annual_rate'],
        }

        assumptions_info = {
            'appreciation_rate': ASSUMPTIONS['appreciation_rate'],
            'rent_appreciation_rate': ASSUMPTIONS['rent_appreciation_rate'],
            'property_tax_rate': ASSUMPTIONS['property_tax_rate'],
            'home_insurance_rate': ASSUMPTIONS['home_insurance_rate'],
            'vacancy_rate': ASSUMPTIONS['vacancy_rate'],
            'repair_savings_rate': ASSUMPTIONS['repair_savings_rate'],
            'closing_costs_rate': ASSUMPTIONS['closing_costs_rate'],
            'discount_rate': ASSUMPTIONS['discount_rate'],
        }

        result_path = export_property_analysis(row, rents, ASSUMPTIONS['after_tax_monthly_income'], loan_info, assumptions_info, output_path)
        console.print(f"[green]PDF exported successfully to: {result_path}[/green]")

def handle_property_wide_research_generation(property_id: str):
    """Generate property-wide rent research for single family homes (whole-house rental analysis)"""
    researcher = RentResearcher(supabase, console)

    try:
        report_id = researcher.generate_property_wide_research(property_id)

        if report_id:
            console.print(f"[green]✅ Property-wide research completed! Report ID: {report_id}[/green]")

            view_now = questionary.confirm("Would you like to view the report now?").ask()

            if view_now:
                report_data = researcher.get_report_by_id(report_id)
                if report_data:
                    researcher.display_report(report_data['report_content'])

            extract_estimates = questionary.confirm(
                "Would you like to extract property-wide rent estimates and update the properties table?"
            ).ask()

            if extract_estimates:
                property_wide_result = researcher.extract_property_wide_estimates(report_id)

                if property_wide_result:
                    reload_dataframe()
                    console.print("\n[bold green]✅ Property-wide rent estimates successfully extracted and saved![/bold green]")
                else:
                    console.print("\n[bold red]❌ Failed to extract property-wide estimates.[/bold red]")
        else:
            console.print("[red]❌ Property-wide research generation failed.[/red]")

    except Exception as e:
        console.print(f"[red]Error during property-wide research generation: {str(e)}[/red]")

def handle_neighborhood_analysis(property_id: str):
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
                        reload_dataframe()
                    else:
                        console.print("[yellow]⚠ Failed to extract letter grade[/yellow]")
                except Exception as e:
                    console.print(f"[yellow]⚠ Error extracting letter grade: {str(e)}[/yellow]")
        else:
            console.print("[red]❌ Neighborhood analysis failed.[/red]")

    except Exception as e:
        console.print(f"[red]Error during neighborhood analysis: {str(e)}[/red]")

def handle_extract_neighborhood_grade(property_id: str):
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
            console.print(f"\n[yellow]⚠️  No neighborhood assigned for property: {property_id}[/yellow]")
            console.print("[yellow]Please assign a neighborhood first before extracting letter grade.[/yellow]")
            return

        # Extract neighborhood name
        neighborhood_dict = neighborhood_response.data[0].get("neighborhoods")
        if not neighborhood_dict or not isinstance(neighborhood_dict, dict) or "name" not in neighborhood_dict:
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
            console.print(f"\n[yellow]⚠️  No neighborhood report found for '{neighborhood_name}'[/yellow]")
            console.print("[yellow]Please run a neighborhood analysis first before extracting letter grade.[/yellow]")
            return

        report_id = existing_report.data[0]["id"]
        console.print(f"\n[cyan]📊 Extracting letter grade from neighborhood report for '{neighborhood_name}'...[/cyan]")

        # Extract and save the letter grade
        grade_result = neighborhoods.extract_neighborhood_grade(report_id, show_progress=True)

        if grade_result and grade_result.get('letter_grade'):
            console.print(f"\n[bold green]✓ Letter grade '{grade_result['letter_grade']}' saved to neighborhoods table[/bold green]")
            console.print(f"[dim]Confidence: {grade_result.get('confidence_score', 'N/A')}[/dim]")
            reload_dataframe()
        else:
            console.print("[red]❌ Failed to extract letter grade[/red]")

    except Exception as e:
        console.print(f"[red]Error extracting neighborhood letter grade: {str(e)}[/red]")

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
            
            extract_estimates = questionary.confirm(
                "Would you like to extract rent estimates from this report?"
            ).ask()

            if extract_estimates:
                handle_generate_rent_estimates(property_id, report_id=report_id)
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

def handle_risk_assessment(property_id: str):
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

def handle_property_summary(property_id: str):
    """Handle viewing and generating property narrative summary reports"""
    global df

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
                        from rich.markdown import Markdown

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
                    from rich.markdown import Markdown

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
                        from rich.markdown import Markdown

                        md = Markdown(report_response.data['report_content'])

                        with console.pager():
                            console.print(md)
                except Exception as e:
                    console.print(f"[red]Error displaying report: {str(e)}[/red]")

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

def display_new_property_qualification(address1):
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

def get_phase2_data_checklist():
    """
    Gets all phase 1 properties and their data checklist.
    - Uses vectorized pandas operations instead of iterrows()
    - Batches neighborhood database queries (1 query instead of N)
    - Expected speedup: 15-30x depending on dataset size

    Returns:
        Dictionary mapping address1 -> dict of completion checks
    """
    combined_df = get_combined_phase1_qualifiers()
    unique_neighborhoods = combined_df["neighborhood"].dropna().unique().tolist()
    neighborhood_analysis_cache = neighborhoods.has_neighborhood_analysis_batch(unique_neighborhoods)
    unique_addresses = combined_df["address1"].dropna().unique().tolist()
    neighborhood_assessment_cache = neighborhoods.is_neighborhood_assessment_complete_batch(unique_addresses)
    combined_df = combined_df.assign(
        _has_listing=combined_df["listed_date"].notna(),
        _has_taxes=combined_df["annual_tax_amount"].notna(),
        _has_seller_circumstances=combined_df["seller_circumstances"].notna(),
        _has_zillow_link=combined_df["zillow_link"].notna(),
        _has_built_in_year=combined_df["built_in"].notna(),
        _has_neighborhood=combined_df["neighborhood"].notna(),
        _has_rent_dd=combined_df["rent_dd_completed"].fillna(False),
        _has_inspection_done=False,
        _has_maps_data=is_property_maps_done_vectorized(combined_df),
        _has_property_assessment=is_property_assessment_done_vectorized(combined_df),
        _has_neighborhood_analysis=combined_df["neighborhood"].map(
            lambda n: neighborhood_analysis_cache.get(n, False)
            if pd.notna(n)
            else False
        ),
        _has_neighborhood_assessment=combined_df["address1"].map(
            lambda addr: neighborhood_assessment_cache.get(addr, False)
        ),
    )

    checklist = {
        address: {
            # required to determine if we tour the property
            "has_listing": has_listing,
            "has_maps_data": has_maps_data,
            "has_rent_dd": has_rent_dd,
            "has_neighborhood_analysis": has_neighborhood_analysis,
            "has_taxes": has_taxes,
            "has_property_assessment": has_property_assessment,
            "has_zillow_link": has_zillow_link,
            "has_built_in_year": has_built_in_year,
            "has_neighborhood": has_neighborhood,
            # required to determine if we can run phase 2 criteria against
            "has_neighborhood_assessment": has_neighborhood_assessment,
            "has_inspection_done": has_inspection_done,
            "has_seller_circumstances": has_seller_circumstances,
        }
        for address, has_listing, has_inspection_done, has_maps_data, has_rent_dd,
            has_neighborhood_analysis, has_neighborhood_assessment, has_taxes, has_seller_circumstances,
            has_property_assessment, has_zillow_link, has_built_in_year, has_neighborhood
        in zip(
            combined_df["address1"],
            combined_df["_has_listing"],
            combined_df["_has_inspection_done"],
            combined_df["_has_maps_data"],
            combined_df["_has_rent_dd"],
            combined_df["_has_neighborhood_analysis"],
            combined_df["_has_neighborhood_assessment"],
            combined_df["_has_taxes"],
            combined_df["_has_seller_circumstances"],
            combined_df["_has_property_assessment"],
            combined_df["_has_zillow_link"],
            combined_df["_has_built_in_year"],
            combined_df["_has_neighborhood"]
        )
    }

    return checklist

def handle_generate_rent_estimates(property_id: str, report_id: str = None):
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
                handle_neighborhood_analysis(property_id)

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

  LAST_USED_LOAN = selected_loan_id
  load_loan(LAST_USED_LOAN)
  reload_dataframe()

using_application = True

def run_all_properties_options():
    using_all_properties = True
    choices = [
        "Phase 1 - Qualifiers",
        "Phase 1 - Total Rent Differences",
        "Phase 1.5 - Research List",
        "Phase 2 - Qualifiers",
        "All properties - Active",
        "All properties - Y2 Calculations",
        "All properties - Property Info",
        "All properties - Investment Metrics",
        "All properties - Sold / Passed",
        "Go back",
    ]

    while using_all_properties:
        option = questionary.select(
            "What would you like to display?", choices=choices
        ).ask()

        if option == "Go back":
            using_all_properties = False
        elif option == "All properties - Active":
            dataframe = df.query("status == 'active'")
            display_all_properties(
                properties_df=dataframe, title="All active properties using FHA", show_prop_type=True
            )
        elif option == "Phase 1 - Qualifiers":
            display_all_phase1_qualifying_properties()
        elif option == "Phase 1.5 - Research List":
            display_phase1_research_list()
        elif option == "Phase 1 - Total Rent Differences":
            display_phase1_total_rent_differences()
        elif option == "All properties - Y2 Calculations":
            display_y2_calculations()
        elif option == "All properties - Property Info":
            display_all_properties_info(properties_df=df)
        elif option == "All properties - Investment Metrics":
            display_property_metrics()
        elif option == "All properties - Sold / Passed":
            dataframe = df.query("status != 'active'")
            display_all_properties(
                properties_df=dataframe,
                title="All inactive properties using FHA",
                show_status=True,
            )
        elif option == "Phase 2 - Qualifiers":
            display_all_phase2_qualifying_properties()

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
    choices = ['All properties', 'One property', 'One property - phase 1 research list', "Add new property", "Loans", "Refresh data", "Quit"]
    option = questionary.select("What would you like to analyze?", choices=choices).ask()

    if option == "Quit":
      using_application = False
    elif option == "All properties":
      run_all_properties_options()
    elif option == "One property":
      property_ids = []
      properties_get_response = supabase.table('properties').select('address1').limit(10000).execute()
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
    elif option == "One property - phase 1 research list":
      tour_list = get_phase1_research_list()
      property_ids = sorted(tour_list['address1'].tolist())  # Sort alphabetically

      if len(property_ids) == 0:
        console.print("[yellow]No properties on phase 1 research list yet[/yellow]\n")
      else:
        property_id = inquirer.fuzzy(
            message="Type to search phase 1 research list properties",
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
      display_new_property_qualification(property_details['address1'])
    elif option == "Loans":
      run_loans_options()
    elif option == "Refresh data":
      load_assumptions()
      load_loan(LAST_USED_LOAN)
      reload_dataframe()
