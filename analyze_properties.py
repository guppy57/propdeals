import pandas as pd
import questionary
import yaml
import csv
from rich.console import Console 
from rich.table import Table
from rich.panel import Panel

console = Console() 

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
  monthly_rate = annual_rate / 12
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
df["operating_expenses"] = df["monthly_vacancy_costs"] + df["monthly_repair_costs"] + df["monthly_taxes"] + df["monthly_insurance"]
df["total_monthly_cost"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses"]
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

df["monthly_cash_flow_y1"] = df["net_rent_y1"] - df["total_monthly_cost"]
df["monthly_cash_flow_y2"] = df["total_rent"] - df["total_monthly_cost"]
df["annual_cash_flow_y1"] = df["monthly_cash_flow_y1"] * 12
df["annual_cash_flow_y2"] = df["monthly_cash_flow_y2"] * 12

# fourth, calculate investment metrics
df["cap_rate_y1"] = df["annual_cash_flow_y1"] / df["purchase_price"]
df["cap_rate_y2"] = df["annual_cash_flow_y2"] / df["purchase_price"]
df["CoC_y1"] = df["annual_cash_flow_y1"] / df["cash_needed"]
df["CoC_y2"] = df["annual_cash_flow_y2"] / df["cash_needed"]
df["GRM_y1"] = df["purchase_price"] / df["annual_rent_y1"] # Gross Rent Multiplier (lower = better)
df["GRM_y2"] = df["purchase_price"] / df["annual_rent_y2"]
df["MGR_PP"] = df["total_rent"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
df["OpEx_Rent"] = df["operating_expenses"] / df["total_rent"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
df["DSCR"] = df["total_rent"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25

def display_all_properties(properties_df):
    """Display all properties in a formatted Rich table"""
    dataframe = df if properties_df is None else properties_df
    table = Table(title="Property Analysis - FHA Loan Scenario", show_header=True, header_style="bold magenta")
    
    # Add columns with proper alignment
    table.add_column("Address", style="cyan", no_wrap=True)
    table.add_column("Purchase Price", justify="right", style="green")
    table.add_column("Cash Needed", justify="right", style="yellow")
    table.add_column("Costs/Month", justify="right", style="yellow")
    table.add_column("Monthly CF Y1", justify="right", style="red" if df['monthly_cash_flow_y1'].iloc[0] < 0 else "green")
    table.add_column("Monthly CF Y2", justify="right", style="red" if df['monthly_cash_flow_y2'].iloc[0] < 0 else "green")
    table.add_column("Cap Rate Y1", justify="right", style="blue")
    table.add_column("Cap Rate Y2", justify="right", style="blue")
    table.add_column("CoC Y1", justify="right", style="purple")
    table.add_column("GRM Y1", justify="right", style="orange3")
    
    # Add rows for each property
    for _, row in dataframe.iterrows():
        # Determine cash flow colors
        cf_y1_style = "red" if row['monthly_cash_flow_y1'] < 0 else "green"
        cf_y2_style = "red" if row['monthly_cash_flow_y2'] < 0 else "green"
        
        table.add_row(
            str(row['address1']),
            format_currency(row['purchase_price']),
            format_currency(row['cash_needed']),
            format_currency(row['total_monthly_cost']),
            f"[{cf_y1_style}]{format_currency(row['monthly_cash_flow_y1'])}[/{cf_y1_style}]",
            f"[{cf_y2_style}]{format_currency(row['monthly_cash_flow_y2'])}[/{cf_y2_style}]",
            format_percentage(row['cap_rate_y1']),
            format_percentage(row['cap_rate_y2']),
            format_percentage(row['CoC_y1']),
            format_number(row['GRM_y1'])
        )
    
    console.print(table)

# displays all properties that match our dealflow analysis strict criteria
def display_all_qualifying_properties():
  display_all_properties(properties_df=df)

using_application = True

def analyze_property(property_id):
    """Display detailed analysis for a single property"""
    row = df[df['address1'] == property_id].iloc[0]
    
    # Create property details table
    table = Table(title=f"Property Details: {property_id}", show_header=True, header_style="bold cyan")
    table.add_column("Metric", style="yellow", no_wrap=True)
    table.add_column("Year 1 (Live-in)", justify="right", style="green")
    table.add_column("Year 2 (All Rent)", justify="right", style="blue")
    
    # Property basics
    console.print(Panel(f"[bold cyan]Property Overview[/bold cyan]\n"
                      f"Address: {row['address1']}\n"
                      f"Purchase Price: {format_currency(row['purchase_price'])}\n"
                      f"Bedrooms: {int(row['beds'])} | Bathrooms: {int(row['baths'])} | Sq Ft: {format_number(row['square_ft'])}\n"
                      f"Built: {int(row['built_in'])} (Age: {int(row['home_age'])} years)\n"
                      f"Units: {int(row['units'])}\n"
                      f"Cost per Sq Ft: {format_currency(row['cost_per_sqrft'])}", 
                      title="Basic Info"))
    
    # Rent estimates table
    property_rents = rents[rents['address_1'] == property_id]
    min_rent_value = property_rents['rent_estimate'].min()
    
    rent_table = Table(title="Unit Rent Estimates", show_header=True, header_style="bold green")
    rent_table.add_column("Unit", style="cyan", justify="center")
    rent_table.add_column("Configuration", style="yellow")
    rent_table.add_column("Monthly Rent", justify="right", style="green")
    rent_table.add_column("Status", style="magenta")
    
    total_monthly_rent = 0
    for _, rent_row in property_rents.iterrows():
        is_your_unit = rent_row['rent_estimate'] == min_rent_value
        unit_config = f"{int(rent_row['beds'])}-bed {int(rent_row['baths'])}-bath"
        status = "[bold red]Your Unit[/bold red]" if is_your_unit else "Rental"
        rent_style = "bold red" if is_your_unit else "green"
        
        rent_table.add_row(
            str(int(rent_row['unit_num'])),
            unit_config,
            f"[{rent_style}]{format_currency(rent_row['rent_estimate'])}[/{rent_style}]",
            status
        )
        total_monthly_rent += rent_row['rent_estimate']
    
    # Add summary row
    rent_table.add_row(
        "[bold]Total[/bold]",
        "",
        f"[bold blue]{format_currency(total_monthly_rent)}[/bold blue]",
        ""
    )
    
    console.print(rent_table)
    
    # Rental income summary
    console.print(Panel(f"[bold blue]Rental Income Summary[/bold blue]\n"
                      f"Total Monthly Rent (All Units): {format_currency(row['total_rent'])}\n"
                      f"Your Unit Rent (Not Collected): {format_currency(row['min_rent'])}\n"
                      f"[bold]Net Monthly Income (Year 1): {format_currency(row['net_rent_y1'])}[/bold]\n"
                      f"[bold]Full Rental Income (Year 2): {format_currency(row['total_rent'])}[/bold]", 
                      title="Income Breakdown"))
    
    # Financial metrics table
    table.add_row("Monthly Cash Flow", 
                  f"[{'red' if row['monthly_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y1'])}[/]",
                  f"[{'red' if row['monthly_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['monthly_cash_flow_y2'])}[/]")
    table.add_row("Annual Cash Flow",
                  f"[{'red' if row['annual_cash_flow_y1'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y1'])}[/]",
                  f"[{'red' if row['annual_cash_flow_y2'] < 0 else 'green'}]{format_currency(row['annual_cash_flow_y2'])}[/]")
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
    
    console.print(table)
    
    # Cost breakdown
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
    
    console.print(cost_table)
    
    # Investment summary
    console.print(Panel(f"[bold green]Investment Summary[/bold green]\n"
                      f"Down Payment: {format_currency(row['down_payment'])}\n"
                      f"Closing Costs: {format_currency(row['closing_costs'])}\n"
                      f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
                      f"Loan Amount: {format_currency(row['loan_amount'])}", 
                      title="Investment Requirements"))

while using_application:
  option = questionary.select("What would you like to analyze?", choices=['All properties (FHA)', 'One property', "Quit"]).ask()

  if option == "Quit":
    using_application = False
  elif option == "All properties (FHA)":
    display_all_properties(properties_df=None)
    display_all_qualifying_properties()
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
    analyze_property(property_id)
