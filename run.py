import os
import pandas as pd
import questionary
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv
from supabase import create_client, Client
from prompt_toolkit.styles import Style
from InquirerPy import inquirer

from add_property import run_add_property
from rent_research import RentResearcher

load_dotenv()

console = Console() 
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Create white style for questionary prompts
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
  rent_appreciation_rate = assumptions["rent_appreciation_rate"]
  property_tax_rate = assumptions["property_tax_rate"]
  home_insurance_rate = assumptions["home_insurance_rate"]
  vacancy_rate = assumptions["vacancy_rate"]
  repair_savings_rate = assumptions["repair_savings_rate"]
  closing_costs_rate = assumptions["closing_costs_rate"]
  live_in_unit_setting = assumptions["unit_living_in"]

## LOAN DETAILS - load FHA loan details from Supabase and setup global variables
fha_loan_get_response = supabase.table('loans').select("*").eq("id", 1).limit(1).single().execute()

interest_rate = float(fha_loan_get_response.data['interest_rate'])
down_payment_rate = float(fha_loan_get_response.data['down_payment_rate'])
loan_length_years = float(fha_loan_get_response.data['years'])
mip_upfront_rate = float(fha_loan_get_response.data['mip_upfront_rate'])
mip_annual_rate = float(fha_loan_get_response.data['mip_annual_rate'])

def calculate_mortgage(principal, annual_rate, years):
  monthly_rate = annual_rate / 12
  num_payments = years * 12

  monthly_payment = (
      principal
      * (monthly_rate * (1 + monthly_rate) ** num_payments)
      / ((1 + monthly_rate) ** num_payments - 1)
  )

  return monthly_payment

def deal_score_property(row):
    score = 0
    
    # 1. Cash Flow Performance (0-6 points)
    score += (3 if row["monthly_cash_flow_y2"] > 500 else 
              2 if row["monthly_cash_flow_y2"] > 400 else 
              1 if row["monthly_cash_flow_y2"] > 200 else 0)
    score += (3 if row["monthly_cash_flow_y1"] > 0 else 2 if row["monthly_cash_flow_y1"] > -350 else 0)  # House-hacking bonus
    
    # 2. Return Metrics (0-4 points)  
    score += (3 if row["CoC_y2"] > 0.15 else 
              2 if row["CoC_y2"] > 0.12 else 
              1 if row["CoC_y2"] > 0.08 else 0)
    score += (1 if row["cap_rate_y2"] > 0.06 else 0)
    
    # 3. Key Investment Rules (0-6 points)
    score += (2 if row["MGR_PP"] >= 0.01 else 1 if row["MGR_PP"] >= 0.008 else 0)  # 1% rule
    score += (2 if 0.4 <= row["OpEx_Rent"] <= 0.6 else 1 if 0.3 <= row["OpEx_Rent"] <= 0.7 else 0)  # 50% rule  
    score += (2 if row["DSCR"] >= 1.25 else 1 if row["DSCR"] >= 1.1 else 0)
    
    # 4. Affordability & Risk (0-3 points)
    score += (2 if row["cash_needed"] < 20000 else 1 if row["cash_needed"] < 30000 else 0)
    score += (1 if row["GRM_y2"] < 12 else 0)  # Lower GRM is better
    
    # 5. Property Quality (0-4 points)
    score += (2 if row["cost_per_sqrft"] < 100 else 1 if row["cost_per_sqrft"] < 150 else 0)
    score += (2 if row["home_age"] < 20 else 0)
    
    return score

def mobility_score(row):
  score = (row["walk_score"] * 0.6) + (row["transit_score"] * 0.30) + (row["bike_score"] * 0.10)
  return score

def get_expected_gains(row, length_years):
  current_home_value = row["purchase_price"]
  loan_amount = row["loan_amount"]
  y1_cashflow = row["annual_cash_flow_y1"]
  y2_cashflow = row["annual_cash_flow_y2"]

  # Calculate cumulative cashflows with compound growth
  y1_cashflow_grown = y1_cashflow * (1 + rent_appreciation_rate)
  cumulative_cashflow = y1_cashflow_grown
  for year in range(2, length_years + 1):
    yearly_cashflow = y2_cashflow * ((1 + rent_appreciation_rate) ** (year - 1))
    cumulative_cashflow += yearly_cashflow

  # Property appreciation gains
  appreciation_gains = current_home_value * ((1 + appreciation_rate) ** length_years - 1)
  
  # Principal paydown using amortization formula
  monthly_rate = interest_rate / 12
  num_payments = loan_length_years * 12
  total_payments_in_period = length_years * 12
  
  # Calculate remaining balance after length_years
  remaining_balance = loan_amount * (
    ((1 + monthly_rate) ** num_payments - (1 + monthly_rate) ** total_payments_in_period) /
    ((1 + monthly_rate) ** num_payments - 1)
  )
  equity_gains = loan_amount - remaining_balance

  return cumulative_cashflow + appreciation_gains + equity_gains

def reload_dataframe():
    """Reload and recalculate all property data from supabase"""
    global df, rents
    
    console.print("[yellow]Reloading property data...[/yellow]")

    # Load fresh data from Supabase query
    properties_get_response = supabase.table('properties').select('*').execute()
    df = pd.DataFrame(properties_get_response.data)

    df = df.drop(["zillow_link", "full_address"], axis=1)
    
    # replace all WalkScore scoring values that are NA with 0
    cols = ["walk_score", "transit_score", "bike_score"]
    df[cols] = df[cols].apply(pd.to_numeric, errors="coerce")
    df[cols] = df[cols].fillna(0)

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
    df["cash_needed"] = df["closing_costs"] + df["down_payment"]

    # third, calculate cash flow variables for analysis
    # need to use rent estimates data for each property

    rents_get_response = supabase.table('rent_estimates').select('*').execute()
    rents = pd.DataFrame(rents_get_response.data)
    rents = rents.drop(['id'], axis=1)

    # Aggregate: sum all rents and find minimum rent per property
    rent_summary = rents.groupby("address1")["rent_estimate"].agg(["sum", "min"]).reset_index()
    rent_summary.columns = ["address1", "total_rent", "min_rent"]

    # Calculate net rental income (total - cheapest unit you'll live in)
    rent_summary["net_rent_y1"] = rent_summary["total_rent"] - rent_summary["min_rent"]

    # Merge with properties
    df = df.merge(rent_summary, on="address1", how="left")

    df["annual_rent_y1"] = df["net_rent_y1"] * 12
    df["annual_rent_y2"] = df["total_rent"] * 12

    df["monthly_vacancy_costs"] = df["total_rent"] * vacancy_rate
    df["monthly_repair_costs"] = df["total_rent"] * repair_savings_rate
    df["operating_expenses"] = df["monthly_vacancy_costs"] + df["monthly_repair_costs"] + df["monthly_taxes"] + df["monthly_insurance"]
    df["total_monthly_cost"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses"]

    # Net Operating Income (NOI) - this is what you use for cap rate
    df["monthly_NOI"] = df["total_rent"] - df["operating_expenses"]
    df["annual_NOI_y1"] = (df["net_rent_y1"] - df["operating_expenses"]) * 12
    df["annual_NOI_y2"] = df["monthly_NOI"] * 12

    df["monthly_cash_flow_y1"] = df["net_rent_y1"] - df["total_monthly_cost"]
    df["monthly_cash_flow_y2"] = df["total_rent"] - df["total_monthly_cost"]
    df["annual_cash_flow_y1"] = df["monthly_cash_flow_y1"] * 12
    df["annual_cash_flow_y2"] = df["monthly_cash_flow_y2"] * 12

    # fourth, calculate investment metrics
    df["cap_rate_y1"] = df["annual_NOI_y1"] / df["purchase_price"]
    df["cap_rate_y2"] = df["annual_NOI_y2"] / df["purchase_price"]
    df["CoC_y1"] = df["annual_cash_flow_y1"] / df["cash_needed"]
    df["CoC_y2"] = df["annual_cash_flow_y2"] / df["cash_needed"]
    df["GRM_y1"] = df["purchase_price"] / df["annual_rent_y1"] # Gross Rent Multiplier (lower = better)
    df["GRM_y2"] = df["purchase_price"] / df["annual_rent_y2"]
    df["MGR_PP"] = df["total_rent"] / df["purchase_price"] # Monthly Gross Rent : Purchase Price, goal is for it to be greater than 0.01
    df["OpEx_Rent"] = df["operating_expenses"] / df["total_rent"] # Operating Expenses : Gross Rent, goal is for it to be ~50%
    df["DSCR"] = df["total_rent"] / df["monthly_mortgage"] # Debt Service Coverage Ratio, goal is for it to be greater than 1.25
    df["5y_forecast"] = df.apply(get_expected_gains, axis=1, args=(5,))
    df["10y_forecast"] = df.apply(get_expected_gains, axis=1, args=(10,))

    # fifth, calculate property scores
    df["deal_score"] = df.apply(deal_score_property, axis=1)
    df["mobility_score"] = df.apply(mobility_score, axis=1)
    
    console.print("[green]Property data reloaded successfully![/green]")

# Initialize dataframe at startup
reload_dataframe()

def display_all_properties(properties_df, title):
  """Display all properties in a formatted Rich table"""
  dataframe = df if properties_df is None else properties_df
  table = Table(title=title, show_header=True, header_style="bold magenta")

  # Calculate mobility score percentiles for color coding
  mobility_75th_percentile = df['mobility_score'].quantile(0.75)
  mobility_25th_percentile = df['mobility_score'].quantile(0.25)

  # Calculate investment growth percentiles for color coding
  forecast_10y_75th_percentile = df['10y_forecast'].quantile(0.75)
  forecast_10y_25th_percentile = df['10y_forecast'].quantile(0.25)
  
  # Calculate quintile percentiles for price and cash needed (lower is better)
  price_20th = dataframe['purchase_price'].quantile(0.20)
  price_40th = dataframe['purchase_price'].quantile(0.40)
  price_60th = dataframe['purchase_price'].quantile(0.60)
  price_80th = dataframe['purchase_price'].quantile(0.80)
  
  cash_20th = dataframe['cash_needed'].quantile(0.20)
  cash_40th = dataframe['cash_needed'].quantile(0.40)
  cash_60th = dataframe['cash_needed'].quantile(0.60)
  cash_80th = dataframe['cash_needed'].quantile(0.80)
  
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
  
  # Add columns with proper alignment
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
  # table.add_column("GRM Y1", justify="right", style="orange3")
  table.add_column("1% Rule", justify="right", style="cyan")
  table.add_column("50% Rule", justify="right", style="magenta")
  table.add_column("DSCR", justify="right", style="blue")
  table.add_column("DS", justify="right", style="bold white") # deal score
  table.add_column("MS", justify="right", style="bold white") # mobility score
  table.add_column("10Y", justify="right", style="bold white") # 10 year investment growth
  
  # Add rows for each property
  for _, row in dataframe.iterrows():
      # Determine cash flow colors
      cf_y1_style = "red" if row['monthly_cash_flow_y1'] < 0 else "green"
      cf_y2_style = "red" if row['monthly_cash_flow_y2'] < 0 else "green"

      # net operating income color
      noi_style = "red" if row["monthly_NOI"] < 0 else "green"
      
      # Determine metric colors based on goals
      # mgr_pp_style = "green" if row['MGR_PP'] >= 0.01 else "red"
      opex_rent_style = "green" if 0.45 <= row['OpEx_Rent'] <= 0.55 else ("yellow" if 0.35 <= row['OpEx_Rent'] <= 0.65 else "red")
      dscr_style = "green" if row['DSCR'] >= 1.25 else "red"
      
      # Deal score color coding (24-point scale)
      deal_score_style = ("green" if row['deal_score'] >= 15 else 
                          "yellow" if row['deal_score'] >= 12 else 
                          "red")

      mobility_score_style = ("green" if row['mobility_score'] >= mobility_75th_percentile else 
                          "yellow" if row['mobility_score'] >= mobility_25th_percentile else 
                          "red")
      
      # Forecast color coding based on percentiles
      forecast_10y_style = ("green" if row['10y_forecast'] >= forecast_10y_75th_percentile else 
                            "yellow" if row['10y_forecast'] >= forecast_10y_25th_percentile else 
                            "red")
      
      # Price and cash needed quintile color coding (lower values = better)
      price_style = get_quintile_color(row['purchase_price'], price_20th, price_40th, price_60th, price_80th)
      cash_style = get_quintile_color(row['cash_needed'], cash_20th, cash_40th, cash_60th, cash_80th)
      
      table.add_row(
          str(row['address1']),
          f"[{price_style}]{format_currency(row['purchase_price'])}[/{price_style}]",
          f"[{cash_style}]{format_currency(row['cash_needed'])}[/{cash_style}]",
          format_currency(row['total_monthly_cost']),
          f"[{cf_y1_style}]{format_currency(row['monthly_cash_flow_y1'])}[/{cf_y1_style}]",
          f"[{cf_y2_style}]{format_currency(row['monthly_cash_flow_y2'])}[/{cf_y2_style}]",
          f"[{noi_style}]{format_currency(row['monthly_NOI'])}[/{noi_style}]",
          format_percentage(row['cap_rate_y1']),
          format_percentage(row['cap_rate_y2']),
          format_percentage(row['CoC_y2']),
          format_number(row['GRM_y1']),
          # f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]",
          f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]",
          f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]",
          f"[{deal_score_style}]{int(row['deal_score'])}/24[/{deal_score_style}]",
          f"[{mobility_score_style}]{int(row['mobility_score'])}[/{mobility_score_style}]",
          f"[{forecast_10y_style}]{format_currency(row['10y_forecast'])}[/{forecast_10y_style}]"
      )
  
  console.print(table)

# displays all properties that match our dealflow analysis strict criteria
def display_all_phase1_qualifying_properties():
    """
    This method filters all properties based on our criteria for what is a financially viable property
    Current criteria:
      - 1% rule (monthly gross rent must be 1% or more of purchase price)
      - 50% rule (operating expenses must be 50% or lower than gross rent)
      - Cash needed must be below $25,000
      - Debt Service Coverage Ratio should be above 1.25
    """
    filtered_df = df.copy()
    filtered_df = filtered_df.query(
        "MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & cash_needed <= 25000 & monthly_cash_flow_y1 >= -400 & monthly_cash_flow_y2 >= 400"
    )
    display_all_properties(
        properties_df=filtered_df, title="Phase 1 Criteria Qualifying Properties"
    )

# determines what price each property would have to be to qualify for phase 1 criteria 
def fit_purchase_price_to_phase_1():
  """
  Method determines what percentage to decrease purchase price to fix all of our phase 1 criteria
  This factor would then answer the question: "At what price does this property qualify for Phase 1"

  We will *not* apply this to properties that *already qualify for Phase 1*
  """
  # Get properties that DON'T qualify for Phase 1 (use OR logic to catch any failing criteria)
  filtered_df = df.copy()
  filtered_df = filtered_df.query(
      "MGR_PP < 0.01 | OpEx_Rent > 0.5 | DSCR < 1.25 | cash_needed > 25000 | monthly_cash_flow_y1 < -400 | monthly_cash_flow_y2 < 400"
  )
  
  console.print(f"[yellow]Found {len(filtered_df)} properties that don't meet Phase 1 criteria[/yellow]")
  console.print("[dim]This feature is still under development[/dim]")
  
  # TODO: Implement price adjustment calculation
  # For each property, calculate what price would make:
  # - MGR_PP >= 0.01 (1% rule)
  # - OpEx_Rent <= 0.5 (50% rule) 
  # - DSCR >= 1.25
  # - cash_needed <= 25000
  # - monthly_cash_flow_y1 >= -400
  # - monthly_cash_flow_y2 >= 400

  for _, row in filtered_df.iterrows():
    x_1 = row["total_rent"] / (row["purchase_price"] * 0.0105) # find x for MGR_PP
    x_2 


def display_all_properties_info(properties_df):
    """Display all properties with basic info: address, sqft, age, units, mobility scores, and electricity cost"""
    dataframe = df if properties_df is None else properties_df
    table = Table(
        title="Properties Basic Information",
        show_header=True,
        header_style="bold magenta",
    )

    # Calculate percentiles for color coding from the dataframe being displayed
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

    # Add columns with proper alignment
    table.add_column("Address", style="cyan", no_wrap=True)
    table.add_column("Sqrft", justify="right", style="green")
    table.add_column("Built", justify="right", style="yellow")
    table.add_column("Units", justify="center", style="blue")
    table.add_column("Walk", justify="right", style="orange3")
    table.add_column("Transit", justify="right", style="orange3")
    table.add_column("Bike", justify="right", style="orange3")
    table.add_column("Elec.", justify="right", style="red")

    # Add rows for each property
    for _, row in dataframe.iterrows():
        # Convert units to descriptive text
        units_value = int(row["units"])
        if units_value == 2:
            units_display = "duplex"
        elif units_value == 3:
            units_display = "triplex"
        elif units_value == 4:
            units_display = "fourplex"
        else:
            units_display = str(units_value)

        # Color coding for metrics based on percentiles
        # Square footage: higher is better
        sqft_style = (
            "green"
            if row["square_ft"] >= sqft_75th_percentile
            else "yellow"
            if row["square_ft"] >= sqft_25th_percentile
            else "red"
        )

        # Age: lower is better (younger houses are green)
        built_in_style = (
            "green"
            if row["home_age"] <= built_25th_percentile
            else "yellow"
            if row["home_age"] <= built_75th_percentile
            else "red"
        )

        # Walk score: higher is better
        walk_style = (
            "green"
            if row["walk_score"] >= walk_75th_percentile
            else "yellow"
            if row["walk_score"] >= walk_25th_percentile
            else "red"
        )

        # Transit score: higher is better
        transit_style = (
            "green"
            if row["transit_score"] >= transit_75th_percentile
            else "yellow"
            if row["transit_score"] >= transit_25th_percentile
            else "red"
        )

        # Bike score: higher is better
        bike_style = (
            "green"
            if row["bike_score"] >= bike_75th_percentile
            else "yellow"
            if row["bike_score"] >= bike_25th_percentile
            else "red"
        )

        # Electricity cost: lower is better (reverse logic)
        elec_style = (
            "green"
            if row["annual_electricity_cost_est"] <= elec_25th_percentile
            else "yellow"
            if row["annual_electricity_cost_est"] <= elec_75th_percentile
            else "red"
        )

        table.add_row(
            str(row["address1"]),
            f"[{sqft_style}]{int(row['square_ft']):,}[/{sqft_style}]",
            f"[{built_in_style}]{int(row['built_in'])}[/{built_in_style}]",
            units_display,
            f"[{walk_style}]{int(row['walk_score'])}[/{walk_style}]",
            f"[{transit_style}]{int(row['transit_score'])}[/{transit_style}]",
            f"[{bike_style}]{int(row['bike_score'])}[/{bike_style}]",
            f"[{elec_style}]{format_currency(row['annual_electricity_cost_est'])}[/{elec_style}]",
        )

    console.print(table)

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
    property_rents = rents[rents['address1'] == property_id]
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
                      f"[bold]Full Rental Income (Year 2): {format_currency(row['total_rent'])}[/bold]\n\n"
                      f"[bold yellow]Operating Expenses:[/bold yellow]\n"
                      f"Monthly Operating Expenses: {format_currency(row['operating_expenses'])} ({format_currency(row['operating_expenses'] * 12)} annually)\n\n"
                      f"[bold green]Net Operating Income (NOI):[/bold green]\n"
                      f"NOI Year 1 (Live-in): {format_currency(row['net_rent_y1'] - row['operating_expenses'])} ({format_currency(row['annual_NOI_y1'])} annually)\n"
                      f"NOI Year 2 (All Rent): {format_currency(row['monthly_NOI'])} ({format_currency(row['annual_NOI_y2'])} annually)", 
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
    table.add_row("5-Year Investment Gain",
                  format_currency(row['5y_forecast']),
                  format_currency(row['5y_forecast']))
    table.add_row("10-Year Investment Gain",
                  format_currency(row['10y_forecast']),
                  format_currency(row['10y_forecast']))
    
    # Add new metrics with color coding
    mgr_pp_style = "green" if row['MGR_PP'] >= 0.01 else "red"
    opex_rent_style = "green" if 0.45 <= row['OpEx_Rent'] <= 0.55 else ("yellow" if 0.35 <= row['OpEx_Rent'] <= 0.65 else "red")
    dscr_style = "green" if row['DSCR'] >= 1.25 else "red"
    
    table.add_row("1% Rule (MGR/PP)",
                  f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]",
                  f"[{mgr_pp_style}]{format_percentage(row['MGR_PP'])}[/{mgr_pp_style}]")
    table.add_row("50% Rule (OpEx/Rent)",
                  f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]",
                  f"[{opex_rent_style}]{format_percentage(row['OpEx_Rent'])}[/{opex_rent_style}]")
    table.add_row("DSCR (Rent/Mortgage)",
                  f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]",
                  f"[{dscr_style}]{format_number(row['DSCR'])}[/{dscr_style}]")
    
    console.print(table)
    
    # Investment Criteria Scoring Table
    criteria_table = Table(title="Investment Criteria Breakdown", show_header=True, header_style="bold magenta")
    criteria_table.add_column("Criteria", style="yellow", width=25)
    criteria_table.add_column("Score", justify="right", style="white", width=8)
    criteria_table.add_column("Max", justify="right", style="dim white", width=5)
    criteria_table.add_column("Details", style="dim cyan")
    
    # Calculate individual component scores for display (match the actual scoring function)
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
    
    # Deal score color
    deal_score_style = ("green" if row['deal_score'] >= 15 else "yellow" if row['deal_score'] >= 12 else "red")
    
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
    criteria_table.add_row("[bold]TOTAL SCORE[/bold]", f"[bold {deal_score_style}]{int(row['deal_score'])}[/bold {deal_score_style}]", "[bold]24[/bold]", 
                          f"[bold {deal_score_style}]{'Excellent' if row['deal_score'] >= 15 else 'Good' if row['deal_score'] >= 12 else 'Poor'}[/bold {deal_score_style}]")
    
    console.print(criteria_table)

    # Mobility Score Breakdown Table
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
    cost_table.add_row("Electricity (est.)", format_currency(row['annual_electricity_cost_est']), format_currency(row['annual_electricity_cost_est'] / 12))
    
    console.print(cost_table)
    
    # Investment summary
    console.print(Panel(f"[bold green]Investment Summary[/bold green]\n"
                      f"Down Payment: {format_currency(row['down_payment'])}\n"
                      f"Closing Costs: {format_currency(row['closing_costs'])}\n"
                      f"[bold]Total Cash Needed: {format_currency(row['cash_needed'])}[/bold]\n"
                      f"Loan Amount: {format_currency(row['loan_amount'])}", 
                      title="Investment Requirements"))
    
    # Rent research options
    console.print("\n")
    research_choice = questionary.select(
        "Would you like to generate or view rental market research for this property?",
        choices=[
            "Generate new rent research (AI-powered)",
            "View existing research reports", 
            "Skip - return to main menu"
        ]
    ).ask()
    
    if research_choice == "Generate new rent research (AI-powered)":
        handle_rent_research_generation(property_id)
    elif research_choice == "View existing research reports":
        handle_view_research_reports(property_id)

def handle_rent_research_generation(property_id: str):
    researcher = RentResearcher(supabase, console)
    
    try:
        report_id = researcher.generate_rent_research(property_id)
        
        if report_id:
            console.print(f"[green]✅ Research completed! Report ID: {report_id}[/green]")
            
            # Ask if user wants to view the report immediately
            view_now = questionary.confirm("Would you like to view the report now?").ask()
            
            if view_now:
                report_data = researcher.get_report_by_id(report_id)
                if report_data:
                    researcher.display_report(report_data['report_content'])
        else:
            console.print("[red]❌ Research generation failed.[/red]")
            
    except Exception as e:
        console.print(f"[red]Error during research generation: {str(e)}[/red]")

def handle_view_research_reports(property_id: str):
    """Handle viewing existing research reports for a property"""
    
    researcher = RentResearcher(supabase, console)
    reports = researcher.get_reports_for_property(property_id)
    
    if not reports:
        console.print("[yellow]No research reports found for this property.[/yellow]")
        return
    
    # Create report selection list
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
    
    # Extract report ID from selection
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

def view_loans_table():
  pass

using_application = True

def run_all_properties_options():
  using_all_properties = True
  choices = ["Go back", "FHA Loan - All properties", "Phase 1 Qualifiers", "Property Info"]

  while using_all_properties:
    option = questionary.select("What would you like to display?", choices=choices).ask()

    if option == "Go back":
      using_all_properties = False
    elif option == "FHA Loan - All properties":
      display_all_properties(properties_df=None, title="Property Analysis - FHA Loan Scenario")
    elif option == "Phase 1 Qualifiers":
      display_all_phase1_qualifying_properties()
    elif option == "Property Info":
      display_all_properties_info(properties_df=df)

def run_loans_options():
  using_loans = True
  choices = ["Go back", "Add new loan", "View loans"]

  while using_loans:
    option = questionary.select("Select an option", choices=choices).ask()
    if option == "Go back":
      using_loans = False
    elif option == "Add new loan":
      console.print("Coming soon!!")
    elif option == "View loans":
      view_loans_table()

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
    run_add_property(supabase_client=supabase)
    reload_dataframe()
  elif option == "Loans":
    run_loans_options()
  elif option == "Refresh data":
    reload_dataframe()
