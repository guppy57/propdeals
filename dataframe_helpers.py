import numpy as np
import pandas as pd
from helpers import (
    calculate_irr,
    calculate_mortgage,
    calculate_net_proceeds,
    calculate_npv,
    calculate_payback_period,
    calculate_roe,
    get_expected_gains,
    get_state_tax_rate,
    calculate_emergency_fund,
)

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

def apply_closing_costs_calculations(df, loan):
    totals = {}
    if loan["lender_fees"] == 0 or loan["lender_fees"] is None:
      lender_costs = {}
      lender_costs["loan_origination_fee"] = df["loan_amount"] * 0.01
      lender_costs["processing_fee"] = 500
      lender_costs["underwriting_fee"] = 600
      lender_costs["credit_reporting_fee"] = 75
      df = safe_concat_columns(df, lender_costs)
      totals["total_lender_costs"] = df["loan_origination_fee"] + df["processing_fee"] + df["underwriting_fee"] + lender_costs["credit_reporting_fee"]
    else:
      totals["total_lender_costs"] = loan["lender_fees"]
    title_costs = {}
    title_costs["tax_service_fee"] = 75
    title_costs["flood_certification_fee"] = 20
    title_costs["appraisal_fee"] = 600
    title_costs["abstract_update_fee"] = 75
    title_costs["title_examination_fee"] = 215
    title_costs["title_guaranty_certificate"] = 175
    title_costs["owners_title_insurance"] = 0
    title_costs["settlement_fee"] = 520
    df = safe_concat_columns(df, title_costs)
    totals["total_title_costs"] = df["abstract_update_fee"] + df["title_guaranty_certificate"] + df["title_examination_fee"] + df["owners_title_insurance"] + df["settlement_fee"]  + title_costs["tax_service_fee"] + title_costs["flood_certification_fee"] + title_costs["appraisal_fee"]
    government_costs = {}
    government_costs["deed_recording_fee"] = 17
    government_costs["mortgage_recording_fee"] = 72
    df = safe_concat_columns(df, government_costs)
    totals["total_government_costs"] = df["deed_recording_fee"] + df["mortgage_recording_fee"] 
    prepaid_costs = {}
    prepaid_costs["prepaid_home_insurance"] = df["monthly_insurance"] * 12
    prepaid_costs["property_tax_proration"] = df["monthly_taxes"] * 4
    prepaid_costs["prepaid_interest"] = df["loan_amount"] * ((loan["interest_rate"] / 365) * 20)
    df = safe_concat_columns(df, prepaid_costs)
    totals["total_prepaid_costs"] = df["prepaid_home_insurance"] + df["property_tax_proration"] + df["prepaid_interest"]
    escrow_costs = {}
    escrow_costs["insurance_reserve"] = df["monthly_insurance"] * 3
    escrow_costs["tax_reserve"] = df["monthly_taxes"] * 3
    escrow_costs["aggregate_adjustment"] = df["monthly_taxes"] * -1
    df = safe_concat_columns(df, escrow_costs)
    totals["total_escrow_costs"] = df["insurance_reserve"] + df["tax_reserve"] + escrow_costs["aggregate_adjustment"]
    optional_costs = {}
    optional_costs["home_inspection_fee"] = 400
    optional_costs["property_survey_fee"] = 600
    optional_costs["pest_inspection_fee"] = 100
    optional_costs["structural_engineer_fee"] = 400
    optional_costs["sewer_inspection_fee"] = 200
    optional_costs["keller_williams_fee"] = 495
    optional_costs["courier_fees"] = 35
    optional_costs["notary_fees"] = 25
    df = safe_concat_columns(df, optional_costs)
    totals["total_optional_costs"] = df["home_inspection_fee"] + df["property_survey_fee"] + df["pest_inspection_fee"] + df["courier_fees"] + df["notary_fees"] + df["structural_engineer_fee"] + df["keller_williams_fee"] + df["sewer_inspection_fee"]
    df = safe_concat_columns(df, totals)
    df["closing_costs"] = df["total_lender_costs"] + df["total_title_costs"] + df["total_government_costs"] + df["total_prepaid_costs"] + df["total_escrow_costs"] + df["total_optional_costs"]
    df["closing_costs_prcnt"] = df["closing_costs"] / df["purchase_price"]
    return df

def apply_calculations_on_dataframe(df, loan, assumptions):
    cols = ["walk_score", "transit_score", "bike_score"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    df[cols] = df[cols].fillna(0)
    basic_columns = {}
    basic_columns["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"]
    basic_columns["home_age"] = 2025 - df["built_in"].fillna(2025)
    basic_columns["down_payment"] = df["purchase_price"] * loan["down_payment_rate"]
    basic_columns["5_pct_loan"] = df["purchase_price"] * 0.05
    upfront_mip = 0 if loan["loan_type"] == "FHA" else (df["purchase_price"] * loan["mip_upfront_rate"])
    reduce_downpayment_condition = ((df["units"] == 0) & loan["using_ifa_loan"])
    basic_columns["loan_amount"] = pd.Series(
        np.where(reduce_downpayment_condition,
            df["purchase_price"] - basic_columns["down_payment"] + upfront_mip - basic_columns["5_pct_loan"],
            df["purchase_price"] - basic_columns["down_payment"] + upfront_mip
        ),
        index=df.index
    )
    basic_columns["2nd_loan_type"] = pd.Series(np.where(reduce_downpayment_condition, "reduced_dp", "reduced_loan"), index=df.index)
    basic_columns["monthly_mortgage"] = basic_columns["loan_amount"].apply(lambda x: calculate_mortgage(x, loan["interest_rate"], loan["loan_length_years"]))
    if loan["pmi_amount"] is not None:
        basic_columns["monthly_mip"] = loan["pmi_amount"]
    else:
        basic_columns["monthly_mip"] = (basic_columns["loan_amount"] * loan["mip_annual_rate"]) / 12
    basic_columns["monthly_taxes"] = (df["purchase_price"] * assumptions["property_tax_rate"]) / 12
    basic_columns["monthly_insurance"] = (df["purchase_price"] * assumptions["home_insurance_rate"]) / 12
    df = safe_concat_columns(df, basic_columns)
    df = apply_closing_costs_calculations(df, loan)
    new_columns = {}
    new_columns["piti"] = df["monthly_mortgage"] + df["monthly_mip"] + df["monthly_taxes"] + df["monthly_insurance"]
    new_columns["cash_needed"] = df["closing_costs"] + df["down_payment"] - loan["upfront_discounts"]
    factor = np.where(df["units"] == 0, 0.0075, 0.0105)
    new_columns["quick_monthly_rent_estimate"] = (df["purchase_price"] * (1 + assumptions["closing_costs_rate"])) * factor
    new_columns["ammoritization_estimate"] = df["monthly_mortgage"] - (df["loan_amount"] * loan["apr_rate"] / 12)
    new_columns["total_rent"] = new_columns["quick_monthly_rent_estimate"]
    new_columns["annual_rent"] = new_columns["total_rent"] * 12
    new_columns["monthly_vacancy_costs"] = new_columns["total_rent"] * assumptions["vacancy_rate"]
    new_columns["monthly_repair_costs"] = new_columns["total_rent"] * assumptions["repair_savings_rate"]
    new_columns["monthly_capex_costs"] = new_columns["total_rent"] * assumptions["capex_reserve_rate"]
    new_columns["operating_expenses"] = new_columns["monthly_vacancy_costs"] + new_columns["monthly_repair_costs"] + new_columns["monthly_capex_costs"] + df["monthly_taxes"] + df["monthly_insurance"]
    sqft_scaling_owner_unit = df["owner_unit_sqft"] / assumptions["utility_baseline_sqft"]
    units_for_calcs = df["units"].apply(lambda x: max(1, x if pd.notna(x) and x > 0 else 1))
    new_columns["monthly_utility_electric"] = assumptions["utility_electric_base"] * sqft_scaling_owner_unit
    new_columns["monthly_utility_gas"] = assumptions["utility_gas_base"] * sqft_scaling_owner_unit
    new_columns["monthly_utility_water"] = df.apply(lambda row: 0 if row["units"] > 0 else assumptions["utility_water_base"], axis=1)
    new_columns["monthly_utility_trash"] = assumptions["utility_trash_base"] * units_for_calcs
    new_columns["monthly_utility_internet"] = df.apply(lambda row: assumptions["utility_internet_base"] if row["units"] == 0 else 0, axis=1)
    new_columns["monthly_utility_total"] = new_columns["monthly_utility_electric"] + new_columns["monthly_utility_gas"] + new_columns["monthly_utility_water"] + new_columns["monthly_utility_trash"] + new_columns["monthly_utility_internet"]
    beds_safe = df["beds"].fillna(3).clip(lower=1)
    utility_total = new_columns["monthly_utility_total"]
    roommate_utilities_sfh = utility_total * (beds_safe - 1) / beds_safe
    new_columns["roommate_utilities"] = np.where(df["units"] == 0, roommate_utilities_sfh, 0)
    new_columns["owner_utilities"] = new_columns["monthly_utility_total"] - new_columns["roommate_utilities"]
    new_columns["total_monthly_cost"] = df["monthly_mortgage"] + new_columns["operating_expenses"] + new_columns["monthly_utility_total"] + (df["monthly_mip"] if loan["down_payment_rate"] < 0.2 else 0)
    new_columns["monthly_cash_flow"] = new_columns["total_rent"] - new_columns["total_monthly_cost"] + new_columns["ammoritization_estimate"] + new_columns["roommate_utilities"]
    new_columns["annual_cash_flow"] = new_columns["monthly_cash_flow"] * 12
    df = safe_concat_columns(df, new_columns)
    misc_columns = {}
    misc_columns["3m_emergency_fund"] = df.apply(lambda x: calculate_emergency_fund(3, x["piti"], x["monthly_utility_total"]), axis=1)
    df = safe_concat_columns(df, misc_columns)
    return df

def apply_investment_calculations(df, loan, assumptions):
    state_rate = get_state_tax_rate(assumptions["state_tax_code"])
    combined_tax_rate = assumptions["federal_tax_rate"] + state_rate
    is_sfh_with_estimate = (df["units"] == 0) & df["rent_estimate"].notna() & (df["rent_estimate"] > 0)
    rent_base_columns = {}
    rent_base_columns["y1_opex_rent_base"] = np.where(is_sfh_with_estimate, df["rent_estimate"], df["market_total_rent_estimate"])
    rent_base_columns["y2_rent_base"] = rent_base_columns["y1_opex_rent_base"]
    rent_base_columns["y2_rent_base_source"] = np.where(is_sfh_with_estimate, "whole_property", "room_sum")
    df = safe_concat_columns(df, rent_base_columns)
    def calculate_roommate_utilities_y1(row):
        beds_safe = row["beds"] if pd.notna(row["beds"]) and row["beds"] > 0 else 3
        return row["monthly_utility_total"] * (beds_safe - 1) / beds_safe if row["units"] == 0 else 0
    roommate_utilities_y1 = df.apply(calculate_roommate_utilities_y1, axis=1)
    roommate_utilities_y2 = df["monthly_utility_total"]
    owner_utilities_y1 = df["monthly_utility_total"] - roommate_utilities_y1
    owner_utilities_y2 = df["monthly_utility_total"] - roommate_utilities_y2
    new_columns_stage1 = {}
    new_columns_stage1["mr_monthly_vacancy_costs"] = df["y1_opex_rent_base"] * assumptions["vacancy_rate"]
    new_columns_stage1["mr_monthly_repair_costs"] = df["y1_opex_rent_base"] * assumptions["repair_savings_rate"]
    new_columns_stage1["mr_monthly_capex_costs"] = df["y1_opex_rent_base"] * assumptions["capex_reserve_rate"]
    new_columns_stage1["mr_operating_expenses"] = new_columns_stage1["mr_monthly_vacancy_costs"] + new_columns_stage1["mr_monthly_repair_costs"] + new_columns_stage1["mr_monthly_capex_costs"] + df["monthly_taxes"] + df["monthly_insurance"]
    new_columns_stage1["mr_total_monthly_cost"] = df["monthly_mortgage"] + df["monthly_mip"] + new_columns_stage1["mr_operating_expenses"] + df["monthly_utility_total"]
    trash_adjustment_y1 = df.apply(lambda row: (row["units"] - 1) * 18 if row["units"] > 0 else 0, axis=1)
    trash_adjustment_y2 = df.apply(lambda row: row["units"] * 18 if row["units"] > 0 else 0, axis=1)
    new_columns_stage1["mr_net_rent_y1"] = df["market_total_rent_estimate"] - df["min_rent"] + trash_adjustment_y1
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
    new_columns_stage2["GRM_y1"] = df["purchase_price"] / df["mr_annual_rent_y1"]
    new_columns_stage2["GRM_y2"] = df["purchase_price"] / df["mr_annual_rent_y2"]
    new_columns_stage2["MGR_PP"] = df["y2_rent_base"] / df["purchase_price"]
    new_columns_stage2["OpEx_Rent"] = df["mr_operating_expenses"] / df["y2_rent_base"]
    new_columns_stage2["DSCR"] = df["y2_rent_base"] / df["monthly_mortgage"]
    new_columns_stage2["ltv_ratio"] = df["loan_amount"] / df["purchase_price"]
    new_columns_stage2["price_per_door"] = df.apply(lambda row: row["purchase_price"] / row["beds"] if row["units"] == 0 else row["purchase_price"] / row["units"], axis=1)
    new_columns_stage2["rent_per_sqft"] = df["y2_rent_base"] / df["square_ft"]
    new_columns_stage2["break_even_occupancy"] = df["mr_total_monthly_cost"] / df["y2_rent_base"]
    new_columns_stage2["break_even_vacancy"] = 1.0 - new_columns_stage2["break_even_occupancy"]
    new_columns_stage2["oer"] = df["mr_operating_expenses"] / df["y2_rent_base"]
    new_columns_stage2["egi"] = df["y2_rent_base"] - df["mr_monthly_vacancy_costs"]
    new_columns_stage2["debt_yield"] = df["mr_annual_NOI_y2"] / df["loan_amount"]
    new_columns_stage2["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5, assumptions, loan))
    new_columns_stage2["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10, assumptions, loan))
    new_columns_stage2["20y_forecast"] = df.apply(get_expected_gains, axis=1, args=(20, assumptions, loan))
    new_columns_stage2["mobility_score"] = (df["walk_score"] * 0.6) + (df["transit_score"] * 0.30) + (df["bike_score"] * 0.10)
    new_columns_stage2["piti"] = df["monthly_mortgage"] + df["monthly_mip"] + df["monthly_taxes"] + df["monthly_insurance"]
    new_columns_stage2["costs_to_income"] = new_columns_stage2["piti"] / assumptions["after_tax_monthly_income"]
    new_columns_stage2["monthly_depreciation"] = (df["purchase_price"] * (1 - assumptions["land_value_prcnt"])) / assumptions["residential_depreciation_period_yrs"] / 12
    new_columns_stage2["tax_savings_monthly"] = new_columns_stage2["monthly_depreciation"] * combined_tax_rate
    new_columns_stage2["after_tax_cash_flow_y1"] = df["mr_monthly_cash_flow_y1"] + new_columns_stage2["tax_savings_monthly"]
    new_columns_stage2["after_tax_cash_flow_y2"] = df["mr_monthly_cash_flow_y2"] + new_columns_stage2["tax_savings_monthly"]
    new_columns_stage2["future_value_5yr"] = df.apply(lambda row: row["purchase_price"] * ((1 + (assumptions["appreciation_rate"] if row["units"] == 0 else assumptions["mf_appreciation_rate"])) ** 5), axis=1)
    new_columns_stage2["future_value_10yr"] = df.apply(lambda row: row["purchase_price"] * ((1 + (assumptions["appreciation_rate"] if row["units"] == 0 else assumptions["mf_appreciation_rate"])) ** 10), axis=1)
    new_columns_stage2["future_value_20yr"] = df.apply(lambda row: row["purchase_price"] * ((1 + (assumptions["appreciation_rate"] if row["units"] == 0 else assumptions["mf_appreciation_rate"])) ** 20), axis=1)
    new_columns_stage2["net_proceeds_5yr"] = df.apply(calculate_net_proceeds, axis=1, args=(5, assumptions["selling_costs_rate"], assumptions["longterm_capital_gains_tax_rate"], assumptions, loan))
    new_columns_stage2["net_proceeds_10yr"] = df.apply(calculate_net_proceeds, axis=1, args=(10, assumptions["selling_costs_rate"], assumptions["longterm_capital_gains_tax_rate"], assumptions, loan))
    new_columns_stage2["net_proceeds_20yr"] = df.apply(calculate_net_proceeds, axis=1, args=(20, assumptions["selling_costs_rate"], assumptions["longterm_capital_gains_tax_rate"], assumptions, loan))
    new_columns_stage2["equity_multiple_5yr"] = (new_columns_stage2["5y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    new_columns_stage2["equity_multiple_10yr"] = (new_columns_stage2["10y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    new_columns_stage2["equity_multiple_20yr"] = (new_columns_stage2["20y_forecast"] + df["cash_needed"]) / df["cash_needed"]
    new_columns_stage2["avg_annual_return_5yr"] = ((new_columns_stage2["5y_forecast"] / df["cash_needed"]) / 5) * 100
    new_columns_stage2["avg_annual_return_10yr"] = ((new_columns_stage2["10y_forecast"] / df["cash_needed"]) / 10) * 100
    new_columns_stage2["avg_annual_return_20yr"] = ((new_columns_stage2["20y_forecast"] / df["cash_needed"]) / 20) * 100
    new_columns_stage2["roe_y2"] = df.apply(calculate_roe, axis=1, args=[loan])
    new_columns_stage2["leverage_benefit"] = new_columns_stage2["CoC_y2"] - (df["mr_annual_NOI_y2"] / df["purchase_price"])
    new_columns_stage2["payback_period_years"] = df.apply(lambda row: calculate_payback_period(row, assumptions, loan), axis=1)
    new_columns_stage2["irr_5yr"] = df.apply(calculate_irr, axis=1, args=(5, assumptions, loan))
    new_columns_stage2["irr_10yr"] = df.apply(calculate_irr, axis=1, args=(10, assumptions, loan))
    new_columns_stage2["irr_20yr"] = df.apply(calculate_irr, axis=1, args=(20, assumptions, loan))
    new_columns_stage2["npv_5yr"] = df.apply(calculate_npv, axis=1, args=(5, assumptions, loan))
    new_columns_stage2["npv_10yr"] = df.apply(calculate_npv, axis=1, args=(10, assumptions, loan))
    new_columns_stage2["npv_20yr"] = df.apply(calculate_npv, axis=1, args=(20, assumptions, loan))
    new_columns_stage2["fair_value_5yr"] = df["purchase_price"] + new_columns_stage2["npv_5yr"]
    new_columns_stage2["fair_value_10yr"] = df["purchase_price"] + new_columns_stage2["npv_10yr"]
    new_columns_stage2["fair_value_20yr"] = df["purchase_price"] + new_columns_stage2["npv_20yr"]
    new_columns_stage2["value_gap_pct_5yr"] = (new_columns_stage2["npv_5yr"] / df["cash_needed"]) * 100
    new_columns_stage2["value_gap_pct_10yr"] = (new_columns_stage2["npv_10yr"] / df["cash_needed"]) * 100
    new_columns_stage2["value_gap_pct_20yr"] = (new_columns_stage2["npv_20yr"] / df["cash_needed"]) * 100
    new_columns_stage2["beats_market"] = new_columns_stage2["npv_10yr"] > 0
    new_columns_stage2["cash_flow_y1_downside_10pct"] = (df["mr_net_rent_y1"] * 0.9) - df["mr_total_monthly_cost"]
    new_columns_stage2["cash_flow_y2_downside_10pct"] = (df["y2_rent_base"] * 0.9) - df["mr_total_monthly_cost"]
    new_columns_stage2["fha_self_sufficiency_ratio"] = (df["y2_rent_base"] * 0.75) / new_columns_stage2["piti"]
    df = safe_concat_columns(df, new_columns_stage2)
    return df

