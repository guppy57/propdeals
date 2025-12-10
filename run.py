import os
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
from handlers import (
    handle_property_wide_research_generation,
    handle_neighborhood_analysis,
    handle_changing_loan,
    handle_extract_neighborhood_grade,
    handle_rent_research_generation,
    handle_status_change,
    handle_price_cut,
    handle_view_research_reports
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
    display_rent_estimates_comparison,
)
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
    df["annual_rent"] = df["total_rent"] * 12
    df["monthly_vacancy_costs"] = df["total_rent"] * ASSUMPTIONS['vacancy_rate']
    df["monthly_repair_costs"] = df["total_rent"] * ASSUMPTIONS['repair_savings_rate']
    df["operating_expenses"] = df["monthly_vacancy_costs"] + df["monthly_repair_costs"] + df["monthly_taxes"] + df["monthly_insurance"]
    df["total_monthly_cost"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses"]
    df["monthly_cash_flow"] = df["total_rent"] - df["total_monthly_cost"] + df['ammoritization_estimate']
    df["annual_cash_flow"] = df["monthly_cash_flow"] * 12
    return df

def apply_investment_calculations(df):
    df["mr_monthly_vacancy_costs"] = df["market_total_rent_estimate"] * ASSUMPTIONS['vacancy_rate']
    df["mr_monthly_repair_costs"] = df["market_total_rent_estimate"] * ASSUMPTIONS['repair_savings_rate']
    df["mr_operating_expenses"] = df['mr_monthly_vacancy_costs'] + df['mr_monthly_repair_costs'] + df['monthly_taxes'] + df['monthly_insurance']
    df["mr_total_monthly_cost"] = df['monthly_mortgage'] + df['monthly_mip'] + df['mr_operating_expenses']
    df["mr_net_rent_y1"] = df['market_total_rent_estimate'] - df['min_rent']
    df["mr_annual_rent_y1"] = df["mr_net_rent_y1"] * 12 
    df["mr_annual_rent_y2"] = df["market_total_rent_estimate"] * 12
    df["mr_monthly_NOI_y1"] = df["mr_net_rent_y1"] - df["mr_operating_expenses"]
    df["mr_monthly_NOI_y2"] = df["market_total_rent_estimate"] - df["mr_operating_expenses"]
    df["mr_annual_NOI_y1"] = df["mr_monthly_NOI_y1"] * 12
    df["mr_annual_NOI_y2"] = df["mr_monthly_NOI_y2"] * 12
    df["mr_monthly_cash_flow_y1"] = df["mr_net_rent_y1"] - df["mr_total_monthly_cost"] + df["ammoritization_estimate"]
    df["mr_monthly_cash_flow_y2"] = df["market_total_rent_estimate"] - df["mr_total_monthly_cost"] + df["ammoritization_estimate"]
    df["mr_annual_cash_flow_y1"] = df["mr_monthly_cash_flow_y1"] * 12
    df["mr_annual_cash_flow_y2"] = df["mr_monthly_cash_flow_y2"] * 12
    state_rate = get_state_tax_rate(ASSUMPTIONS['state_tax_code'])
    combined_tax_rate = FEDERAL_TAX_RATE + state_rate
    df["cap_rate_y1"] = df["mr_annual_NOI_y1"] / df["purchase_price"]
    df["cap_rate_y2"] = df["mr_annual_NOI_y2"] / df["purchase_price"]
    df["CoC_y1"] = df["mr_annual_cash_flow_y1"] / df["cash_needed"]
    df["CoC_y2"] = df["mr_annual_cash_flow_y2"] / df["cash_needed"]
    df["GRM_y1"] = df["purchase_price"] / df["mr_annual_rent_y1"] # Gross Rent Multiplier (lower = better)
    df["GRM_y2"] = df["purchase_price"] / df["mr_annual_rent_y2"]
    df["MGR_PP"] = df["market_total_rent_estimate"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
    df["OpEx_Rent"] = df["mr_operating_expenses"] / df["market_total_rent_estimate"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
    df["DSCR"] = df["market_total_rent_estimate"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25
    df["ltv_ratio"] = df["loan_amount"] / df["purchase_price"] # Loan-to-Value ratio
    df["price_per_door"] = df.apply(
        lambda row: row["purchase_price"] / row["beds"] if row["units"] == 0 else row["purchase_price"] / row["units"],
        axis=1
    ) # Price per unit/door (or per bedroom for single family)
    df["rent_per_sqft"] = df["market_total_rent_estimate"] / df["square_ft"] # Monthly rent per square foot (Y2 for SFH)
    df["break_even_occupancy"] = df["mr_total_monthly_cost"] / df["market_total_rent_estimate"] # Break-even occupancy rate
    df["break_even_vacancy"] = 1.0 - df["break_even_occupancy"]
    df["oer"] = df["mr_operating_expenses"] / df["market_total_rent_estimate"] # Operating Expense Ratio (standard industry metric)
    df["egi"] = df["market_total_rent_estimate"] - df["mr_monthly_vacancy_costs"] # Effective Gross Income
    df["debt_yield"] = df["mr_annual_NOI_y2"] / df["loan_amount"] # Debt Yield (lender metric)
    df["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5,ASSUMPTIONS,LOAN,))
    df["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10,ASSUMPTIONS,LOAN,))
    df["20y_forecast"] = df.apply(get_expected_gains, axis=1, args=(20,ASSUMPTIONS,LOAN,))
    df["mobility_score"] = (df["walk_score"] * 0.6) + (df["transit_score"] * 0.30) + (df["bike_score"] * 0.10)
    df["piti"] = df['monthly_mortgage'] + df['monthly_mip'] + df['monthly_taxes'] + df['monthly_insurance']
    df['costs_to_income'] = df["piti"] / ASSUMPTIONS['after_tax_monthly_income']
    df["monthly_depreciation"] = (df["purchase_price"] * (1 - LAND_VALUE_PCT)) / DEPRECIATION_YEARS / 12
    df["tax_savings_monthly"] = df["monthly_depreciation"] * combined_tax_rate
    df["after_tax_cash_flow_y1"] = df["mr_monthly_cash_flow_y1"] + df["tax_savings_monthly"]
    df["after_tax_cash_flow_y2"] = df["mr_monthly_cash_flow_y2"] + df["tax_savings_monthly"]
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
    df["leverage_benefit"] = df["CoC_y2"] - (df["mr_annual_NOI_y2"] / df["purchase_price"])
    df["payback_period_years"] = df.apply(calculate_payback_period, axis=1)
    df["irr_5yr"] = df.apply(calculate_irr, axis=1, args=(5,ASSUMPTIONS,LOAN))
    df["irr_10yr"] = df.apply(calculate_irr, axis=1, args=(10,ASSUMPTIONS,LOAN))
    df["irr_20yr"] = df.apply(calculate_irr, axis=1, args=(20,ASSUMPTIONS,LOAN))
    df["npv_5yr"] = df.apply(calculate_npv, axis=1, args=(5,ASSUMPTIONS,LOAN))
    df["npv_10yr"] = df.apply(calculate_npv, axis=1, args=(10,ASSUMPTIONS,LOAN))
    df["npv_20yr"] = df.apply(calculate_npv, axis=1, args=(20,ASSUMPTIONS,LOAN))
    df["fair_value_5yr"] = df["purchase_price"] + df["npv_5yr"]
    df["fair_value_10yr"] = df["purchase_price"] + df["npv_10yr"]
    df["fair_value_20yr"] = df["purchase_price"] + df["npv_20yr"]
    df["value_gap_pct_5yr"] = (df["npv_5yr"] / df["cash_needed"]) * 100
    df["value_gap_pct_10yr"] = (df["npv_10yr"] / df["cash_needed"]) * 100
    df["value_gap_pct_20yr"] = (df["npv_20yr"] / df["cash_needed"]) * 100
    df["beats_market"] = df["npv_10yr"] > 0
    df["cash_flow_y1_downside_10pct"] = (df["mr_net_rent_y1"] * 0.9) - df["mr_total_monthly_cost"]
    df["cash_flow_y2_downside_10pct"] = (df["market_total_rent_estimate"] * 0.9) - df["mr_total_monthly_cost"]
    df["fha_self_sufficiency_ratio"] = (df["market_total_rent_estimate"] * 0.75) / df["piti"]  # Uses Y2 rent (whole-property for SFH)
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
      - Net Present Value in 10 years must be positive, thus beating the stock market
    """
    status_criteria = "status == 'active'" if active else "status != 'active'"
    criteria = (
        f"{status_criteria} "
        "& square_ft >= 1000 "
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
                      f"After-Tax Monthly Income: {format_currency(ASSUMPTIONS['after_tax_monthly_income'])}\n"
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

    grant = format_currency(IA_FIRSTHOME_GRANT_AMT) if ASSUMPTIONS['ia_fhb_prog_upfront_option'] == "GRANT" and ASSUMPTIONS['using_ia_fhb_prog'] else "[dim]Not using grant option for Iowa First Home[/dim]"

    investment_summary = (
        f"[bold green]Investment Summary[/bold green]\n"
        f"Down Payment: {format_currency(row['down_payment'])}\n"
        f"Closing Costs: {format_currency(row['closing_costs'])}\n"
        f"Lender Discounts: {format_currency(LOAN['upfront_discounts'])}\n"
        f"IA FirstHome Grant: {grant}\n" 
        f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
        f"Loan Amount: {format_currency(row['loan_amount'])}"
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
        handle_rent_research_generation(property_id, supabase, console, handle_generate_rent_estimates)
    elif research_choice == "View existing research reports":
        handle_view_research_reports(property_id, supabase, console)
    elif research_choice == "Generate rent estimates from report":
        handle_generate_rent_estimates(property_id)
    elif research_choice == "Generate property-wide rent research":
        handle_property_wide_research_generation(property_id, supabase, console)
        reload_dataframe()
        console.print("\n[bold green]✅ Property-wide rent estimates successfully extracted and saved![/bold green]")
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
      display_new_property_qualification(console, property_details['address1'], get_all_phase1_qualifying_properties)
    elif option == "Loans":
      run_loans_options()
    elif option == "Refresh data":
      load_assumptions()
      load_loan(LAST_USED_LOAN)
      reload_dataframe()
