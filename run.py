import math
import os
from datetime import datetime

import numpy_financial as npf
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
from exporter import export_property_analysis
from helpers import (
  calculate_monthly_take_home,
  calculate_mortgage,
  express_percent_as_months_and_days,
  format_currency,
  format_number,
  format_percentage,
)
from inspections import InspectionsClient
from loans import LoansProvider
from neighborhoods import NeighborhoodsClient
from rent_research import RentResearcher

load_dotenv()

console = Console() 
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections = InspectionsClient(supabase_client=supabase)
neighborhoods = NeighborhoodsClient()

LAST_USED_LOAN = 1
LAND_VALUE_PCT = 0.20  # 20% of purchase price is land (non-depreciable)
FEDERAL_TAX_RATE = 0.22  # 22% federal tax bracket
SELLING_COSTS_RATE = 0.07  # 7% selling costs (6% agent commission + 1% closing)
CAPITAL_GAINS_RATE = 0.15  # 15% long-term capital gains tax
DEPRECIATION_YEARS = 27.5  # Residential property depreciation period

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
  global appreciation_rate, mf_appreciation_rate, rent_appreciation_rate, property_tax_rate, home_insurance_rate, vacancy_rate, repair_savings_rate, closing_costs_rate, live_in_unit_setting, after_tax_monthly_income, state_tax_code, discount_rate
  console.print("[yellow]Reloading assumptions...[/yellow]")
  assumptions_get_response = supabase.table('assumptions').select('*').eq('id', 1).limit(1).single().execute()
  appreciation_rate = float(assumptions_get_response.data["appreciation_rate"])
  mf_appreciation_rate = float(appreciation_rate - 0.01) # multi-family properties appreciate slower than single family
  rent_appreciation_rate = float(assumptions_get_response.data["rent_appreciation_rate"])
  property_tax_rate = float(assumptions_get_response.data["property_tax_rate"])
  home_insurance_rate = float(assumptions_get_response.data["home_insurance_rate"])
  vacancy_rate = float(assumptions_get_response.data["vacancy_rate"])
  repair_savings_rate = float(assumptions_get_response.data["repair_savings_rate"])
  closing_costs_rate = float(assumptions_get_response.data["closing_costs_rate"])
  live_in_unit_setting = assumptions_get_response.data["live_in_unit_setting"]
  gross_annual_income = assumptions_get_response.data["gross_annual_income"]
  state_tax_code = assumptions_get_response.data["state_tax_code"]
  after_tax_monthly_income = calculate_monthly_take_home(gross_annual_income, state_tax_code)
  discount_rate = assumptions_get_response.data["discount_rate"]
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

def get_deal_score(row):
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
    score += (2 if row["irr_10yr"] >= 0.15 else 1 if row["irr_10yr"] >= 0.12 else 0)  # IRR 10yr
    score += (2 if row["after_tax_cash_flow_y2"] > 600 else 1 if row["after_tax_cash_flow_y2"] > 400 else 0)  # After-tax CF Y2
    score += (2 if row["payback_period_years"] < 7 and row["payback_period_years"] != float('inf') else
              1 if row["payback_period_years"] < 10 and row["payback_period_years"] != float('inf') else 0)  # Payback period
    score += (2 if row["cash_flow_y1_downside_10pct"] > 0 else 1 if row["cash_flow_y1_downside_10pct"] > -200 else 0)  # Y1 downside resilience (heavier weight)
    score += (1 if row["cash_flow_y2_downside_10pct"] > 0 else 0)  # Y2 downside resilience
    score += (2 if row["equity_multiple_10yr"] >= 3 else 1 if row["equity_multiple_10yr"] >= 2 else 0)  # Equity multiple 10yr
    score += (2 if row["roe_y2"] >= 0.20 else 1 if row["roe_y2"] >= 0.15 else 0)  # ROE Y2
    score += (2 if row["leverage_benefit"] >= 0.05 else 1 if row["leverage_benefit"] >= 0.02 else 0)  # Leverage benefit
    score += (1 if row["break_even_occupancy"] < 0.80 else 0)  # Break-even occupancy
    score += (1 if row["net_proceeds_10yr"] > 100000 else 0)  # Net proceeds 10yr
    score += (1 if row["npv_10yr"] > 20000 else 0)  # NPV 10yr (beats market)
    return score

def get_mobility_score(row):
    score = (row["walk_score"] * 0.6) + (row["transit_score"] * 0.30) + (row["bike_score"] * 0.10)
    return score

def get_rentability_score(row) -> float:
    score = 0.0

    # determine factors that make something more or less rentable
    # in-unit laundry, shared basement or not, renovated units, proximity to certain locations
    # then make a score out of it

    return score

def get_seller_motivation_score(row) -> str:
    """
    Calculate seller motivation score based on multiple factors.
    Returns: 'low', 'medium', or 'high'
    """
    listed_date = row.get('listed_date')
    if listed_date and pd.notna(listed_date):
        if isinstance(listed_date, str):
            listed_datetime = datetime.fromisoformat(listed_date.replace('Z', '+00:00').split('T')[0])
        else:
            listed_datetime = pd.to_datetime(listed_date)
        days_on_market = (datetime.now() - listed_datetime).days
    else:
        days_on_market = 0  # Default to 0 if no listing date available
    
    property_condition: str = row['property_condition']
    price_reductions: bool = row['has_reduced_price']
    seller_circumstances: str = row.get('seller_circumstance')
    score = 0
    
    if days_on_market > 30 and days_on_market < 60:
        score += 1
    elif days_on_market < 90:
        score += 2
    else: 
        score += 3
    
    if price_reductions:
        score += 2
    
    high_motivation_circumstances = ['estate_sale', 'financial_distress', 'divorce', 'relocation', 'inherited']
    medium_motivation_circumstances = ['downsizing', 'upgrading', 'portfolio_liquidation']
    
    if seller_circumstances in high_motivation_circumstances:
        score += 3
    elif seller_circumstances in medium_motivation_circumstances:
        score += 2

    if property_condition == "medium":
        score += 1
    elif property_condition == "low":
        score += 2
    
    if score <= 3:
        return 'low'
    elif score <= 7:
        return 'medium'
    else:
        return 'high'

def get_expected_gains(row, length_years):
    current_home_value = row["purchase_price"]
    loan_amount = row["loan_amount"]
    y1_cashflow = row["annual_cash_flow_y1"]
    y2_cashflow = row["annual_cash_flow_y2"]

    # Year 1 is the base year (no appreciation applied)
    cumulative_cashflow = y1_cashflow
    for year in range(2, length_years + 1):
        # Year 2 starts with base y2_cashflow, then compounds
        yearly_cashflow = y2_cashflow * ((1 + rent_appreciation_rate) ** (year - 2))
        cumulative_cashflow += yearly_cashflow

    rate = appreciation_rate if row["units"] == 0 else mf_appreciation_rate
    appreciation_gains = current_home_value * ((1 + rate) ** length_years - 1)
    monthly_rate = apr_rate / 12
    num_payments = loan_length_years * 12
    total_payments_in_period = length_years * 12
    remaining_balance = loan_amount * (
        ((1 + monthly_rate) ** num_payments - (1 + monthly_rate) ** total_payments_in_period) /
        ((1 + monthly_rate) ** num_payments - 1)
    )
    equity_gains = loan_amount - remaining_balance
    return cumulative_cashflow + appreciation_gains + equity_gains

def get_monthly_taxes(row):
    annual_tax = row.get('annual_tax_amount')
    if pd.notna(annual_tax) and annual_tax is not None:
        return (annual_tax * 1.05) / 12 # add a small buffer of 5% to be conservative
    return (row["purchase_price"] * property_tax_rate) / 12

def get_state_tax_rate(state_code):
    """Get state marginal tax rate from state code"""
    state_rates = {
        'IA': 0.0482,  # Iowa 4.82%
        'IL': 0.0495,  # Illinois 4.95%
    }
    return state_rates.get(state_code, 0.05)  # Default to 5% if state not found

def calculate_payback_period(row):
    """Calculate payback period accounting for Year 1 losses"""
    if row["annual_cash_flow_y1"] < 0:
        # Year 1 we lose money, need to recover initial investment + Year 1 losses
        total_to_recover = row["cash_needed"] + abs(row["annual_cash_flow_y1"])
    else:
        # Year 1 profitable, deduct from recovery needed
        total_to_recover = row["cash_needed"] - row["annual_cash_flow_y1"]

    if row["annual_cash_flow_y2"] <= 0:
        return float('inf')  # Never pays back

    # +1 for Year 1 already passed
    payback_years = 1 + (total_to_recover / row["annual_cash_flow_y2"])
    return payback_years

def calculate_net_proceeds(row, years, selling_costs_rate=0.07, capital_gains_rate=0.15):
    """Calculate net proceeds from sale after N years"""
    # Future property value (single family vs multi-family appreciation rates)
    rate = appreciation_rate if row["units"] == 0 else mf_appreciation_rate
    future_value = row["purchase_price"] * ((1 + rate) ** years)

    # Remaining loan balance
    loan_amount = row["loan_amount"]
    monthly_rate = apr_rate / 12
    num_payments = loan_length_years * 12
    total_payments_in_period = years * 12
    remaining_balance = loan_amount * (
        ((1 + monthly_rate) ** num_payments - (1 + monthly_rate) ** total_payments_in_period) /
        ((1 + monthly_rate) ** num_payments - 1)
    )

    # Selling costs (agent commission + closing costs)
    selling_costs = future_value * selling_costs_rate

    # Capital gains tax (only on appreciation)
    capital_gain = future_value - row["purchase_price"]
    capital_gains_tax = capital_gain * capital_gains_rate if capital_gain > 0 else 0

    # Net proceeds = Future value - Loan payoff - Selling costs - Taxes
    net_proceeds = future_value - remaining_balance - selling_costs - capital_gains_tax

    return net_proceeds

def calculate_irr(row, years):
    """Calculate Internal Rate of Return over N years"""
    try:
        # Build cash flow array
        cash_flows = [-row["cash_needed"]]  # Year 0: initial investment (outflow)

        # Year 1 cash flow
        cash_flows.append(row["annual_cash_flow_y1"])

        # Years 2 through N: compounded with rent appreciation
        for year in range(2, years + 1):
            yearly_cashflow = row["annual_cash_flow_y2"] * ((1 + rent_appreciation_rate) ** (year - 2))
            cash_flows.append(yearly_cashflow)

        # Final year: add net proceeds from sale
        net_proceeds = calculate_net_proceeds(row, years)
        cash_flows[-1] += net_proceeds

        # Calculate IRR
        irr = npf.irr(cash_flows)
        return irr if not math.isnan(irr) else 0
    except Exception:
        return 0  # Return 0 if calculation fails

def calculate_npv(row, years):
    """Calculate Net Present Value over N years using discount_rate"""
    try:
        # Build cash flow array (same as IRR)
        cash_flows = [-row["cash_needed"]]  # Year 0: initial investment (outflow)

        # Year 1 cash flow
        cash_flows.append(row["annual_cash_flow_y1"])

        # Years 2 through N: compounded with rent appreciation
        for year in range(2, years + 1):
            yearly_cashflow = row["annual_cash_flow_y2"] * ((1 + rent_appreciation_rate) ** (year - 2))
            cash_flows.append(yearly_cashflow)

        # Final year: add net proceeds from sale
        net_proceeds = calculate_net_proceeds(row, years)
        cash_flows[-1] += net_proceeds

        # Calculate NPV: discount each cash flow back to present
        npv = 0
        for year, cash_flow in enumerate(cash_flows):
            npv += cash_flow / ((1 + discount_rate) ** year)

        return npv
    except Exception:
        return 0  # Return 0 if calculation fails

def calculate_roe(row):
    """Calculate Return on Equity for Year 2"""
    # Equity after Year 1 = down payment + principal paid in Year 1
    loan_amount = row["loan_amount"]
    monthly_rate = apr_rate / 12
    num_payments = loan_length_years * 12

    # Remaining balance after 1 year (12 payments)
    remaining_balance_y1 = loan_amount * (
        ((1 + monthly_rate) ** num_payments - (1 + monthly_rate) ** 12) /
        ((1 + monthly_rate) ** num_payments - 1)
    )

    # Principal paid in Year 1
    principal_paid_y1 = loan_amount - remaining_balance_y1

    # Current equity = down payment + principal paid
    current_equity = row["down_payment"] + principal_paid_y1

    # ROE = Annual cash flow Y2 / Current equity
    if current_equity > 0:
        return row["annual_cash_flow_y2"] / current_equity
    return 0

def apply_calculations_on_dataframe(df):
    state_rate = get_state_tax_rate(state_tax_code)
    combined_tax_rate = FEDERAL_TAX_RATE + state_rate
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
    df["monthly_taxes"] = df.apply(get_monthly_taxes, axis=1)
    df["monthly_insurance"] = (df["purchase_price"] * home_insurance_rate) / 12
    df["cash_needed"] = df["closing_costs"] + df["down_payment"]
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
    df["ltv_ratio"] = df["loan_amount"] / df["purchase_price"] # Loan-to-Value ratio
    df["price_per_door"] = df.apply(
        lambda row: row["purchase_price"] / row["beds"] if row["units"] == 0 else row["purchase_price"] / row["units"],
        axis=1
    ) # Price per unit/door (or per bedroom for single family)
    df["rent_per_sqft"] = df["total_rent"] / df["square_ft"] # Monthly rent per square foot
    df["break_even_occupancy"] = df["total_monthly_cost"] / df["total_rent"] # Break-even occupancy rate
    df["break_even_vacancy"] = 1.0 - df["break_even_occupancy"]
    df["oer"] = df["operating_expenses"] / df["total_rent"] # Operating Expense Ratio (standard industry metric)
    df["egi"] = df["total_rent"] - df["monthly_vacancy_costs"] # Effective Gross Income
    df["debt_yield"] = df["annual_NOI_y2"] / df["loan_amount"] # Debt Yield (lender metric)
    df["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5,))
    df["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10,))
    df["20y_forecast"] = df.apply(get_expected_gains, axis=1, args=(20,))
    df["mobility_score"] = df.apply(get_mobility_score, axis=1)
    df["piti"] = df['monthly_mortgage'] + df['monthly_mip'] + df['monthly_taxes'] + df['monthly_insurance']
    df['costs_to_income'] = df["piti"] / after_tax_monthly_income
    df["monthly_depreciation"] = (df["purchase_price"] * (1 - LAND_VALUE_PCT)) / DEPRECIATION_YEARS / 12
    df["tax_savings_monthly"] = df["monthly_depreciation"] * combined_tax_rate
    df["after_tax_cash_flow_y1"] = df["monthly_cash_flow_y1"] + df["tax_savings_monthly"]
    df["after_tax_cash_flow_y2"] = df["monthly_cash_flow_y2"] + df["tax_savings_monthly"]
    df["future_value_5yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (appreciation_rate if row["units"] == 0 else mf_appreciation_rate)) ** 5),
        axis=1
    )
    df["future_value_10yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (appreciation_rate if row["units"] == 0 else mf_appreciation_rate)) ** 10),
        axis=1
    )
    df["future_value_20yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (appreciation_rate if row["units"] == 0 else mf_appreciation_rate)) ** 20),
        axis=1
    )
    df["net_proceeds_5yr"] = df.apply(calculate_net_proceeds, axis=1, args=(5, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE))
    df["net_proceeds_10yr"] = df.apply(calculate_net_proceeds, axis=1, args=(10, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE))
    df["net_proceeds_20yr"] = df.apply(calculate_net_proceeds, axis=1, args=(20, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE))
    df["equity_multiple_5yr"] = (df["5y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    df["equity_multiple_10yr"] = (df["10y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    df["equity_multiple_20yr"] = (df["20y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    df["avg_annual_return_5yr"] = ((df["5y_forecast"] / df["cash_needed"]) / 5) * 100
    df["avg_annual_return_10yr"] = ((df["10y_forecast"] / df["cash_needed"]) / 10) * 100
    df["avg_annual_return_20yr"] = ((df["20y_forecast"] / df["cash_needed"]) / 20) * 100
    df["roe_y2"] = df.apply(calculate_roe, axis=1)
    df["leverage_benefit"] = df["CoC_y2"] - (df["annual_NOI_y2"] / df["purchase_price"])
    df["payback_period_years"] = df.apply(calculate_payback_period, axis=1)
    df["irr_5yr"] = df.apply(calculate_irr, axis=1, args=(5,))
    df["irr_10yr"] = df.apply(calculate_irr, axis=1, args=(10,))
    df["irr_20yr"] = df.apply(calculate_irr, axis=1, args=(20,))
    df["npv_5yr"] = df.apply(calculate_npv, axis=1, args=(5,))
    df["npv_10yr"] = df.apply(calculate_npv, axis=1, args=(10,))
    df["npv_20yr"] = df.apply(calculate_npv, axis=1, args=(20,))
    df["fair_value_5yr"] = df["purchase_price"] + df["npv_5yr"]
    df["fair_value_10yr"] = df["purchase_price"] + df["npv_10yr"]
    df["fair_value_20yr"] = df["purchase_price"] + df["npv_20yr"]
    df["value_gap_pct_5yr"] = (df["npv_5yr"] / df["cash_needed"]) * 100
    df["value_gap_pct_10yr"] = (df["npv_10yr"] / df["cash_needed"]) * 100
    df["value_gap_pct_20yr"] = (df["npv_20yr"] / df["cash_needed"]) * 100
    df["beats_market"] = df["npv_10yr"] > 0
    df["cash_flow_y1_downside_10pct"] = (df["net_rent_y1"] * 0.9) - df["total_monthly_cost"]
    df["cash_flow_y2_downside_10pct"] = (df["total_rent"] * 0.9) - df["total_monthly_cost"]
    df["deal_score"] = df.apply(get_deal_score, axis=1)
    df["fha_self_sufficiency_ratio"] = (df["total_rent"] * 0.75) / df["piti"]
    return df

def reload_dataframe():
    global df, rents
    console.print("[yellow]Reloading property data...[/yellow]")
    properties_get_response = supabase.table('properties').select('*').execute()
    df = pd.DataFrame(properties_get_response.data)
    df = df.drop(["zillow_link", "full_address"], axis=1)
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
    df = apply_calculations_on_dataframe(df=df)
    console.print("[green]Property data reloaded successfully![/green]")

load_assumptions()
load_loan(LAST_USED_LOAN)
reload_dataframe()

def display_all_properties(properties_df, title, show_status=False, show_min_rent_data=False):
    dataframe = df if properties_df is None else properties_df
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
    table.add_column("Cost/Inc", justify="right", style="bold white")
    table.add_column("DS", justify="right", style="bold white")  # deal score
    table.add_column("MS", justify="right", style="bold white")  # mobility score
    table.add_column("10Y", justify="right", style="bold white")  # 10 year investment growth
    table.add_column("IRR 10Y", justify="right", style="bold white")  
    table.add_column("NPV10Y", justify="right", style="bold white") # Net present value 10 years

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
            if row["deal_score"] >= 30
            else ("yellow" if row["deal_score"] >= 20 else "red")
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
            f"[{costs_to_income_style}]{format_percentage(row['costs_to_income'])}[/{costs_to_income_style}]",
            f"[{deal_score_style}]{int(row['deal_score'])}/38[/{deal_score_style}]",
            f"[{mobility_score_style}]{int(row['mobility_score'])}[/{mobility_score_style}]",
            f"[{forecast_10y_style}]{format_currency(row['10y_forecast'])}[/{forecast_10y_style}]",
            f"[{irr_10yr_style}]{format_percentage(row['irr_10yr'])}[/{irr_10yr_style}]",
            f"[{npv_style}]{format_currency(row["npv_10yr"])}[/{npv_style}]"
        ]

        if show_status:
            row_args.append(row["status"])
        
        if show_min_rent_data:
            row_args.append(str(row["min_rent_unit_beds"]))
            row_args.append(str(int(row["min_rent_unit_beds"] - 1)))
            row_args.append(str(calculate_additional_room_rent(row)))
            
        table.add_row(*row_args)

    console.print(table)

def calculate_quintile_colors_for_metrics(dataframe):
    """
    Calculate quintile-based colors for all metrics across ALL properties.
    Uses 3-color scheme: Green (top 40%), Yellow (middle 20%), Red (bottom 40%).

    Returns a dictionary mapping (address, metric_name) -> color_string
    """
    import numpy as np

    # Define which metrics should be colored with "lower is better" logic
    lower_is_better = {
        'price_per_door',
        'break_even_occupancy',
        'oer',
        'payback_period_years'
    }

    # Metric column name to actual dataframe column mapping
    metric_columns = {
        'price_per_door': 'price_per_door',
        'rent_per_sqft': 'rent_per_sqft',
        'break_even_occupancy': 'break_even_occupancy',
        'break_even_vacancy': 'break_even_vacancy',
        'oer': 'oer',
        'egi': 'egi',
        'debt_yield': 'debt_yield',
        'monthly_depreciation': 'monthly_depreciation',
        'tax_savings_monthly': 'tax_savings_monthly',
        'after_tax_cash_flow_y1': 'after_tax_cash_flow_y1',
        'after_tax_cash_flow_y2': 'after_tax_cash_flow_y2',
        'future_value_10yr': 'future_value_10yr',
        'net_proceeds_10yr': 'net_proceeds_10yr',
        'equity_multiple_10yr': 'equity_multiple_10yr',
        'avg_annual_return_10yr': 'avg_annual_return_10yr',
        'roe_y2': 'roe_y2',
        'leverage_benefit': 'leverage_benefit',
        'payback_period_years': 'payback_period_years',
        'irr_10yr': 'irr_10yr',
        'npv_10yr': 'npv_10yr',
        'cash_flow_y2_downside_10pct': 'cash_flow_y2_downside_10pct'
    }

    color_map = {}

    for metric_name, col_name in metric_columns.items():
        if col_name not in dataframe.columns:
            continue

        # Filter out special values (inf, -inf, NaN)
        valid_mask = ~(dataframe[col_name].isna() |
                      np.isinf(dataframe[col_name]))
        valid_data = dataframe[valid_mask][col_name]

        if len(valid_data) == 0:
            # No valid data, skip this metric
            continue

        # Calculate 40th and 60th percentiles
        p40 = np.percentile(valid_data, 40)
        p60 = np.percentile(valid_data, 60)

        # Assign colors to each property for this metric
        for idx, row in dataframe.iterrows():
            address = row['address1']
            value = row[col_name]

            # Handle special values with gray color
            if pd.isna(value) or np.isinf(value):
                color = 'dim white'
            else:
                # Determine color based on quintile and direction
                if metric_name in lower_is_better:
                    # Lower is better: green for low values, red for high
                    if value <= p40:
                        color = 'green'
                    elif value <= p60:
                        color = 'yellow'
                    else:
                        color = 'red'
                else:
                    # Higher is better: green for high values, red for low
                    if value >= p60:
                        color = 'green'
                    elif value >= p40:
                        color = 'yellow'
                    else:
                        color = 'red'

            color_map[(address, metric_name)] = color

    return color_map

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
    Current criteria:
      - status = 'active'
      - 1% rule (monthly gross rent must be 1% or more of purchase price)
      - 50% rule (operating expenses must be 50% or lower than gross rent)
      - Cash needed must be below $25,000
      - Debt Service Coverage Ratio should be above 1.25
      - Monthly Cashflow with cheapest unit not rented above -400 (house hacking)
      - Fully rented monthly cashflow above 400
      - Triplexes / Duplexes must pass FHA self-sufficiency test (Gross Rent * 0.75 >= PITI)
    """
    status_criteria = "status == 'active'" if active else "status != 'active'"
    criteria = f"{status_criteria} & MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & cash_needed <= 25000 & monthly_cash_flow_y1 >= -400 & monthly_cash_flow_y2 >= 400 & fha_self_sufficiency_ratio >= 1"

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

def get_combined_phase1_qualifiers(active=True):
    current_df, reduced_df, creative_df = get_all_phase1_qualifying_properties(active=active)
    combined = pd.concat(
        [current_df, reduced_df, creative_df], ignore_index=True
    ).drop_duplicates(subset=["address1"], keep="first") 
    return combined

def get_all_phase2_properties():
    """
    This method filters phase 1 qualifiers based property condition, rentability, and affordability 
    Current criteria:
      - property must qualify for phase 1
      - property must not have any 'deal breakers'
      - fixed monthly costs to after tax income ratio must be greater than 0.45
    """
    p1_df = get_combined_phase1_qualifiers()

    # STEP 1 - REMOVE PROPERTIES THAT AREN'T DATA COMPLETE
    checklist = get_phase2_data_checklist()

    complete_address1s = [
        address for address, checks in checklist.items()
        if all(checks.values())
    ]

    completed_df = p1_df[p1_df['address1'].isin(complete_address1s)].copy()
    incompleted_df = p1_df[~p1_df['address1'].isin(complete_address1s)].copy()

    # STEP 2 - RUN ALL NEW EVALUATIONS AND MODIFY DATAFRAME
    qualifying_df = [] 
    disqualifying_df = [] 

    if not completed_df.empty:
        completed_df['property_condition'] = completed_df.apply(lambda row: inspections.get_property_condition(row), axis=1) # TODO - finish this
        completed_df['has_inspection_dealbreakers'] = completed_df.apply(lambda row: inspections.has_dealbreakers(row), axis=1) # TODO - finish this
        completed_df['seller_motivation_score'] = completed_df.apply(lambda row: get_seller_motivation_score(row), axis=1)  # TODO - finish this
        completed_df['rentability_score'] = completed_df.apply(lambda row: get_rentability_score(row), axis=1)  # TODO - finish this
        completed_df['total_diy_repair_costs'] = completed_df.apply(lambda row: inspections.get_total_diy_repair_costs(row), axis=1)  # TODO - finish this
        completed_df['total_pro_repair_costs'] = completed_df.apply(lambda row: inspections.get_total_pro_repair_costs(row), axis=1)  # TODO - finish this
        completed_df['est_diy_repair_costs'] = completed_df.apply(lambda row: inspections.get_est_diy_repair_costs(row), axis=1)  # TODO - finish this
        completed_df['est_pro_repair_costs'] = completed_df.apply(lambda row: inspections.get_est_pro_repair_costs(row), axis=1)  # TODO - finish this
        # is_selling_at_loss (using last purchase data)
        # depreciation_rate_per_year (using last purchase data)
        # how long has current owner owned (last purchase date - today), longer = more equity = more price flexibility
        # ^ can be used in seller motivation score

        # STEP 3 - CREATE CRITERIA AND QUERY
        qualifying_criteria = "has_inspection_dealbreakers == False & costs_to_income <= 0.45" # todo add more here
        disqualifying_criteria = "has_inspection_dealbreaks == True | costs_to_income >= 0.45" # todo add more here
        qualifying_df = completed_df.query(qualifying_criteria)
        disqualifying_df = completed_df.query(disqualifying_criteria)

    # STEP 4 - CREATE A DF-RELATIVE RANKING AMONGST QUALIFIERS
    # maybe pandas has ranking methods?

    return {
        "qualifiers": qualifying_df,
        "disqualifiers": disqualifying_df,
        "incomplete_data": incompleted_df if not incompleted_df.empty else [],
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
    df2["deal_score"] = df2.apply(get_deal_score, axis=1)
    return df2

def get_reduced_pp_df(reduction_factor):
    dataframe = df.copy()
    dataframe["original_price"] = dataframe["purchase_price"]
    dataframe["purchase_price"] = dataframe["purchase_price"] * (1 - reduction_factor) # new purchase price
    dataframe = apply_calculations_on_dataframe(df=dataframe)
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
                      f"Address: {row['address1']}\n"
                      f"Purchase Price: {format_currency(row['purchase_price'])}\n"
                      f"Bedrooms: {int(row['beds'])} | Bathrooms: {int(row['baths'])} | Sq Ft: {format_number(row['square_ft'])}\n"
                      f"Built: {int(row['built_in'])} (Age: {int(row['home_age'])} years)\n"
                      f"{property_type_display}\n"
                      f"Cost per Sq Ft: {format_currency(row['cost_per_sqrft'])}",
                      title="Basic Info"))
    
    property_rents = rents[rents['address1'] == property_id]
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
                      f"Monthly Operating Expenses: {format_currency(row['operating_expenses'])} ({format_currency(row['operating_expenses'] * 12)} annually)\n\n"
                      f"[bold green]Net Operating Income (NOI):[/bold green]\n"
                      f"NOI Year 1 (Live-in): {format_currency(row['net_rent_y1'] - row['operating_expenses'])} ({format_currency(row['annual_NOI_y1'])} annually)\n"
                      f"NOI Year 2 (All Rent): {format_currency(row['monthly_NOI'])} ({format_currency(row['annual_NOI_y2'])} annually)\n\n"
                      f"[bold cyan]Personal Income & Housing Costs:[/bold cyan]\n"
                      f"After-Tax Monthly Income: {format_currency(after_tax_monthly_income)}\n"
                      f"Housing Cost to Income Ratio: {format_percentage(row['costs_to_income'])}",
                      title="Income Breakdown"))
    
    table.add_row("Monthly Cash Flow", 
                  f"[{'red' if row['monthly_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y1'])}[/]",
                  f"[{'red' if row['monthly_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y2'])}[/]")
    table.add_row("Annual Cash Flow",
                  f"[{'red' if row['annual_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y1'])}[/]",
                  f"[{'red' if row['annual_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y2'])}[/]")
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
    table.add_row("Annual Rent",
                  format_currency(row['annual_rent_y1']),
                  format_currency(row['annual_rent_y2']))
    mgr_pp_style = "green" if row['MGR_PP'] >= 0.01 else "red"
    opex_rent_style = "green" if 0.45 <= row['OpEx_Rent'] <= 0.55 else ("yellow" if 0.35 <= row['OpEx_Rent'] <= 0.65 else "red")
    dscr_style = "green" if row['DSCR'] >= 1.25 else "red"
    fha_style = "green" if row["fha_self_sufficiency_ratio"] >= 1 else "red"
    table.add_row("1% Rule (MGR/PP)","",f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]")
    table.add_row("50% Rule (OpEx/Rent)","",f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]")
    table.add_row("DSCR (Rent/Mortgage)","",f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]")
    table.add_row("FHA Self Sufficiency Ratio","",f"[{fha_style}]{format_percentage(row["fha_self_sufficiency_ratio"])}[/{fha_style}]")
    table.add_row("LTV Ratio","",format_percentage(row['ltv_ratio']))
    table.add_row("Price Per Door","",format_currency(row['price_per_door']))
    table.add_row("Rent Per Sqft","",format_currency(row['rent_per_sqft']))
    table.add_row("Break-Even Occupancy","",format_percentage(row['break_even_occupancy']))
    table.add_row("Break-Even Vacancy","",express_percent_as_months_and_days(row["break_even_vacancy"]))
    table.add_row("Operating Expense Ratio","",format_percentage(row['oer']))
    table.add_row("Effective Gross Income","",format_currency(row['egi']))
    table.add_row("Debt Yield","",format_percentage(row['debt_yield']))
    table.add_row("Monthly Depreciation Deduction","",format_currency(row['monthly_depreciation']))
    table.add_row("Monthly Tax Savings","",format_currency(row['tax_savings_monthly']))
    
    table.add_row("Return on Equity (ROE) Y2","",format_percentage(row['roe_y2']))
    table.add_row("Leverage Benefit","",format_percentage(row['leverage_benefit']))
    payback_display = f"{row['payback_period_years']:.1f} years" if row['payback_period_years'] != float('inf') else "Never"
    table.add_row("Payback Period","",payback_display)
    downside_y1_style = "green" if row['cash_flow_y1_downside_10pct'] > 0 else "red"
    downside_y2_style = "green" if row['cash_flow_y2_downside_10pct'] > 0 else "red"
    table.add_row("Cash Flow (10% Rent Drop)",
                  f"[{downside_y1_style}]{format_currency(row['cash_flow_y1_downside_10pct'])}[/{downside_y1_style}]",
                  f"[{downside_y2_style}]{format_currency(row['cash_flow_y2_downside_10pct'])}[/{downside_y2_style}]")
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

    # New scoring metrics
    irr_score = (2 if row["irr_10yr"] >= 0.15 else 1 if row["irr_10yr"] >= 0.12 else 0)
    at_cf_score = (2 if row["after_tax_cash_flow_y2"] > 600 else 1 if row["after_tax_cash_flow_y2"] > 400 else 0)
    payback_score = (2 if row["payback_period_years"] < 7 and row["payback_period_years"] != float('inf') else
                     1 if row["payback_period_years"] < 10 and row["payback_period_years"] != float('inf') else 0)
    downside_y1_score = (2 if row["cash_flow_y1_downside_10pct"] > 0 else 1 if row["cash_flow_y1_downside_10pct"] > -200 else 0)
    downside_y2_score = (1 if row["cash_flow_y2_downside_10pct"] > 0 else 0)
    equity_mult_score = (2 if row["equity_multiple_10yr"] >= 3 else 1 if row["equity_multiple_10yr"] >= 2 else 0)
    roe_score = (2 if row["roe_y2"] >= 0.20 else 1 if row["roe_y2"] >= 0.15 else 0)
    leverage_score = (2 if row["leverage_benefit"] >= 0.05 else 1 if row["leverage_benefit"] >= 0.02 else 0)
    breakeven_score = (1 if row["break_even_occupancy"] < 0.80 else 0)
    proceeds_score = (1 if row["net_proceeds_10yr"] > 100000 else 0)
    npv_score = (1 if row["npv_10yr"] > 20000 else 0)

    deal_score_style = ("green" if row['deal_score'] >= 20 else "yellow" if row['deal_score'] >= 15 else "red")
    
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
    criteria_table.add_row("IRR (10yr)", f"[white]{irr_score}[/white]", "2", f"{row['irr_10yr']:.1%}")
    criteria_table.add_row("After-Tax CF Y2", f"[white]{at_cf_score}[/white]", "2", f"${row['after_tax_cash_flow_y2']:.0f}/month")
    payback_display = f"{row['payback_period_years']:.1f} yrs" if row['payback_period_years'] != float('inf') else "Never"
    criteria_table.add_row("Payback Period", f"[white]{payback_score}[/white]", "2", payback_display)
    criteria_table.add_row("Y1 Rent Drop Resilience (10%)", f"[white]{downside_y1_score}[/white]", "2", f"${row['cash_flow_y1_downside_10pct']:.0f}/month")
    criteria_table.add_row("Y2 Rent Drop Resilience (10%)", f"[white]{downside_y2_score}[/white]", "1", f"${row['cash_flow_y2_downside_10pct']:.0f}/month")
    criteria_table.add_row("Equity Multiple (10yr)", f"[white]{equity_mult_score}[/white]", "2", f"{row['equity_multiple_10yr']:.2f}x")
    criteria_table.add_row("Return on Equity Y2", f"[white]{roe_score}[/white]", "2", f"{row['roe_y2']:.1%}")
    criteria_table.add_row("Leverage Benefit", f"[white]{leverage_score}[/white]", "2", f"{row['leverage_benefit']:.1%}")
    criteria_table.add_row("Break-Even Occupancy", f"[white]{breakeven_score}[/white]", "1", f"{row['break_even_occupancy']:.1%}")
    criteria_table.add_row("Net Proceeds (10yr)", f"[white]{proceeds_score}[/white]", "1", f"${row['net_proceeds_10yr']:,.0f}")
    criteria_table.add_row("NPV (10yr)", f"[white]{npv_score}[/white]", "1", f"${row['npv_10yr']:,.0f}")
    criteria_table.add_row("[bold]TOTAL SCORE[/bold]", f"[bold {deal_score_style}]{int(row['deal_score'])}[/bold {deal_score_style}]", "[bold]38[/bold]",
                          f"[bold {deal_score_style}]{'Excellent' if row['deal_score'] >= 20 else 'Good' if row['deal_score'] >= 15 else 'Poor'}[/bold {deal_score_style}]")
    
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
    cost_table.add_row("Electricity (est.)", format_currency(row['annual_electricity_cost_est'] / 12), format_currency(row['annual_electricity_cost_est']))
    
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
            "Export property analysis to PDF",
            "Skip - return to main menu"
        ]
    ).ask()
    
    if research_choice == "Generate new rent research (AI-powered)":
        handle_rent_research_generation(property_id)
    elif research_choice == "View existing research reports":
        handle_view_research_reports(property_id)
    elif research_choice == "Generate rent estimates from report":
        handle_generate_rent_estimates(property_id)
    elif research_choice == "Export property analysis to PDF":
        downloads_folder = os.getenv("DOWNLOADS_FOLDER", ".")
        safe_address = property_id.replace(' ', '_').replace(',', '').replace('.', '')
        output_path = os.path.join(downloads_folder, f"{safe_address}_analysis.pdf")

        row = df[df['address1'] == property_id].iloc[0]

        # Prepare loan info dict
        loan_info = {
            'interest_rate': interest_rate,
            'apr_rate': apr_rate,
            'down_payment_rate': down_payment_rate,
            'years': loan_length_years,
            'mip_upfront_rate': mip_upfront_rate,
            'mip_annual_rate': mip_annual_rate,
        }

        # Prepare assumptions dict
        assumptions = {
            'appreciation_rate': appreciation_rate,
            'rent_appreciation_rate': rent_appreciation_rate,
            'property_tax_rate': property_tax_rate,
            'home_insurance_rate': home_insurance_rate,
            'vacancy_rate': vacancy_rate,
            'repair_savings_rate': repair_savings_rate,
            'closing_costs_rate': closing_costs_rate,
            'discount_rate': discount_rate,
        }

        result_path = export_property_analysis(row, rents, after_tax_monthly_income, loan_info, assumptions, output_path)
        console.print(f"[green]PDF exported successfully to: {result_path}[/green]")

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

def is_property_assessment_done(row) -> bool:
    bool_fields = [
        'obtained_county_records', 'has_short_ownership_pattern',
        'has_deed_restrictions', 'has_hao', 'has_historic_preservation',
        'has_easements', 'in_flood_zone', 'has_open_pulled_permits',
        'has_work_done_wo_permits'
    ]

    other_fields = [
        'previous_owner_count', 'last_purchase_price', 'last_purchase_date'
    ]

    text_fields = [
        'setbacks', 'easements', 'county_record_notes',
        'permit_notes', 'whitepages_notes'
    ]

    for field in bool_fields + other_fields:
        value = row.get(field)
        if value is None or pd.isna(value):
            return False

    for field in text_fields:
        value = row.get(field)
        if value is None or pd.isna(value) or value == '':
            return False

    return True

def get_phase2_data_checklist():
    """Gets all phase 1 properties and their data checklist"""
    combined_df = get_combined_phase1_qualifiers()
    checklist = {}

    for _, row in combined_df.iterrows():
        checklist[row["address1"]] = {
            "has_listing": row["listed_date"] is not None,
            "has_inspection_done": inspections.is_property_inspection_done(
                row["address1"]
            ),
            "has_maps_data": is_property_maps_done(row),
            "has_rent_dd": row["rent_dd_completed"] if row["rent_dd_completed"] is not None else False,
            "has_neighborhood_assessment": neighborhoods.is_neighborhood_assessment_complete(row["address1"]),
            "has_taxes": row["annual_tax_amount"] is not None,
            "has_seller_circumstances": row["seller_circumstances"] is not None,
            "has_property_assessment": is_property_assessment_done(row),
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

  LAST_USED_LOAN = selected_loan_id
  load_loan(LAST_USED_LOAN)
  reload_dataframe()

using_application = True

def run_all_properties_options():
    using_all_properties = True
    choices = [
        "Phase 1 - Qualifiers",
        "Phase 2 - Qualifiers",
        "All properties - Active (FHA)",
        "All properties - Reduce price and recalculate",
        "All properties - Property Info",
        "All properties - Creative Pricing",
        "All properties - Investment Metrics",
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
        elif option == "All properties - Investment Metrics":
            display_property_metrics()
        elif option == "All properties - Sold / Passed (FHA)":
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
      load_assumptions()
      load_loan(LAST_USED_LOAN)
      reload_dataframe()
