import pandas as pd

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
      * (monthly_rate * (1 + monthly_rate) ** num_payments)
      / ((1 + monthly_rate) ** num_payments - 1)
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