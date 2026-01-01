import os
import pandas as pd
import numpy as np
import questionary
from dotenv import load_dotenv
from InquirerPy import inquirer
from rich.console import Console
from rich.panel import Panel
from supabase import Client, create_client

from add_property import run_add_property
from exporter import export_property_analysis
from handlers import (
    handle_property_wide_research_generation,
    handle_neighborhood_analysis,
    handle_changing_loan,
    handle_extract_neighborhood_grade,
    handle_rent_research_generation,
    handle_status_change,
    handle_price_change,
    handle_view_research_reports,
    handle_risk_assessment,
    handle_property_summary,
    handle_generate_rent_estimates,
    handle_rent_research_after_add,
    handle_scrape_neighborhood_from_findneighborhoods
)
from display import (
    display_all_phase1_qualifying_properties,
    display_all_phase2_qualifying_properties,
    display_all_properties,
    display_all_properties_info,
    display_all_properties_homestyle_analysis,
    display_homestyle_overview_panel,
    display_new_property_qualification,
    display_phase1_research_list,
    display_phase1_total_rent_differences,
    display_property_metrics,
    display_y2_calculations,
    display_property_overview_panel,
    display_property_rent_estimates_table,
    display_property_investment_metrics_table,
    display_investment_requirements_panel,
    display_loans,
    display_current_context_panel
)
from helpers import (
    calculate_monthly_take_home,
    calculate_mortgage,
    get_expected_gains,
    calculate_payback_period,
    get_state_tax_rate,
    calculate_net_proceeds,
    calculate_irr,
    calculate_additional_room_rent,
    calculate_npv,
    calculate_roe,
    estimate_renovation_cost,
    estimate_arv,
)
from inspections import InspectionsClient
from loans import LoansProvider
from neighborhood_assessment import edit_neighborhood_assessment
from neighborhoods import NeighborhoodsClient
from neighborhood_scraper import NeighborhoodScraper
from property_assessment import edit_property_assessment
from scripts import ScriptsProvider

load_dotenv()

console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections = InspectionsClient(supabase_client=supabase)
neighborhoods = NeighborhoodsClient(supabase_client=supabase, console=console)
scraper = NeighborhoodScraper(supabase_client=supabase, console=console)

LAST_USED_LOAN = 2
LAND_VALUE_PCT = 0.20  # 20% of purchase price is land (non-depreciable)
FEDERAL_TAX_RATE = 0.22  # 22% federal tax bracket
SELLING_COSTS_RATE = 0.07  # 7% selling costs (6% agent commission + 1% closing)
CAPITAL_GAINS_RATE = 0.15  # 15% long-term capital gains tax
DEPRECIATION_YEARS = 27.5  # Residential property depreciation period
IA_FIRSTHOME_GRANT_AMT = 2500
DEFAULT_PROPERTY_CONDITION_SCORE = 3  # Default to moderate condition (1-5 scale)

def load_assumptions():
    global ASSUMPTIONS 
    console.print("[yellow]Reloading assumptions...[/yellow]")
    assumptions_get_response = supabase.table("assumptions").select("*").eq("id", 1).limit(1).single().execute()
    ASSUMPTIONS = {
        "appreciation_rate": float(assumptions_get_response.data["appreciation_rate"]),
        "mf_appreciation_rate": (float(assumptions_get_response.data["appreciation_rate"]) - 0.01),
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
        "ia_fhb_prog_upfront_option": assumptions_get_response.data["ia_fhb_prog_upfront_option"],
        # Des Moines, IA utility costs (2025)
        # Sources: EnergySage (electric), RealEstates.network (gas/water),
        #          City of Des Moines (trash), RSINC (internet)
        # Last updated: 2025-12-25
        # Valid through: 2025-04 (4-month purchasing timeline)
        "utility_electric_base": 136.00,  # per month (~$137 avg, 13¢/kWh, 1060 kWh/mo)
        "utility_gas_base": 106.40,       # per month annual avg ($155.84 winter, $56.95 summer)
        "utility_water_base": 49.00,      # per month (Iowa average)
        "utility_trash_base": 18.00,      # per month (Des Moines: $17.91 for 96-gal cart)
        "utility_internet_base": 60.00,   # per month (Iowa avg: $59.75) - SFH only
        "utility_baseline_sqft": 1500,    # baseline square footage for scaling electric/gas
        "description": assumptions_get_response.data['description']
    }
    console.print(
        f"[green]Assumption set '{assumptions_get_response.data['description']}' reloaded successfully![/green]"
    )

def load_loan(loan_id):
    global LOAN
    console.print("[yellow]Reloading loan data...[/yellow]")
    loan_provider = LoansProvider(supabase_client=supabase, console=console)
    loan = loan_provider.get_loan_by_id(loan_id)
    LOAN = {
        "name": loan.name,
        "interest_rate": loan.interest_rate,
        "apr_rate": loan.apr_rate,
        "down_payment_rate": loan.down_payment_rate,
        "loan_length_years": loan.years,
        "mip_upfront_rate": loan.mip_upfront_rate,
        "mip_annual_rate": loan.mip_annual_rate,
        "upfront_discounts": loan.upfront_discounts,
        "loan_type": loan.loan_type
    }
    console.print(f"[green]Loan {loan.name} data reloaded successfully![/green]")

def safe_concat_columns(df, new_columns_dict):
    """
    Add new columns to dataframe, replacing any existing columns with same names.
    Prevents duplicate column creation when pd.concat is used.
    """
    # Identify columns that already exist and need to be dropped
    columns_to_add = list(new_columns_dict.keys())
    existing_columns = [col for col in columns_to_add if col in df.columns]

    # Drop existing columns to prevent duplicates
    if existing_columns:
        df = df.drop(columns=existing_columns)

    # Add all new columns at once (maintains fragmentation fix)
    return pd.concat([df, pd.DataFrame(new_columns_dict, index=df.index)], axis=1)

def apply_closing_costs_calculations(df):
    totals = {}
    lender_costs = {}
    # TODO - eventually replace with fees attached to the loans table in Supabase
    lender_costs["loan_origination_fee"] = df["loan_amount"] * 0.01 # 0.5 - 1% of loan
    lender_costs["credit_reporting_fee"] = 50
    lender_costs["appraisal_fee"] = 370
    lender_costs["flood_certification_fee"] = 20
    lender_costs["tax_service_fee"] = 75
    lender_costs["processing_fee"]= 500
    lender_costs["underwriting_fee"] = 600
    df = safe_concat_columns(df, lender_costs)

    totals["total_lender_costs"] = (
        df["loan_origination_fee"] + df["credit_reporting_fee"] + df["appraisal_fee"] +
        df["flood_certification_fee"] + df["tax_service_fee"] + df["processing_fee"] + df["underwriting_fee"]
    )

    title_costs = {} # Title and Escrow
    title_costs["abstract_update_fee"] = 250  # Iowa-specific: updating the abstract
    title_costs["title_examination_fee"] = 350  # Attorney reviews abstract and issues title opinion
    title_costs["title_guaranty_certificate"] = 175 # flat 175 unless purchase price is above $750k
    title_costs["owners_title_insurance"] = 0 # free with lender's certificate in Iowa
    title_costs["settlement_fee"] = 300
    title_costs["attorney_fee"] = 500# additional attorney buffer on top of title exam fee

    df = safe_concat_columns(df, title_costs)

    totals["total_title_costs"] = (
        df["abstract_update_fee"] + df["title_guaranty_certificate"] + df["title_guaranty_certificate"] + 
        df["owners_title_insurance"] + df["settlement_fee"] + df["attorney_fee"]
    )

    government_costs = {}
    government_costs["deed_recording_fee"] = 27
    government_costs["mortgage_recording_fee"] = 22
    # $1.60 per $1000 of purchase price, but first $500 of purchase price is exempt
    government_costs["polk_county_transfer_tax"] = ((df["purchase_price"] - 500) / 1000) * 1.6
    government_costs["polk_county_transfer_fee"] = 5
    df = safe_concat_columns(df, government_costs)

    totals["total_government_costs"] = (
      df["deed_recording_fee"] + df["mortgage_recording_fee"] + df["polk_county_transfer_tax"] + 
      df["polk_county_transfer_fee"]
    )

    prepaid_costs = {}
    prepaid_costs["prepaid_home_insurance"] = df["monthly_insurance"] * 12
    # This is settled with seller - may be credit or debit depending on timing
    prepaid_costs["property_tax_proration"] = df["monthly_taxes"] * 4 # 2-6 months, typicaly 2-3 months
    # assuming a closing date on the 1st of a month (it may not be, but better to be conservative)
    prepaid_costs["prepaid_interest"] = df["loan_amount"] * ((LOAN["apr_rate"] / 365) * 30)
    df = safe_concat_columns(df, prepaid_costs)

    totals["total_prepaid_costs"] = df["prepaid_home_insurance"] + df["property_tax_proration"] + df["prepaid_interest"]

    escrow_costs = {} # reserves held by lender and NOT a prepayment like prepaid_costs
    escrow_costs["insurance_reserve"] = df["monthly_insurance"] * 3 # typically 3 months
    escrow_costs["tax_reserve"] = df["monthly_taxes"] * 3 # typically 2-6 months
    df = safe_concat_columns(df, escrow_costs)

    totals["total_escrow_costs"] = df["insurance_reserve"] + df["tax_reserve"]

    optional_costs = {}
    optional_costs["home_inspection_fee"] = 400
    optional_costs["property_survey_fee"] = 600
    optional_costs["pest_inspection_fee"] = 100
    optional_costs["courier_fees"] = 35
    optional_costs["notary_fees"] = 25
    df = safe_concat_columns(df, optional_costs)

    totals["total_optional_costs"] = (
      df["home_inspection_fee"] + df["property_survey_fee"] + df["pest_inspection_fee"] + 
      df["courier_fees"] + df["notary_fees"]
    )

    df = safe_concat_columns(df, totals)

    df["closing_costs"] = (
        df["total_lender_costs"] + df["total_title_costs"] + df["total_government_costs"] + 
        df["total_prepaid_costs"] + df["total_escrow_costs"] + df["total_optional_costs"]
    )
    df["closing_costs_prcnt"] = df["closing_costs"] / df["purchase_price"]

    return df

def apply_calculations_on_dataframe(df):
    cols = ["walk_score", "transit_score", "bike_score"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    df[cols] = df[cols].fillna(0)

    basic_columns = {}
    basic_columns["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"]
    basic_columns["home_age"] = 2025 - df["built_in"].fillna(2025)
    basic_columns["down_payment"] = df["purchase_price"] * LOAN["down_payment_rate"]
    basic_columns["5_pct_loan"] = df["purchase_price"] * 0.05
    upfront_mip = 0 if LOAN["loan_type"] == "FHA" else (df["purchase_price"] * LOAN['mip_upfront_rate']) # upfront PMI only on FHA loans
    basic_columns["loan_amount"] = df["purchase_price"] - basic_columns["down_payment"] + upfront_mip
    basic_columns["monthly_mortgage"] = basic_columns["loan_amount"].apply(lambda x: calculate_mortgage(x, LOAN["apr_rate"], LOAN["loan_length_years"]))
    basic_columns["monthly_mip"] = (basic_columns["loan_amount"] * LOAN["mip_annual_rate"]) / 12
    basic_columns["monthly_taxes"] = (df["purchase_price"] * ASSUMPTIONS["property_tax_rate"]) / 12
    basic_columns["monthly_insurance"] = (df["purchase_price"] * ASSUMPTIONS["home_insurance_rate"]) / 12
    df = safe_concat_columns(df, basic_columns)
    df = apply_closing_costs_calculations(df)

    new_columns = {}
    new_columns["cash_needed"] = df["closing_costs"] + df["down_payment"] - LOAN["upfront_discounts"]
    # Vectorized rent estimate calculation (replaces slow .apply() with lambda)
    factor = np.where(df['units'] == 0, 0.0075, 0.0105)
    new_columns["quick_monthly_rent_estimate"] = (
        df['purchase_price'] * (1 + ASSUMPTIONS['closing_costs_rate'])
    ) * factor
    new_columns["ammoritization_estimate"] = df["monthly_mortgage"] - (df["loan_amount"] * LOAN["apr_rate"] / 12)
    new_columns["total_rent"] = new_columns['quick_monthly_rent_estimate']
    new_columns["annual_rent"] = new_columns["total_rent"] * 12
    new_columns["monthly_vacancy_costs"] = new_columns["total_rent"] * ASSUMPTIONS['vacancy_rate']
    new_columns["monthly_repair_costs"] = new_columns["total_rent"] * ASSUMPTIONS['repair_savings_rate']
    new_columns["operating_expenses"] = (
        new_columns["monthly_vacancy_costs"] + new_columns["monthly_repair_costs"] +
        df["monthly_taxes"] + df["monthly_insurance"]
    )
    # For electric/gas: use owner's unit sqft (not total building sqft)
    # For SFH: owner_unit_sqft = total sqft
    # For multi-family: owner_unit_sqft = actual unit sqft from rent_estimates
    sqft_scaling_owner_unit = df["owner_unit_sqft"] / ASSUMPTIONS['utility_baseline_sqft']
    units_for_calcs = df["units"].apply(lambda x: max(1, x if pd.notna(x) and x > 0 else 1))
    new_columns["monthly_utility_electric"] = ASSUMPTIONS['utility_electric_base'] * sqft_scaling_owner_unit
    new_columns["monthly_utility_gas"] = ASSUMPTIONS['utility_gas_base'] * sqft_scaling_owner_unit
    # Water: Tenants pay their own water bills directly (owner pays $0)
    new_columns["monthly_utility_water"] = df.apply(lambda row: 0 if row['units'] > 0 else ASSUMPTIONS['utility_water_base'], axis=1)
    new_columns["monthly_utility_trash"] = ASSUMPTIONS['utility_trash_base'] * units_for_calcs
    # Internet: SFH pays for house-hacking connection; MF tenants pay their own
    new_columns["monthly_utility_internet"] = df.apply(lambda row: ASSUMPTIONS['utility_internet_base'] if row['units'] == 0 else 0, axis=1)
    new_columns["monthly_utility_total"] = (
        new_columns["monthly_utility_electric"] + new_columns["monthly_utility_gas"] + new_columns["monthly_utility_water"] +
        new_columns["monthly_utility_trash"] + new_columns["monthly_utility_internet"]
    )

    # Calculate roommate utility contributions (what roommates pay)
    # Vectorized calculation - replaces slow .iterrows() loop
    beds_safe = df['beds'].fillna(3).clip(lower=1)
    utility_total = new_columns["monthly_utility_total"]

    # SFH house hack: utility_total * (beds - 1) / beds
    # Multi-family: 0 (owner pays full unit)
    roommate_utilities_sfh = utility_total * (beds_safe - 1) / beds_safe
    new_columns["roommate_utilities"] = np.where(
        df['units'] == 0,
        roommate_utilities_sfh,
        0
    )
    new_columns["owner_utilities"] = new_columns["monthly_utility_total"] - new_columns["roommate_utilities"]
    new_columns["total_monthly_cost"] = (
        df["monthly_mortgage"] + new_columns["operating_expenses"] + new_columns["monthly_utility_total"] + 
        (df["monthly_mip"] if LOAN["down_payment_rate"] < 0.2 else 0)
    )
    new_columns["monthly_cash_flow"] = new_columns["total_rent"] - new_columns["total_monthly_cost"] + new_columns['ammoritization_estimate'] + new_columns["roommate_utilities"]
    new_columns["annual_cash_flow"] = new_columns["monthly_cash_flow"] * 12
    df = safe_concat_columns(df, new_columns)
    return df

def apply_investment_calculations(df):
    state_rate = get_state_tax_rate(ASSUMPTIONS['state_tax_code'])
    combined_tax_rate = FEDERAL_TAX_RATE + state_rate

    # Vectorized rent base calculations (replaces 3 redundant .apply() calls)
    # Calculate condition once and reuse for all three columns
    is_sfh_with_estimate = (
        (df['units'] == 0) &
        df['rent_estimate'].notna() &
        (df['rent_estimate'] > 0)
    )

    rent_base_columns = {}
    rent_base_columns["y1_opex_rent_base"] = np.where(
        is_sfh_with_estimate,
        df['rent_estimate'],
        df['market_total_rent_estimate']
    )
    rent_base_columns["y2_rent_base"] = rent_base_columns["y1_opex_rent_base"]
    rent_base_columns["y2_rent_base_source"] = np.where(
        is_sfh_with_estimate,
        "whole_property",
        "room_sum"
    )

    df = safe_concat_columns(df, rent_base_columns)

    def calculate_roommate_utilities_y1(row):
        """Calculate what roommates pay in Year 1 (live-in)"""
        beds_safe = row['beds'] if pd.notna(row['beds']) and row['beds'] > 0 else 3
        if row['units'] == 0:  # SFH house hack
            return row['monthly_utility_total'] * (beds_safe - 1) / beds_safe
        else:  # Multi-family
            return 0  # Owner pays full unit

    roommate_utilities_y1 = df.apply(calculate_roommate_utilities_y1, axis=1)
    roommate_utilities_y2 = df['monthly_utility_total']  # Year 2: tenants pay all
    owner_utilities_y1 = df['monthly_utility_total'] - roommate_utilities_y1
    owner_utilities_y2 = df['monthly_utility_total'] - roommate_utilities_y2  # = 0

    new_columns_stage1 = {}
    new_columns_stage1["mr_monthly_vacancy_costs"] = df["y1_opex_rent_base"] * ASSUMPTIONS['vacancy_rate']
    new_columns_stage1["mr_monthly_repair_costs"] = df["y1_opex_rent_base"] * ASSUMPTIONS['repair_savings_rate']
    new_columns_stage1["mr_operating_expenses"] = new_columns_stage1['mr_monthly_vacancy_costs'] + new_columns_stage1['mr_monthly_repair_costs'] + df['monthly_taxes'] + df['monthly_insurance']
    new_columns_stage1["mr_total_monthly_cost"] = df['monthly_mortgage'] + df['monthly_mip'] + new_columns_stage1['mr_operating_expenses'] + df['monthly_utility_total']

    # Add trash to tenant rents for multi-family
    # Y1: (units - 1) tenant units × $18/month
    # Y2: all units × $18/month
    trash_adjustment_y1 = df.apply(
        lambda row: (row['units'] - 1) * 18 if row['units'] > 0 else 0,
        axis=1
    )
    trash_adjustment_y2 = df.apply(
        lambda row: row['units'] * 18 if row['units'] > 0 else 0,
        axis=1
    )

    # Y1 and Y2 net rents with trash adjustments
    new_columns_stage1["mr_net_rent_y1"] = df['market_total_rent_estimate'] - df['min_rent'] + trash_adjustment_y1
    new_columns_stage1["mr_net_rent_y2"] = df["y2_rent_base"] + trash_adjustment_y2
    new_columns_stage1["mr_annual_rent_y1"] = new_columns_stage1["mr_net_rent_y1"] * 12
    new_columns_stage1["mr_annual_rent_y2"] = new_columns_stage1["mr_net_rent_y2"] * 12
    new_columns_stage1["mr_monthly_NOI_y1"] = new_columns_stage1["mr_net_rent_y1"] - new_columns_stage1["mr_operating_expenses"]
    new_columns_stage1["mr_monthly_NOI_y2"] = new_columns_stage1["mr_net_rent_y2"] - new_columns_stage1["mr_operating_expenses"]
    new_columns_stage1["mr_annual_NOI_y1"] = new_columns_stage1["mr_monthly_NOI_y1"] * 12
    new_columns_stage1["mr_annual_NOI_y2"] = new_columns_stage1["mr_monthly_NOI_y2"] * 12
    new_columns_stage1["mr_monthly_cash_flow_y1"] = new_columns_stage1["mr_net_rent_y1"] - new_columns_stage1["mr_total_monthly_cost"] + roommate_utilities_y1
    new_columns_stage1["mr_monthly_cash_flow_y2"] = new_columns_stage1["mr_net_rent_y2"] - new_columns_stage1["mr_total_monthly_cost"] + roommate_utilities_y2
    new_columns_stage1["mr_annual_cash_flow_y1"] = new_columns_stage1["mr_monthly_cash_flow_y1"] * 12
    new_columns_stage1["mr_annual_cash_flow_y2"] = new_columns_stage1["mr_monthly_cash_flow_y2"] * 12
    new_columns_stage1["roommate_utilities_y1"] = roommate_utilities_y1
    new_columns_stage1["roommate_utilities_y2"] = roommate_utilities_y2
    new_columns_stage1["owner_utilities_y1"] = owner_utilities_y1
    new_columns_stage1["owner_utilities_y2"] = owner_utilities_y2
    df = safe_concat_columns(df, new_columns_stage1)

    new_columns_stage2 = {}
    new_columns_stage2["cap_rate_y1"] = df["mr_annual_NOI_y1"] / df["purchase_price"]
    new_columns_stage2["cap_rate_y2"] = df["mr_annual_NOI_y2"] / df["purchase_price"]
    new_columns_stage2["CoC_y1"] = df["mr_annual_cash_flow_y1"] / df["cash_needed"]
    new_columns_stage2["CoC_y2"] = df["mr_annual_cash_flow_y2"] / df["cash_needed"]
    new_columns_stage2["GRM_y1"] = df["purchase_price"] / df["mr_annual_rent_y1"] # Gross Rent Multiplier (lower = better)
    new_columns_stage2["GRM_y2"] = df["purchase_price"] / df["mr_annual_rent_y2"]
    new_columns_stage2["MGR_PP"] = df["y2_rent_base"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
    new_columns_stage2["OpEx_Rent"] = df["mr_operating_expenses"] / df["y2_rent_base"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
    new_columns_stage2["DSCR"] = df["y2_rent_base"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25
    new_columns_stage2["ltv_ratio"] = df["loan_amount"] / df["purchase_price"] # Loan-to-Value ratio
    new_columns_stage2["price_per_door"] = df.apply(
        lambda row: row["purchase_price"] / row["beds"] if row["units"] == 0 else row["purchase_price"] / row["units"],
        axis=1
    ) # Price per unit/door (or per bedroom for single family)
    new_columns_stage2["rent_per_sqft"] = df["y2_rent_base"] / df["square_ft"] # Monthly rent per square foot (Y2 for SFH)
    new_columns_stage2["break_even_occupancy"] = df["mr_total_monthly_cost"] / df["y2_rent_base"] # Break-even occupancy rate
    new_columns_stage2["break_even_vacancy"] = 1.0 - new_columns_stage2["break_even_occupancy"]
    new_columns_stage2["oer"] = df["mr_operating_expenses"] / df["y2_rent_base"] # Operating Expense Ratio (standard industry metric)
    new_columns_stage2["egi"] = df["y2_rent_base"] - df["mr_monthly_vacancy_costs"] # Effective Gross Income
    new_columns_stage2["debt_yield"] = df["mr_annual_NOI_y2"] / df["loan_amount"] # Debt Yield (lender metric)
    new_columns_stage2["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5,ASSUMPTIONS,LOAN,))
    new_columns_stage2["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10,ASSUMPTIONS,LOAN,))
    new_columns_stage2["20y_forecast"] = df.apply(get_expected_gains, axis=1, args=(20,ASSUMPTIONS,LOAN,))
    new_columns_stage2["mobility_score"] = (df["walk_score"] * 0.6) + (df["transit_score"] * 0.30) + (df["bike_score"] * 0.10)
    new_columns_stage2["piti"] = df['monthly_mortgage'] + df['monthly_mip'] + df['monthly_taxes'] + df['monthly_insurance']
    new_columns_stage2['costs_to_income'] = new_columns_stage2["piti"] / ASSUMPTIONS['after_tax_monthly_income']
    new_columns_stage2["monthly_depreciation"] = (df["purchase_price"] * (1 - LAND_VALUE_PCT)) / DEPRECIATION_YEARS / 12
    new_columns_stage2["tax_savings_monthly"] = new_columns_stage2["monthly_depreciation"] * combined_tax_rate
    new_columns_stage2["after_tax_cash_flow_y1"] = df["mr_monthly_cash_flow_y1"] + new_columns_stage2["tax_savings_monthly"]
    new_columns_stage2["after_tax_cash_flow_y2"] = df["mr_monthly_cash_flow_y2"] + new_columns_stage2["tax_savings_monthly"]
    new_columns_stage2["future_value_5yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (ASSUMPTIONS['appreciation_rate'] if row["units"] == 0 else ASSUMPTIONS['mf_appreciation_rate'])) ** 5),
        axis=1
    )
    new_columns_stage2["future_value_10yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (ASSUMPTIONS['appreciation_rate'] if row["units"] == 0 else ASSUMPTIONS['mf_appreciation_rate'])) ** 10),
        axis=1
    )
    new_columns_stage2["future_value_20yr"] = df.apply(
        lambda row: row["purchase_price"] * ((1 + (ASSUMPTIONS['appreciation_rate'] if row["units"] == 0 else ASSUMPTIONS['mf_appreciation_rate'])) ** 20),
        axis=1
    )
    new_columns_stage2["net_proceeds_5yr"] = df.apply(calculate_net_proceeds, axis=1, args=(5, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE, ASSUMPTIONS, LOAN))
    new_columns_stage2["net_proceeds_10yr"] = df.apply(calculate_net_proceeds, axis=1, args=(10, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE, ASSUMPTIONS, LOAN))
    new_columns_stage2["net_proceeds_20yr"] = df.apply(calculate_net_proceeds, axis=1, args=(20, SELLING_COSTS_RATE, CAPITAL_GAINS_RATE, ASSUMPTIONS, LOAN))
    new_columns_stage2["equity_multiple_5yr"] = (new_columns_stage2["5y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    new_columns_stage2["equity_multiple_10yr"] = (new_columns_stage2["10y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    new_columns_stage2["equity_multiple_20yr"] = (new_columns_stage2["20y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    new_columns_stage2["avg_annual_return_5yr"] = ((new_columns_stage2["5y_forecast"] / df["cash_needed"]) / 5) * 100
    new_columns_stage2["avg_annual_return_10yr"] = ((new_columns_stage2["10y_forecast"] / df["cash_needed"]) / 10) * 100
    new_columns_stage2["avg_annual_return_20yr"] = ((new_columns_stage2["20y_forecast"] / df["cash_needed"]) / 20) * 100
    new_columns_stage2["roe_y2"] = df.apply(calculate_roe, axis=1, args=[LOAN,])
    new_columns_stage2["leverage_benefit"] = new_columns_stage2["CoC_y2"] - (df["mr_annual_NOI_y2"] / df["purchase_price"])
    new_columns_stage2["payback_period_years"] = df.apply(
        lambda row: calculate_payback_period(row, ASSUMPTIONS, LOAN), axis=1
    )
    new_columns_stage2["irr_5yr"] = df.apply(calculate_irr, axis=1, args=(5,ASSUMPTIONS,LOAN))
    new_columns_stage2["irr_10yr"] = df.apply(calculate_irr, axis=1, args=(10,ASSUMPTIONS,LOAN))
    new_columns_stage2["irr_20yr"] = df.apply(calculate_irr, axis=1, args=(20,ASSUMPTIONS,LOAN))
    new_columns_stage2["npv_5yr"] = df.apply(calculate_npv, axis=1, args=(5,ASSUMPTIONS,LOAN))
    new_columns_stage2["npv_10yr"] = df.apply(calculate_npv, axis=1, args=(10,ASSUMPTIONS,LOAN))
    new_columns_stage2["npv_20yr"] = df.apply(calculate_npv, axis=1, args=(20,ASSUMPTIONS,LOAN))
    new_columns_stage2["fair_value_5yr"] = df["purchase_price"] + new_columns_stage2["npv_5yr"]
    new_columns_stage2["fair_value_10yr"] = df["purchase_price"] + new_columns_stage2["npv_10yr"]
    new_columns_stage2["fair_value_20yr"] = df["purchase_price"] + new_columns_stage2["npv_20yr"]
    new_columns_stage2["value_gap_pct_5yr"] = (new_columns_stage2["npv_5yr"] / df["cash_needed"]) * 100
    new_columns_stage2["value_gap_pct_10yr"] = (new_columns_stage2["npv_10yr"] / df["cash_needed"]) * 100
    new_columns_stage2["value_gap_pct_20yr"] = (new_columns_stage2["npv_20yr"] / df["cash_needed"]) * 100
    new_columns_stage2["beats_market"] = new_columns_stage2["npv_10yr"] > 0
    new_columns_stage2["cash_flow_y1_downside_10pct"] = (df["mr_net_rent_y1"] * 0.9) - df["mr_total_monthly_cost"]
    new_columns_stage2["cash_flow_y2_downside_10pct"] = (df["y2_rent_base"] * 0.9) - df["mr_total_monthly_cost"]
    new_columns_stage2["fha_self_sufficiency_ratio"] = (df["y2_rent_base"] * 0.75) / new_columns_stage2["piti"]  # Uses Y2 rent (whole-property for SFH)

    df = safe_concat_columns(df, new_columns_stage2)
    return df

def apply_homestyle_calculations(df):
    df['property_condition_score'] = df['property_condition_score'].fillna(DEFAULT_PROPERTY_CONDITION_SCORE)

    new_columns_stage1 = {}
    new_columns_stage1["hs_renovation_cost"] = df.apply(estimate_renovation_cost, axis=1)
    new_columns_stage1["hs_arv"] = df.apply(lambda row: estimate_arv(row, new_columns_stage1["hs_renovation_cost"].loc[row.name]), axis=1)
    new_columns_stage1["hs_total_project_cost"] = df["purchase_price"] + new_columns_stage1["hs_renovation_cost"]
    df = safe_concat_columns(df, new_columns_stage1)

    new_columns_stage2 = {}
    new_columns_stage2["hs_ltv_limit"] = 0.97  # 97% LTV for FHA primary residence
    new_columns_stage2["hs_max_loan_arv_basis"] = df["hs_arv"] * 0.97
    new_columns_stage2["hs_max_loan_cost_basis"] = df["hs_total_project_cost"] * 0.97
    new_columns_stage2["hs_max_loan_amount"] = np.minimum(new_columns_stage2["hs_max_loan_arv_basis"], new_columns_stage2["hs_max_loan_cost_basis"])
    new_columns_stage2["hs_max_renovation_financing"] = np.minimum(df["hs_renovation_cost"], np.maximum(0, new_columns_stage2["hs_max_loan_amount"] - df["purchase_price"]))
    new_columns_stage2["hs_down_payment"] = df["hs_total_project_cost"] * 0.03
    new_columns_stage2["hs_out_of_pocket_renovation"] = np.maximum(0, df["hs_renovation_cost"] - new_columns_stage2["hs_max_renovation_financing"])
    new_columns_stage2["hs_cash_needed"] = new_columns_stage2["hs_down_payment"] + new_columns_stage2["hs_out_of_pocket_renovation"]
    new_columns_stage2["hs_borrowing_gap"] = np.maximum(0, df["hs_total_project_cost"] - new_columns_stage2["hs_max_loan_amount"])
    new_columns_stage2["hs_ltv_ratio"] = np.where(df["hs_arv"] > 0, new_columns_stage2["hs_max_loan_amount"] / df["hs_arv"], 0)
    new_columns_stage2["hs_built_in_equity"] = df["hs_arv"] - df["hs_total_project_cost"]
    new_columns_stage2["hs_equity_pct"] = np.where(df["hs_arv"] > 0, new_columns_stage2["hs_built_in_equity"] / df["hs_arv"], 0)
    new_columns_stage2["hs_cost_per_sqft"] = np.where(df["square_ft"] > 0, df["hs_total_project_cost"] / df["square_ft"], 0)
    new_columns_stage2["hs_arv_per_sqft"] = np.where(df["square_ft"] > 0, df["hs_arv"] / df["square_ft"], 0)
    new_columns_stage2["hs_renovation_value_add"] = df["hs_arv"] - df["purchase_price"]
    new_columns_stage2["hs_renovation_roi"] = np.where(df["hs_renovation_cost"] > 0, new_columns_stage2["hs_renovation_value_add"] / df["hs_renovation_cost"], 0)
    new_columns_stage2["hs_all_in_basis"] = new_columns_stage2["hs_cash_needed"] + new_columns_stage2["hs_max_loan_amount"]

    # Feasibility check: Is max loan sufficient to cover purchase + most renovations?
    # TRUE = feasible (renovation financing covers at least 75% of renovation cost)
    new_columns_stage2["hs_is_feasible"] = np.where(
        df["hs_renovation_cost"] > 0,
        new_columns_stage2["hs_max_renovation_financing"] >= (df["hs_renovation_cost"] * 0.75),
        True
    )

    # Deal quality score (higher = better deal)
    # Combines equity built-in, renovation ROI, and feasibility
    new_columns_stage2["hs_deal_score"] = (
        (new_columns_stage2["hs_equity_pct"] * 0.4) +  # 40% weight on equity
        (np.minimum(new_columns_stage2["hs_renovation_roi"], 2.0) * 0.4) +  # 40% weight on ROI (cap at 2.0)
        np.where(new_columns_stage2["hs_is_feasible"], 0.2, 0)  # 20% weight on feasibility
    ) * 100  # Scale to 0-100

    df = safe_concat_columns(df, new_columns_stage2)
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
    df = df.merge(rent_summary, on="address1", how="left")

    # Get owner's unit sqft from rent_estimates (min_rent_unit is the unit owner lives in)
    owner_unit_sqft = rents.loc[
        rents.groupby("address1")["rent_estimate"].idxmin(),
        ["address1", "estimated_sqrft"]
    ].rename(columns={"estimated_sqrft": "owner_unit_sqft"})

    # Merge owner unit sqft into main dataframe
    df = df.merge(owner_unit_sqft, on="address1", how="left")

    # Fill missing owner_unit_sqft: use total_sqft/units for multi-family, total_sqft for SFH
    df["owner_unit_sqft"] = df.apply(
        lambda row: (
            row["owner_unit_sqft"]
            if pd.notna(row["owner_unit_sqft"]) and row["owner_unit_sqft"] > 0
            else (row["square_ft"] / row["units"] if row["units"] > 0 else row["square_ft"])
        ),
        axis=1
    )

    neighborhoods_df = neighborhoods.get_neighborhoods_dataframe(supabase)
    df = df.merge(neighborhoods_df, on="address1", how="left")
    df = apply_calculations_on_dataframe(df=df)
    df = apply_investment_calculations(df=df)
    df = apply_homestyle_calculations(df=df)
    console.print("[green]Property data reloaded successfully![/green]")

def get_global_dataframe():
    return df

load_assumptions()
load_loan(LAST_USED_LOAN)
reload_dataframe()

PHASE0_CRITERIA = "square_ft >= 1000 & cash_needed <= 25000 & monthly_cash_flow >= -600"
PHASE1_CRITERIA = (
    "MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & beats_market "
    "& mr_monthly_cash_flow_y1 >= -400 "
    "& ((units == 0 & mr_monthly_cash_flow_y2 >= 0) | (units > 0 & mr_monthly_cash_flow_y2 >= 200))"
)
PHASE1_TOUR_CRITERIA = "((neighborhood_letter_grade in ['A','B','C'] & qualification_type == 'current') | is_fsbo) & status == 'active'"


def get_all_phase0_qualifying_properties():
    """
    This method filters all properties based on our criteria for financial viability using quick rent estimates:
      - status = 'active'
      - Cash needed must be below $25,000
      - SFH/MF: Monthly total cashflow is above -200
      - Square Feet must be greater than or equal to 1000
    """
    return df.copy().query(PHASE0_CRITERIA).copy()

def get_phase0_qualifiers_lacking_research():
    """
    This method finds all Phase 0 qualifying properties that lack market research required for future phases.
    """
    phase0_df = get_all_phase0_qualifying_properties()
    return phase0_df.query("has_market_research == False")

def get_all_phase1_qualifying_properties():
    """
    This method filters all properties based on our criteria for financial viability using market rent estimates
      - 1% rule (monthly gross rent must be 1% or more of purchase price)
      - 50% rule (operating expenses must be 50% or lower than gross rent)
      - Debt Service Coverage Ratio should be above 1.25
      - Net Present Value in 10 years must be positive, thus beating the stock market
      - SFH/MF: Market Rent Monthly Cashflow Y1 must be above -400
      - SFH: Market Rent Monthly Cashflow Y2 must be above -50
      - MF: Market Rent Monthly Cashflow Y2 must be above 400
    """
    base_df = get_all_phase0_qualifying_properties()
    filtered_df = base_df.query(PHASE1_CRITERIA).copy()
    filtered_df["qualification_type"] = "current"
    qualifier_address1s = filtered_df["address1"].tolist()
    reduced_df = get_reduced_pp_df(0.10)
    reduced_df = reduced_df.query(PHASE0_CRITERIA).query(PHASE1_CRITERIA).copy()
    reduced_df["qualification_type"] = "contingent"
    reduced_df = reduced_df[~reduced_df["address1"].isin(qualifier_address1s)].copy()
    creative_df = get_additional_room_rental_df()
    creative_df = creative_df.query(PHASE0_CRITERIA).query(PHASE1_CRITERIA).copy()
    creative_df["qualification_type"] = "creative"
    return filtered_df, reduced_df, creative_df 

def get_combined_phase1_qualifiers():
    current_df, reduced_df, creative_df = get_all_phase1_qualifying_properties()
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
    combined = get_combined_phase1_qualifiers()
    qualified_df = combined.query(PHASE1_TOUR_CRITERIA).copy()
    qualified_addresses = qualified_df['address1'].tolist()
    unqualified_df = combined[~combined['address1'].isin(qualified_addresses)].copy()
    return qualified_df, unqualified_df

def get_all_phase2_qualifiers():
    """
    This method filters phase 1 qualifiers based property condition, rentability, and affordability 
    Current criteria:
      - property must qualify for phase 1 research list
      - property must not have any 'dealbreakers'
      - fixed monthly costs to after tax income ratio must be greater than 0.45
      - Neighborhood Letter Grade must be C or higher
    """
    p1_df = get_combined_phase1_qualifiers()

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

def get_additional_room_rental_df():
    dataframe = df.copy()
    df2 = dataframe.query('min_rent_unit_beds > 1').copy()
    df2["additional_room_rent"] = df2.apply(calculate_additional_room_rent, axis=1)
    df2["total_rent"] = df2["total_rent"] + df2["additional_room_rent"]
    df2["monthly_cash_flow"] = df2["total_rent"] - df2["total_monthly_cost"]
    df2["annual_cash_flow"] = df2["monthly_cash_flow"] * 12
    df2["mr_annual_NOI_y1"] = (df2["mr_net_rent_y1"] - df2["mr_operating_expenses"]) * 12
    df2["mr_cap_rate_y1"] = df2["mr_annual_NOI_y1"] / df2["purchase_price"]
    df2["mr_CoC_y1"] = df2["mr_annual_cash_flow_y1"] / df2["cash_needed"]
    df2["mr_GRM_y1"] = df2["purchase_price"] / df2["mr_annual_rent_y1"]
    return df2

def get_reduced_pp_df(reduction_factor):
    dataframe = df.copy()
    dataframe["original_price"] = dataframe["purchase_price"]
    dataframe["purchase_price"] = dataframe["purchase_price"] * (1 - reduction_factor) # new purchase price
    dataframe = apply_calculations_on_dataframe(df=dataframe)
    dataframe = apply_investment_calculations(df=dataframe)
    return dataframe

def analyze_property(property_id):
    """Display detailed analysis for a single property"""
    row = df[df['address1'] == property_id].iloc[0]
    property_rents = rents[rents['address1'] == property_id]
    is_single_family = int(row['units']) == 0

    if property_rents.empty:
        console.print("[red]ERROR: No rent estimates found for this property![/red]")
        console.print("[yellow]This property may need rent estimates to be generated.[/yellow]")
        return

    display_property_overview_panel(console, row)
    display_property_rent_estimates_table(console, property_rents, is_single_family)
    display_property_investment_metrics_table(console, row, is_single_family)
    display_investment_requirements_panel(console, row, ASSUMPTIONS, LOAN, IA_FIRSTHOME_GRANT_AMT)

    research_menu_choices = [
        "Edit property assessment",
        "View risk assessment report",
        "View property summary",
        "Edit neighborhood assessment",
        "Record price change",
        "Change status",
        "Generate new rent research",
        "View existing research reports",
        "Generate rent estimates from report",
    ]

    if is_single_family:
        research_menu_choices.append("Generate property-wide rent research")

    research_menu_choices.extend([
        "Scrape neighborhood from FindNeighborhoods.dsm.city",
        "Run neighborhood analysis",
        "Extract neighborhood letter grade",
        "View HomeStyle renovation analysis",
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
        handle_risk_assessment(property_id, supabase, console)
    elif research_choice == "View property summary":
        handle_property_summary(property_id, supabase, console, df)
    elif research_choice == "Edit neighborhood assessment":
        edit_neighborhood_assessment(property_id, supabase, console)
    elif research_choice == "Generate new rent research":
        handle_rent_research_generation(property_id, supabase, console, handle_generate_rent_estimates)
    elif research_choice == "View existing research reports":
        handle_view_research_reports(property_id, supabase, console)
    elif research_choice == "Generate rent estimates from report":
        handle_generate_rent_estimates(property_id, supabase, console)
        reload_dataframe()
    elif research_choice == "Generate property-wide rent research":
        handle_property_wide_research_generation(property_id, supabase, console)
        reload_dataframe()
        console.print("\n[bold green]✅ Property-wide rent estimates successfully extracted and saved![/bold green]")
    elif research_choice == "Scrape neighborhood from FindNeighborhoods.dsm.city":
        handle_scrape_neighborhood_from_findneighborhoods(property_id, supabase, console, scraper, ask_user=True)
        reload_dataframe()
    elif research_choice == "Run neighborhood analysis":
        handle_neighborhood_analysis(property_id, console, neighborhoods)
        reload_dataframe()
    elif research_choice == "Extract neighborhood letter grade":
        handle_extract_neighborhood_grade(property_id, supabase, console, neighborhoods)
        reload_dataframe()
    elif research_choice == "View HomeStyle renovation analysis":
        display_homestyle_overview_panel(console, row)
    elif research_choice == "Record price change":
        handle_price_change(property_id, row["purchase_price"], supabase)
        reload_dataframe()
        display_new_property_qualification(console, property_id, get_all_phase1_qualifying_properties)
    elif research_choice == "Change status":
        handle_status_change(property_id, supabase)
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

using_application = True

def run_all_properties_options():
    using_all_properties = True
    choices = [
        "Phase 0 - Qualifiers",
        "Phase 1 - Qualifiers",
        "Phase 1 - Total Rent Differences",
        "Phase 1.5 - Research List",
        "Phase 1.5 - HomeStyle Analysis for Research List",
        "Phase 2 - Qualifiers",
        "All properties - Active",
        "All properties - Y2 Calculations",
        "All properties - Property Info",
        "All properties - Investment Metrics",
        "All properties - HomeStyle Analysis",
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
            display_all_properties(properties_df=dataframe, df=df, title="All active properties using FHA", show_prop_type=True, console=console)
        elif option == "Phase 0 - Qualifiers":
            phase0_df = get_all_phase0_qualifying_properties()
            display_all_properties(properties_df=phase0_df, df=df, title="Phase 0 Qualifiers", show_prop_type=True, console=console, show_has_mr=True)
        elif option == "Phase 1 - Qualifiers":
            current, contingent, creative = get_all_phase1_qualifying_properties()
            phase0_df = get_phase0_qualifiers_lacking_research()
            display_all_phase1_qualifying_properties(console, df, current, contingent, creative, phase0_df)
        elif option == "Phase 1.5 - Research List":
            qualified_df, unqualified_df = get_phase1_research_list()
            display_phase1_research_list(console, qualified_df, unqualified_df)
        elif option == "Phase 1.5 - HomeStyle Analysis for Research List":
            qualified_df, unqualified_df = get_phase1_research_list()
            display_all_properties_homestyle_analysis(console, df, qualified_df)
            display_all_properties_homestyle_analysis(console, df, unqualified_df)
        elif option == "Phase 1 - Total Rent Differences":
            display_phase1_total_rent_differences(console, get_combined_phase1_qualifiers)
        elif option == "All properties - Y2 Calculations":
            display_y2_calculations(console, df)
        elif option == "All properties - Property Info":
            display_all_properties_info(console, df, properties_df=df)
        elif option == "All properties - Investment Metrics":
            display_property_metrics(console, df, get_combined_phase1_qualifiers)
        elif option == "All properties - HomeStyle Analysis":
            display_all_properties_homestyle_analysis(console, df)
        elif option == "All properties - Sold / Passed":
            dataframe = df.query("status != 'active'")
            display_all_properties(
                properties_df=dataframe,
                df=df,
                title="All inactive properties",
                show_status=True,
                console=console,
            )
        elif option == "Phase 2 - Qualifiers":
            display_all_phase2_qualifying_properties(console, df, get_all_phase2_qualifiers)

def run_scripts_options():
  using_scripts = True
  choices = ["Go back", "Add property valuations to all Phase 1.5 qualifiers"]
  scripts = ScriptsProvider(supabase_client=supabase, console=console)

  while using_scripts:
    option = questionary.select("Select a script", choices=choices).ask()
    if option == "Go back":
      using_scripts = False
    elif option == "Add property valuations to all Phase 1 properties":
      qualified_df, _ = get_phase1_research_list() 
      scripts.run_add_property_values_script(properties_df=qualified_df)
      reload_dataframe()

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
      loans = loans_provider.get_loans()
      display_loans(console=console, loans=loans)
    elif option == "Change loans for session":
      selected_loan_id = handle_changing_loan(supabase, console)
      LAST_USED_LOAN = selected_loan_id
      load_loan(LAST_USED_LOAN)
      reload_dataframe()

if __name__ == "__main__":
  while using_application:
    choices = ['All properties', 'One property', 'One property - phase 1 research list', "Add new property", "Scripts", "Loans", "Refresh data", "Quit"]
    option = questionary.select("What would you like to analyze?", choices=choices).ask()

    display_current_context_panel(console, LOAN["name"], ASSUMPTIONS["description"])

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
      property_details, passes_phase0 = run_add_property(
          supabase_client=supabase,
          reload_df_callback=reload_dataframe,
          get_all_phase0_qualifying_properties=get_all_phase0_qualifying_properties,
          get_reduced_pp_df=get_reduced_pp_df,
          phase0_criteria=PHASE0_CRITERIA
      )
      if property_details is None:
        console.print("[red]Property addition failed, skipping post-processing[/red]")
      else:
        handle_scrape_neighborhood_from_findneighborhoods(property_details['address1'], supabase, console, scraper, ask_user=False)

        if passes_phase0:
          handle_rent_research_after_add(property_details['address1'], supabase, console, ask_user=True)
          reload_dataframe()
          display_new_property_qualification(console, property_details['address1'], get_all_phase1_qualifying_properties)
    elif option == "Scripts":
      run_scripts_options()
    elif option == "Loans":
      run_loans_options()
    elif option == "Refresh data":
      load_assumptions()
      load_loan(LAST_USED_LOAN)
      reload_dataframe()
