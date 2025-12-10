import math

import pandas as pd
import numpy as np
import numpy_financial as npf

def format_currency(value):
    """Format currency values with $ sign, commas, and 2 decimal places"""
    if pd.isna(value) or value is None:
        return "N/A"
    if value < 0:
        return f"(${abs(value):,.2f})"
    return f"${value:,.2f}"

def format_percentage(value):
    """Format percentage values with % sign and 2 decimal places"""
    if pd.isna(value) or value is None:
        return "N/A"
    return f"{value * 100:.2f}%"

def format_number(value):
    """Format regular numbers to 2 decimal places"""
    if pd.isna(value) or value is None:
        return "N/A"
    return f"{value:.2f}"

def calculate_mortgage(principal, annual_rate, years):
  monthly_rate = annual_rate / 12
  num_payments = years * 12

  monthly_payment = (
      principal
      * (monthly_rate * ((1 + monthly_rate) ** num_payments))
      / (((1 + monthly_rate) ** num_payments) - 1)
  )

  return monthly_payment

def convert_numpy_types(obj):
    """Convert numpy types to native Python types for JSON serialization"""
    import numpy as np

    if isinstance(obj, dict):
        return {k: convert_numpy_types(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        val = float(obj)
        # Replace inf/-inf with 0 for JSON compatibility
        if math.isinf(val):
            return 0
        return val
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, float):
        # Handle regular Python floats too
        if math.isinf(obj):
            return 0
        return obj
    else:
        return obj

def calculate_monthly_take_home(gross_annual_income, state_tax_code='IA'):
    """
    Calculate monthly after-tax pay for Iowa resident.

    Args:
        gross_annual_income: Annual gross income
        filing_status: 'single' or 'married' (default: 'single')

    Returns:
        Monthly take-home pay after federal and Iowa state taxes
    """

    # Federal Tax brackets for filing state = 'single'
    standard_deduction = 15000
    brackets = [
        (11600, 0.10),
        (47150, 0.12),
        (100525, 0.22),
        (191950, 0.24),
        (243725, 0.32),
        (609350, 0.35),
        (float("inf"), 0.37),
    ]

    federal_taxable = max(0, gross_annual_income - standard_deduction)

    federal_tax = 0
    previous_bracket = 0
    for bracket_limit, rate in brackets:
        if federal_taxable <= previous_bracket:
            break
        taxable_in_bracket = min(federal_taxable, bracket_limit) - previous_bracket
        federal_tax += taxable_in_bracket * rate
        previous_bracket = bracket_limit

    if state_tax_code == "IA":
        # Iowa state tax (flat 4.82% for 2025, phasing down to 3.9% by 2026)
        state_tax = gross_annual_income * 0.0482
    elif state_tax_code == "IL":
        state_tax = gross_annual_income * 0.0495

    social_security_tax = min(gross_annual_income, 168600) * 0.062  # 2025 wage base
    medicare_tax = gross_annual_income * 0.0145

    if gross_annual_income > 200000:
        medicare_tax += (gross_annual_income - 200000) * 0.009

    total_tax = federal_tax + state_tax + social_security_tax + medicare_tax
    annual_take_home = gross_annual_income - total_tax
    monthly_take_home = annual_take_home / 12

    return monthly_take_home

def express_percent_as_months_and_days(rate: float) -> str:
    try:
        days = math.ceil(365 * rate)
        months = math.floor(days / 30)
        days_left = math.ceil(days % 30)
        return f"{months}m {days_left}d"
    except Exception:
        return "0m 0d"

def is_property_maps_done_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    Vectorized version of is_property_maps_done.
    Returns a Series of bool indicating whether each property has complete maps data.

    Args:
        df: DataFrame with properties

    Returns:
        Series of bool values
    """
    places = [
        "gas_station",
        "school",
        "university",
        "grocery_or_supermarket",
        "hospital",
        "park",
        "transit_station",
    ]

    # Start with all True
    is_done = pd.Series(True, index=df.index)

    # For each place type, check both distance and count columns
    for place in places:
        distance_col = f"{place}_distance_miles"
        count_col = f"{place}_count_5mi"

        # Mark as not done if either column is missing or has null/NaN
        if distance_col in df.columns:
            is_done &= df[distance_col].notna()
        else:
            is_done = False  # Column doesn't exist at all

        if count_col in df.columns:
            is_done &= df[count_col].notna()
        else:
            is_done = False  # Column doesn't exist at all

    return is_done


def is_property_assessment_done_vectorized(df: pd.DataFrame) -> pd.Series:
    """
    Vectorized version of is_property_assessment_done.
    Returns a Series of bool indicating whether each property has complete assessment data.

    Args:
        df: DataFrame with properties

    Returns:
        Series of bool values
    """
    bool_fields = [
        "obtained_county_records",
        "has_short_ownership_pattern",
        "has_deed_restrictions",
        "has_hao",
        "has_historic_preservation",
        "has_easements",
        "in_flood_zone",
        "has_open_pulled_permits",
        "has_work_done_wo_permits",
    ]

    other_fields = ["previous_owner_count", "last_purchase_price", "last_purchase_date"]

    text_fields = [
        "setbacks",
        "easements",
        "county_record_notes",
        "permit_notes",
        "whitepages_notes",
    ]

    # Start with all True
    is_done = pd.Series(True, index=df.index)

    # Check bool_fields and other_fields - must not be None or NaN
    for field in bool_fields + other_fields:
        if field in df.columns:
            is_done &= df[field].notna()
        else:
            is_done = False  # Column doesn't exist

    # Check text_fields - must not be None, NaN, or empty string
    for field in text_fields:
        if field in df.columns:
            # Must be not null AND not empty string
            is_done &= df[field].notna() & (df[field] != "")
        else:
            is_done = False  # Column doesn't exist

    return is_done

def get_expected_gains(row, length_years, assumptions, loan):
    current_home_value = row["purchase_price"]
    loan_amount = row["loan_amount"]
    y1_cashflow = row["mr_annual_cash_flow_y1"]
    y2_cashflow = row["mr_annual_cash_flow_y2"]

    # Year 1 is the base year (no appreciation applied)
    cumulative_cashflow = y1_cashflow
    for year in range(2, length_years + 1):
        # Year 2 starts with base y2_cashflow, then compounds
        yearly_cashflow = y2_cashflow * ((1 + assumptions['rent_appreciation_rate']) ** (year - 2))
        cumulative_cashflow += yearly_cashflow

    rate = assumptions['appreciation_rate'] if row["units"] == 0 else assumptions['mf_appreciation_rate']
    appreciation_gains = current_home_value * ((1 + rate) ** length_years - 1)
    monthly_rate = loan['apr_rate'] / 12
    num_payments = loan['loan_length_years'] * 12
    total_payments_in_period = length_years * 12
    remaining_balance = loan_amount * (
        (
            (1 + monthly_rate) ** num_payments
            - (1 + monthly_rate) ** total_payments_in_period
        )
        / ((1 + monthly_rate) ** num_payments - 1)
    )
    equity_gains = loan_amount - remaining_balance
    return cumulative_cashflow + appreciation_gains + equity_gains

def calculate_payback_period(row):
    """Calculate payback period accounting for Year 1 losses"""
    if row["mr_annual_cash_flow_y1"] < 0:
        # Year 1 we lose money, need to recover initial investment + Year 1 losses
        total_to_recover = row["cash_needed"] + abs(row["mr_annual_cash_flow_y1"])
    else:
        # Year 1 profitable, deduct from recovery needed
        total_to_recover = row["cash_needed"] - row["mr_annual_cash_flow_y1"]

    if row["mr_annual_cash_flow_y2"] <= 0:
        return float("inf")  # Never pays back

    # +1 for Year 1 already passed
    payback_years = 1 + (total_to_recover / row["mr_annual_cash_flow_y2"])
    return payback_years

def get_state_tax_rate(state_code):
    """Get state marginal tax rate from state code"""
    state_rates = {
        "IA": 0.0482,  # Iowa 4.82%
        "IL": 0.0495,  # Illinois 4.95%
    }
    return state_rates.get(state_code, 0.05)  # Default to 5% if state not found

def calculate_net_proceeds(
    row, years, selling_costs_rate=0.07, capital_gains_rate=0.15, assumptions={}, loan={}
):
    """Calculate net proceeds from sale after N years"""
    # Future property value (single family vs multi-family appreciation rates)
    rate = assumptions['appreciation_rate'] if row["units"] == 0 else assumptions['mf_appreciation_rate']
    future_value = row["purchase_price"] * ((1 + rate) ** years)

    # Remaining loan balance
    loan_amount = row["loan_amount"]
    monthly_rate = loan['apr_rate'] / 12
    num_payments = loan['loan_length_years'] * 12
    total_payments_in_period = years * 12
    additional_loan = (
        row["5_pct_loan"]
        if (
            row["units"] == 0
            and assumptions['using_ia_fhb_prog']
            and assumptions['ia_fhb_prog_upfront_option'] == "LOAN"
        )
        else 0
    )
    remaining_balance = (
        loan_amount
        * (
            (
                (1 + monthly_rate) ** num_payments
                - (1 + monthly_rate) ** total_payments_in_period
            )
            / ((1 + monthly_rate) ** num_payments - 1)
        )
    ) + additional_loan

    # Selling costs (agent commission + closing costs)
    selling_costs = future_value * selling_costs_rate

    # Capital gains tax (only on appreciation)
    capital_gain = future_value - row["purchase_price"]
    capital_gains_tax = capital_gain * capital_gains_rate if capital_gain > 0 else 0

    # Net proceeds = Future value - Loan payoff - Selling costs - Taxes
    net_proceeds = future_value - remaining_balance - selling_costs - capital_gains_tax

    return net_proceeds

def calculate_irr(row, years, assumptions, loan):
    """Calculate Internal Rate of Return over N years"""
    try:
        # Build cash flow array
        cash_flows = [-row["cash_needed"]]  # Year 0: initial investment (outflow)

        # Year 1 cash flow
        cash_flows.append(row["mr_annual_cash_flow_y1"])

        # Years 2 through N: compounded with rent appreciation
        for year in range(2, years + 1):
            yearly_cashflow = row["mr_annual_cash_flow_y2"] * (
                (1 + assumptions['rent_appreciation_rate']) ** (year - 2)
            )
            cash_flows.append(yearly_cashflow)

        # Final year: add net proceeds from sale
        net_proceeds = calculate_net_proceeds(row, years, assumptions=assumptions, loan=loan)
        cash_flows[-1] += net_proceeds

        # Calculate IRR
        irr = npf.irr(cash_flows)
        return irr if not math.isnan(irr) else 0
    except Exception:
        return 0  # Return 0 if calculation fails

def calculate_npv(row, years, assumptions, loan):
    """Calculate Net Present Value over N years using discount_rate"""
    try:
        # Build cash flow array (same as IRR)
        cash_flows = [-row["cash_needed"]]  # Year 0: initial investment (outflow)

        # Year 1 cash flow
        cash_flows.append(row["mr_annual_cash_flow_y1"])

        # Years 2 through N: compounded with rent appreciation
        for year in range(2, years + 1):
            yearly_cashflow = row["mr_annual_cash_flow_y2"] * (
                (1 + assumptions['rent_appreciation_rate']) ** (year - 2)
            )
            cash_flows.append(yearly_cashflow)

        # Final year: add net proceeds from sale
        net_proceeds = calculate_net_proceeds(row, years, assumptions=assumptions, loan=loan)
        cash_flows[-1] += net_proceeds

        # Calculate NPV: discount each cash flow back to present
        npv = 0
        for year, cash_flow in enumerate(cash_flows):
            npv += cash_flow / ((1 + assumptions['discount_rate']) ** year)

        return npv
    except Exception:
        return 0  # Return 0 if calculation fails

def calculate_roe(row, loan):
    """Calculate Return on Equity for Year 2"""
    # Equity after Year 1 = down payment + principal paid in Year 1
    loan_amount = row["loan_amount"]
    monthly_rate = loan['apr_rate'] / 12
    num_payments = loan['loan_length_years'] * 12

    # Remaining balance after 1 year (12 payments)
    remaining_balance_y1 = loan_amount * (
        ((1 + monthly_rate) ** num_payments - (1 + monthly_rate) ** 12)
        / ((1 + monthly_rate) ** num_payments - 1)
    )

    # Principal paid in Year 1
    principal_paid_y1 = loan_amount - remaining_balance_y1

    # Current equity = down payment + principal paid
    current_equity = row["down_payment"] + principal_paid_y1

    # ROE = Annual cash flow Y2 / Current equity
    if current_equity > 0:
        return row["mr_annual_cash_flow_y2"] / current_equity
    return 0

def calculate_additional_room_rent(row):
    return int(row["min_rent_unit_beds"] - 1) * 400

def calculate_quintile_colors_for_metrics(dataframe):
    """
    Calculate quintile-based colors for all metrics across ALL properties.
    Uses 3-color scheme: Green (top 40%), Yellow (middle 20%), Red (bottom 40%).

    Returns a dictionary mapping (address, metric_name) -> color_string
    """
    # Define which metrics should be colored with "lower is better" logic
    lower_is_better = {
        "price_per_door",
        "break_even_occupancy",
        "oer",
        "payback_period_years",
    }

    # Metric column name to actual dataframe column mapping
    metric_columns = {
        "price_per_door": "price_per_door",
        "rent_per_sqft": "rent_per_sqft",
        "break_even_occupancy": "break_even_occupancy",
        "break_even_vacancy": "break_even_vacancy",
        "oer": "oer",
        "egi": "egi",
        "debt_yield": "debt_yield",
        "monthly_depreciation": "monthly_depreciation",
        "tax_savings_monthly": "tax_savings_monthly",
        "after_tax_cash_flow_y1": "after_tax_cash_flow_y1",
        "after_tax_cash_flow_y2": "after_tax_cash_flow_y2",
        "future_value_10yr": "future_value_10yr",
        "net_proceeds_10yr": "net_proceeds_10yr",
        "equity_multiple_10yr": "equity_multiple_10yr",
        "avg_annual_return_10yr": "avg_annual_return_10yr",
        "roe_y2": "roe_y2",
        "leverage_benefit": "leverage_benefit",
        "payback_period_years": "payback_period_years",
        "irr_10yr": "irr_10yr",
        "npv_10yr": "npv_10yr",
        "cash_flow_y2_downside_10pct": "cash_flow_y2_downside_10pct",
    }

    color_map = {}

    for metric_name, col_name in metric_columns.items():
        if col_name not in dataframe.columns:
            continue

        # Filter out special values (inf, -inf, NaN)
        valid_mask = ~(dataframe[col_name].isna() | np.isinf(dataframe[col_name]))
        valid_data = dataframe[valid_mask][col_name]

        if len(valid_data) == 0:
            # No valid data, skip this metric
            continue

        # Calculate 40th and 60th percentiles
        p40 = np.percentile(valid_data, 40)
        p60 = np.percentile(valid_data, 60)

        # Assign colors to each property for this metric
        for idx, row in dataframe.iterrows():
            address = row["address1"]
            value = row[col_name]

            # Handle special values with gray color
            if pd.isna(value) or np.isinf(value):
                color = "dim white"
            else:
                # Determine color based on quintile and direction
                if metric_name in lower_is_better:
                    # Lower is better: green for low values, red for high
                    if value <= p40:
                        color = "green"
                    elif value <= p60:
                        color = "yellow"
                    else:
                        color = "red"
                else:
                    # Higher is better: green for high values, red for low
                    if value >= p60:
                        color = "green"
                    elif value >= p40:
                        color = "yellow"
                    else:
                        color = "red"

            color_map[(address, metric_name)] = color

    return color_map