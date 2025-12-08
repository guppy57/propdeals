import pandas as pd
import math

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

def calculate_principal_from_payment(monthly_payment, annual_rate, years):
  """Calculate loan principal given desired monthly payment"""
  monthly_rate = annual_rate / 12
  num_payments = years * 12
  
  principal = (
      monthly_payment
      * ((1 + monthly_rate) ** num_payments - 1)
      / (monthly_rate * (1 + monthly_rate) ** num_payments)
  )
  
  return principal


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
