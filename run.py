import os
import pandas as pd
import questionary
from dotenv import load_dotenv
from InquirerPy import inquirer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
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
    handle_price_cut,
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
    display_new_property_qualification,
    display_phase1_research_list,
    display_phase1_total_rent_differences,
    display_property_metrics,
    display_y2_calculations,
)
from helpers import (
    calculate_monthly_take_home,
    calculate_mortgage,
    express_percent_as_months_and_days,
    format_currency,
    format_number,
    format_percentage,
    get_expected_gains,
    calculate_payback_period,
    get_state_tax_rate,
    calculate_net_proceeds,
    calculate_irr,
    calculate_additional_room_rent,
    calculate_npv,
    calculate_roe
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
    # Convert and clean existing columns
    cols = ["walk_score", "transit_score", "bike_score"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    df[cols] = df[cols].fillna(0)

    # Collect all new columns in a dictionary to add at once
    new_columns = {}
    new_columns["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"]
    new_columns["home_age"] = 2025 - df["built_in"].fillna(2025)
    new_columns["down_payment"] = df["purchase_price"] * LOAN['down_payment_rate']
    new_columns["5_pct_loan"] = df["purchase_price"] * 0.05
    new_columns["loan_amount"] = df["purchase_price"] - new_columns["down_payment"] + (df["purchase_price"] * LOAN['mip_upfront_rate'])
    new_columns["monthly_mortgage"] = new_columns["loan_amount"].apply(lambda x: calculate_mortgage(x, LOAN['apr_rate'], LOAN['loan_length_years']))
    new_columns["monthly_mip"] = (new_columns["loan_amount"] * LOAN['mip_annual_rate']) / 12
    new_columns["monthly_taxes"] = (df["purchase_price"] * ASSUMPTIONS['property_tax_rate']) / 12
    new_columns["monthly_insurance"] = (df["purchase_price"] * ASSUMPTIONS['home_insurance_rate']) / 12
    new_columns["closing_costs"] = df["purchase_price"] * ASSUMPTIONS['closing_costs_rate']
    new_columns["cash_needed"] = new_columns["closing_costs"] + new_columns["down_payment"] - LOAN['upfront_discounts'] - (IA_FIRSTHOME_GRANT_AMT if (ASSUMPTIONS['ia_fhb_prog_upfront_option'] == "GRANT" and ASSUMPTIONS['using_ia_fhb_prog']) else 0)
    new_columns["quick_monthly_rent_estimate"] = (df["purchase_price"] + new_columns["closing_costs"]) * 0.0075
    new_columns['ammoritization_estimate'] = (new_columns['loan_amount'] * 0.017) / 12
    new_columns["total_rent"] = new_columns['quick_monthly_rent_estimate']
    new_columns["annual_rent"] = new_columns["total_rent"] * 12
    new_columns["monthly_vacancy_costs"] = new_columns["total_rent"] * ASSUMPTIONS['vacancy_rate']
    new_columns["monthly_repair_costs"] = new_columns["total_rent"] * ASSUMPTIONS['repair_savings_rate']
    new_columns["operating_expenses"] = new_columns["monthly_vacancy_costs"] + new_columns["monthly_repair_costs"] + new_columns["monthly_taxes"] + new_columns["monthly_insurance"]
    new_columns["total_monthly_cost"] = new_columns["monthly_mortgage"] + new_columns["monthly_mip"] + new_columns["operating_expenses"]
    new_columns["monthly_cash_flow"] = new_columns["total_rent"] - new_columns["total_monthly_cost"] + new_columns['ammoritization_estimate']
    new_columns["annual_cash_flow"] = new_columns["monthly_cash_flow"] * 12

    # Add all columns at once to avoid fragmentation
    df = pd.concat([df, pd.DataFrame(new_columns, index=df.index)], axis=1)
    return df

def apply_investment_calculations(df):
    # Calculate state tax rate once
    state_rate = get_state_tax_rate(ASSUMPTIONS['state_tax_code'])
    combined_tax_rate = FEDERAL_TAX_RATE + state_rate

    # Stage 1: Add basic columns needed by df.apply() functions
    new_columns_stage1 = {}
    new_columns_stage1["mr_monthly_vacancy_costs"] = df["market_total_rent_estimate"] * ASSUMPTIONS['vacancy_rate']
    new_columns_stage1["mr_monthly_repair_costs"] = df["market_total_rent_estimate"] * ASSUMPTIONS['repair_savings_rate']
    new_columns_stage1["mr_operating_expenses"] = new_columns_stage1['mr_monthly_vacancy_costs'] + new_columns_stage1['mr_monthly_repair_costs'] + df['monthly_taxes'] + df['monthly_insurance']
    new_columns_stage1["mr_total_monthly_cost"] = df['monthly_mortgage'] + df['monthly_mip'] + new_columns_stage1['mr_operating_expenses']
    new_columns_stage1["mr_net_rent_y1"] = df['market_total_rent_estimate'] - df['min_rent']
    new_columns_stage1["mr_annual_rent_y1"] = new_columns_stage1["mr_net_rent_y1"] * 12
    new_columns_stage1["mr_annual_rent_y2"] = df["market_total_rent_estimate"] * 12
    new_columns_stage1["mr_monthly_NOI_y1"] = new_columns_stage1["mr_net_rent_y1"] - new_columns_stage1["mr_operating_expenses"]
    new_columns_stage1["mr_monthly_NOI_y2"] = df["market_total_rent_estimate"] - new_columns_stage1["mr_operating_expenses"]
    new_columns_stage1["mr_annual_NOI_y1"] = new_columns_stage1["mr_monthly_NOI_y1"] * 12
    new_columns_stage1["mr_annual_NOI_y2"] = new_columns_stage1["mr_monthly_NOI_y2"] * 12
    new_columns_stage1["mr_monthly_cash_flow_y1"] = new_columns_stage1["mr_net_rent_y1"] - new_columns_stage1["mr_total_monthly_cost"] + df["ammoritization_estimate"]
    new_columns_stage1["mr_monthly_cash_flow_y2"] = df["market_total_rent_estimate"] - new_columns_stage1["mr_total_monthly_cost"] + df["ammoritization_estimate"]
    new_columns_stage1["mr_annual_cash_flow_y1"] = new_columns_stage1["mr_monthly_cash_flow_y1"] * 12
    new_columns_stage1["mr_annual_cash_flow_y2"] = new_columns_stage1["mr_monthly_cash_flow_y2"] * 12

    # Add stage 1 columns to dataframe so df.apply() functions can access them
    df = pd.concat([df, pd.DataFrame(new_columns_stage1, index=df.index)], axis=1)

    # Stage 2: Add remaining columns including those using df.apply()
    new_columns_stage2 = {}
    new_columns_stage2["cap_rate_y1"] = df["mr_annual_NOI_y1"] / df["purchase_price"]
    new_columns_stage2["cap_rate_y2"] = df["mr_annual_NOI_y2"] / df["purchase_price"]
    new_columns_stage2["CoC_y1"] = df["mr_annual_cash_flow_y1"] / df["cash_needed"]
    new_columns_stage2["CoC_y2"] = df["mr_annual_cash_flow_y2"] / df["cash_needed"]
    new_columns_stage2["GRM_y1"] = df["purchase_price"] / df["mr_annual_rent_y1"] # Gross Rent Multiplier (lower = better)
    new_columns_stage2["GRM_y2"] = df["purchase_price"] / df["mr_annual_rent_y2"]
    new_columns_stage2["MGR_PP"] = df["market_total_rent_estimate"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
    new_columns_stage2["OpEx_Rent"] = df["mr_operating_expenses"] / df["market_total_rent_estimate"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
    new_columns_stage2["DSCR"] = df["market_total_rent_estimate"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25
    new_columns_stage2["ltv_ratio"] = df["loan_amount"] / df["purchase_price"] # Loan-to-Value ratio
    new_columns_stage2["price_per_door"] = df.apply(
        lambda row: row["purchase_price"] / row["beds"] if row["units"] == 0 else row["purchase_price"] / row["units"],
        axis=1
    ) # Price per unit/door (or per bedroom for single family)
    new_columns_stage2["rent_per_sqft"] = df["market_total_rent_estimate"] / df["square_ft"] # Monthly rent per square foot (Y2 for SFH)
    new_columns_stage2["break_even_occupancy"] = df["mr_total_monthly_cost"] / df["market_total_rent_estimate"] # Break-even occupancy rate
    new_columns_stage2["break_even_vacancy"] = 1.0 - new_columns_stage2["break_even_occupancy"]
    new_columns_stage2["oer"] = df["mr_operating_expenses"] / df["market_total_rent_estimate"] # Operating Expense Ratio (standard industry metric)
    new_columns_stage2["egi"] = df["market_total_rent_estimate"] - df["mr_monthly_vacancy_costs"] # Effective Gross Income
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
    new_columns_stage2["payback_period_years"] = df.apply(calculate_payback_period, axis=1)
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
    new_columns_stage2["cash_flow_y2_downside_10pct"] = (df["market_total_rent_estimate"] * 0.9) - df["mr_total_monthly_cost"]
    new_columns_stage2["fha_self_sufficiency_ratio"] = (df["market_total_rent_estimate"] * 0.75) / new_columns_stage2["piti"]  # Uses Y2 rent (whole-property for SFH)

    # Add stage 2 columns to avoid fragmentation
    df = pd.concat([df, pd.DataFrame(new_columns_stage2, index=df.index)], axis=1)
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
    neighborhoods_df = neighborhoods.get_neighborhoods_dataframe(supabase)
    df = df.merge(neighborhoods_df, on="address1", how="left")
    df = apply_calculations_on_dataframe(df=df)
    df = apply_investment_calculations(df=df)
    console.print("[green]Property data reloaded successfully![/green]")

load_assumptions()
load_loan(LAST_USED_LOAN)
reload_dataframe()

def get_all_phase1_qualifying_properties():
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
      - Net Present Value in 10 years must be positive, thus beating the stock market
    """
    criteria = (
        "square_ft >= 1000 "
        "& cash_needed <= 25000 "
        "& ((units == 0 & monthly_cash_flow >= -200) | (units > 0 & monthly_cash_flow >= -200)) "
        "& MGR_PP > 0.01 "
        "& OpEx_Rent < 0.5 "
        "& DSCR > 1.25 "
        # "& monthly_cash_flow_y1 >= -400 "
        "& beats_market "
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
    criteria = "((neighborhood_letter_grade in ['A','B','C'] & qualification_type == 'current') | is_fsbo) & status == 'active'"
    filtered = combined.query(criteria).copy()
    return filtered 

def get_all_phase2_qualifiers():
    """
    This method filters phase 1 qualifiers based property condition, rentability, and affordability 
    Current criteria:
      - property must qualify for phase 1 research list
      - property must not have any 'deal breakers'
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
    return dataframe

def analyze_property(property_id):
    """Display detailed analysis for a single property"""
    row = df[df['address1'] == property_id].iloc[0]
    
    table = Table(title=f"Property Details: {property_id}", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="yellow", no_wrap=True)
    table.add_column("Quick Estimate", justify="right", style="cyan")
    table.add_column("MR Year 1 (Live-in)", justify="right", style="green")
    table.add_column("MR Year 2 (All Rent)", justify="right", style="blue")
    table.add_column("", style="dim white", no_wrap=True)  # Separator/Investment Metric column
    table.add_column("5Y", justify="right", style="magenta")
    table.add_column("10Y", justify="right", style="bright_magenta")
    table.add_column("20Y", justify="right", style="bright_cyan")
    
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
    
    if is_single_family:
        # For single family homes, update table title to clarify the comparison
        table.title = f"Investment Metrics: {property_id}"
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
                  format_currency(row['market_total_rent_estimate']),
                  "Value Gap %",
                  format_percentage(row['value_gap_pct_5yr'] / 100),
                  format_percentage(row['value_gap_pct_10yr'] / 100),
                  format_percentage(row['value_gap_pct_20yr'] / 100))

    table.add_row("Operating Expenses",
                  format_currency(row['operating_expenses']),
                  format_currency(row['mr_operating_expenses']),
                  format_currency(row['mr_operating_expenses']),
                  "", "", "", "")
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

    grant = format_currency(IA_FIRSTHOME_GRANT_AMT) if ASSUMPTIONS['ia_fhb_prog_upfront_option'] == "GRANT" and ASSUMPTIONS['using_ia_fhb_prog'] else "[dim]Not using grant option for Iowa First Home[/dim]"

    investment_summary = (
        f"[bold green]Investment Summary[/bold green]\n"
        f"Down Payment: {format_currency(row['down_payment'])}\n"
        f"Closing Costs: {format_currency(row['closing_costs'])}\n"
        f"Lender Discounts: {format_currency(LOAN['upfront_discounts'])}\n"
        f"IA FirstHome Grant: {grant}\n" 
        f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
        f"Loan Amount: {format_currency(row['loan_amount'])}\n"
        f"[bold blue]Purchase Price: {format_currency(row['purchase_price'])}[/bold blue]"
    )

    if ASSUMPTIONS['using_ia_fhb_prog'] and ASSUMPTIONS['ia_fhb_prog_upfront_option'] == "LOAN" and row["units"] == 0:
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
        "Scrape neighborhood from FindNeighborhoods.dsm.city",
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
        handle_neighborhood_analysis(property_id, neighborhoods, console)
        reload_dataframe()
    elif research_choice == "Extract neighborhood letter grade":
        handle_extract_neighborhood_grade(property_id, supabase, console, neighborhoods)
        reload_dataframe()
    elif research_choice == "Record price cut":
        handle_price_cut(property_id, row["purchase_price"], supabase)
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
                properties_df=dataframe, df=df, title="All active properties using FHA", show_prop_type=True, console=console
            )
        elif option == "Phase 1 - Qualifiers":
            display_all_phase1_qualifying_properties(console, df, get_all_phase1_qualifying_properties)
        elif option == "Phase 1.5 - Research List":
            display_phase1_research_list(console, get_phase1_research_list, get_combined_phase1_qualifiers)
        elif option == "Phase 1 - Total Rent Differences":
            display_phase1_total_rent_differences(console, get_combined_phase1_qualifiers)
        elif option == "All properties - Y2 Calculations":
            display_y2_calculations(console, df)
        elif option == "All properties - Property Info":
            display_all_properties_info(console, df, properties_df=df)
        elif option == "All properties - Investment Metrics":
            display_property_metrics(console, df, get_combined_phase1_qualifiers)
        elif option == "All properties - Sold / Passed":
            dataframe = df.query("status != 'active'")
            display_all_properties(
                properties_df=dataframe,
                df=df,
                title="All inactive properties using FHA",
                show_status=True,
                console=console,
            )
        elif option == "Phase 2 - Qualifiers":
            display_all_phase2_qualifying_properties(console, df, get_all_phase2_qualifiers)

def run_scripts_options():
  using_scripts = True
  choices = ["Go back", "Add property valuations to all Phase 1 properties"]
  scripts = ScriptsProvider(supabase_client=supabase, console=console)

  while using_scripts:
    option = questionary.select("Select a script", choices=choices).ask()
    if option == "Go back":
      using_scripts = False
    elif option == "Add property valuations to all Phase 1 properties":
      phase1_df = get_combined_phase1_qualifiers()
      scripts.run_add_property_values_script(properties_df=phase1_df)
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
      loans_provider.display_loans()
    elif option == "Change loans for session":
      selected_loan_id = handle_changing_loan(supabase, console)
      LAST_USED_LOAN = selected_loan_id
      load_loan(LAST_USED_LOAN)
      reload_dataframe()

if __name__ == "__main__":
  while using_application:
    choices = ['All properties', 'One property', 'One property - phase 1 research list', "Add new property", "Scripts", "Loans", "Refresh data", "Quit"]
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
      handle_scrape_neighborhood_from_findneighborhoods(property_details['address1'], supabase, console, scraper, ask_user=True)
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
