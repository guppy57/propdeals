import pandas as pd
import questionary
import yaml
import csv

with open('assumptions.yaml', 'r') as file:
  assumptions = yaml.safe_load(file)
  appreciation_rate = assumptions["appreciation_rate"]
  property_tax_rate = assumptions["property_tax_rate"]
  home_insurance_rate = assumptions["home_insurance_rate"]
  vacancy_rate = assumptions["vacancy_rate"]
  repair_savings_rate = assumptions["repair_savings_rate"]
  closing_costs_rate = assumptions["closing_costs_rate"]
  live_in_unit_setting = assumptions["unit_living_in"]

with open('loans.csv', 'r', newline='') as loans_file:
    reader = csv.DictReader(loans_file)
    for row in reader:
        if row["name"] != "FHA":
            continue
        interest_rate = float(row["interest_rate"])
        down_payment_rate = float(row["down_payment_rate"])
        loan_length_years = int(row["years"])
        mip_upfront_rate = float(row["mip_upfront_rate"])
        mip_annual_rate = float(row["mip_annual_rate"])

# pd.set_option("display.max_rows", None)
# pd.set_option("display.max_columns", None)
# pd.set_option("display.width", None)
# pd.set_option("display.max_colwidth", None)

df = pd.read_csv('properties.csv')
df = df.drop(["zillow_link", "full_address"], axis=1)

def calculate_mortgage(principal, annual_rate, years):
  monthly_rate = annual_rate / 12 / 100
  num_payments = years * 12

  monthly_payment = (
      principal
      * (monthly_rate * (1 + monthly_rate) ** num_payments)
      / ((1 + monthly_rate) ** num_payments - 1)
  )

  return monthly_payment

# get all per_property calculations completed 
# first, property-only calculations
df["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"]
df["home_age"] = 2025 - df["built_in"]

# second, calculate financials (ONLY DOING FHA NOW)
df["closing_costs"] = df["purchase_price"] * closing_costs_rate
df["down_payment"] = df["purchase_price"] * down_payment_rate
df["loan_amount"] = df["purchase_price"] - df["down_payment"] + (df["purchase_price"] * mip_upfront_rate)
df["monthly_mortgage"] = df["loan_amount"].apply(lambda x: calculate_mortgage(x, interest_rate, loan_length_years))
df["monthly_mip"] = (df["loan_amount"] * mip_annual_rate) / 12
df["monthly_taxes"] = (df["purchase_price"] * property_tax_rate) / 12
df["monthly_insurance"] = (df["purchase_price"] * home_insurance_rate) / 12
df["monthly_fixed_costs"] = df["monthly_mortgage"] + df["monthly_mip"] + df["monthly_taxes"] + df["monthly_insurance"]
df["monthly_vacancy_costs"] = df["monthly_fixed_costs"] * vacancy_rate
df["monthly_repair_costs"] = df["monthly_fixed_costs"] * repair_savings_rate
df["total_monthly_cost"] = df["monthly_fixed_costs"] + df["monthly_repair_costs"] + df["monthly_vacancy_costs"]
df["cash_needed"] = df["closing_costs"] + df["down_payment"]

# third, calculate cash flow variables for analysis
# need to use rent estimates data for each property
rents = pd.read_csv('rent_estimates.csv')
# Aggregate: sum all rents and find minimum rent per property
rent_summary = rents.groupby("address_1")["rent_estimate"].agg(["sum", "min"]).reset_index()
rent_summary.columns = ["address1", "total_rent", "min_rent"]

# Calculate net rental income (total - cheapest unit you'll live in)
rent_summary["net_rent_y1"] = rent_summary["total_rent"] - rent_summary["min_rent"]

# Merge with properties
df = df.merge(rent_summary, on="address1", how="left")

df["annual_rent_y1"] = df["net_rent_y1"] * 12
df["annual_rent_y2"] = df["total_rent"] * 12

df["annual_cash_flow_y1"] = df["net_rent_y1"] - df["total_monthly_cost"]
df["annual_cash_flow_y2"] = df["total_rent"] - df["total_monthly_cost"]
df["monthly_cash_flow_y1"] = df["annual_cash_flow_y1"] / 12
df["monthly_cash_flow_y2"] = df["annual_cash_flow_y2"] / 12

# fourth, calculate investment metrics
df["cap_rate_y1"] = df["annual_cash_flow_y1"] / df["purchase_price"]
df["cap_rate_y2"] = df["annual_cash_flow_y2"] / df["purchase_price"]
df["CoC_y1"] = df["cash_needed"] / df["annual_cash_flow_y1"]
df["CoC_y2"] = df["cash_needed"] / df["annual_cash_flow_y2"]

# Gross Rent Multiplier (lower = better)
df["GRM_y1"] = df["purchase_price"] / df["annual_rent_y1"]
df["GRM_y2"] = df["purchase_price"] / df["annual_rent_y2"]

using_application = True

while using_application:
  option = questionary.select("What would you like to analyze?", choices=['All properties (FHA)', 'One property', "Quit"]).ask()

  if option == "Quit":
    using_application = False
  elif option == "All properties (FHA)":
    # print(df.to_string(index=False))
    print(df.head())
    pass
  elif option == "All properties (conventional)":
    # TODO at some point
    pass
  elif option == "One property":
    property_ids = []
    with open('properties.csv', 'r') as csvfile:
      properties_reader = csv.DictReader(csvfile)
      for row in properties_reader:
        property_ids.append(row["address1"])
    property_id = questionary.select("Select property", choices=property_ids).ask()
