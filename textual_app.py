"""
Property Deal Analyzer - Textual TUI Application

A modern terminal user interface for analyzing property investment deals.
"""

import os
import pandas as pd
from datetime import datetime

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static
from textual.reactive import reactive

# Import existing business logic
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# Import all business logic functions from run.py
# These are the core calculation and data functions that we'll reuse exactly as-is

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

def deal_score_property(row):
    score = 0
    
    # Helper function to safely get values with defaults
    def safe_get(key, default=0):
        try:
            return row.get(key, default) if hasattr(row, 'get') else row[key] if key in row else default
        except (KeyError, TypeError):
            return default
    
    # 1. Cash Flow Performance (0-6 points)
    cf_y2 = safe_get("monthly_cash_flow_y2", 0)
    score += (3 if cf_y2 > 500 else 
              2 if cf_y2 > 400 else 
              1 if cf_y2 > 200 else 0)
    
    cf_y1 = safe_get("monthly_cash_flow_y1", 0)
    score += (3 if cf_y1 > 0 else 2 if cf_y1 > -350 else 0)
    
    # 2. Return Metrics (0-4 points)  
    coc = safe_get("CoC_y2", 0)
    score += (3 if coc > 0.15 else 
              2 if coc > 0.12 else 
              1 if coc > 0.08 else 0)
    
    cap_rate = safe_get("cap_rate_y2", 0)
    score += (1 if cap_rate > 0.06 else 0)
    
    # 3. Key Investment Rules (0-6 points)
    mgr = safe_get("MGR_PP", 0)
    score += (2 if mgr >= 0.01 else 1 if mgr >= 0.008 else 0)
    
    opex = safe_get("OpEx_Rent", 0)
    score += (2 if 0.4 <= opex <= 0.6 else 1 if 0.3 <= opex <= 0.7 else 0)
    
    dscr = safe_get("DSCR", 0)
    score += (2 if dscr >= 1.25 else 1 if dscr >= 1.1 else 0)
    
    # 4. Affordability & Risk (0-3 points)
    cash_needed = safe_get("cash_needed", 0)
    score += (2 if cash_needed < 20000 else 1 if cash_needed < 30000 else 0)
    
    grm = safe_get("GRM_y2", 999)
    score += (1 if grm < 12 else 0)
    
    # 5. Property Quality (0-4 points)
    cost_sqft = safe_get("cost_per_sqrft", 999)
    score += (2 if cost_sqft < 100 else 1 if cost_sqft < 150 else 0)
    
    age = safe_get("home_age", 999)
    score += (2 if age < 20 else 0)
    
    return score

def mobility_score(row):
    # Helper function to safely get values with defaults
    def safe_get(key, default=0):
        try:
            return row.get(key, default) if hasattr(row, 'get') else row[key] if key in row else default
        except (KeyError, TypeError):
            return default
    
    walk = safe_get("walk_score", 0)
    transit = safe_get("transit_score", 0)
    bike = safe_get("bike_score", 0)
    
    score = (walk * 0.6) + (transit * 0.30) + (bike * 0.10)
    return score

class PropertyAnalyzerApp(App):
    """Property Deal Analyzer TUI Application"""
    
    CSS_PATH = "app.tcss"  # We'll create this for styling
    
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("1", "show_all_properties", "All Properties"),
        ("2", "show_property_search", "Single Property"),
        ("3", "add_property", "Add Property"),
        ("4", "manage_loans", "Loans"),
        ("5", "refresh_data", "Refresh"),
        ("?", "show_help", "Help"),
    ]
    
    # Reactive properties for live updates
    current_loan = reactive("FHA Default")
    current_loan_data = reactive({
        "interest_rate": 0.0622,
        "down_payment_rate": 0.035,
        "loan_length_years": 30,
        "mip_upfront_rate": 0.0175,
        "mip_annual_rate": 0.008
    })
    assumptions_data = reactive({
        "property_tax_rate": 0.016,
        "home_insurance_rate": 0.020,
        "vacancy_rate": 0.083,
        "repair_savings_rate": 0.050,
        "closing_costs_rate": 0.025,
        "appreciation_rate": 0.030,
        "rent_appreciation_rate": 0.025
    })
    properties_df = reactive(pd.DataFrame(), always_update=True)
    properties_count = reactive(0)
    last_updated = reactive(datetime.now())
    loading_data = reactive(False)
    
    def __init__(self):
        super().__init__()
        self.supabase: Client = create_client(
            os.getenv("SUPABASE_URL"), 
            os.getenv("SUPABASE_KEY")
        )
        self.setup_initial_data()
    
    def setup_initial_data(self):
        """Initialize with default data"""
        self.current_loan = "FHA Default"
        self.properties_count = 0
        self.last_updated = datetime.now()
        # Data loading will happen in on_mount when event loop is ready
    
    async def load_all_data(self):
        """Load all data from Supabase with timeout and error handling"""
        self.loading_data = True

        
        try:
            # Show loading message
            self.update_loading_status("Loading assumptions...")
            await self.load_assumptions()
            
            self.update_loading_status("Loading loan data...")
            await self.load_loan_data(1)  # Default FHA loan
            
            self.update_loading_status("Loading properties...")
            await self.load_properties_data()
            
            self.loading_data = False
            self.last_updated = datetime.now()
            self.update_loading_status("Data loaded successfully!")
            
            # Update settings display with loaded data
            self.update_settings_display()
            
        except Exception as e:
            self.loading_data = False
            self.update_loading_status(f"Data loading failed: {str(e)[:50]}...")
            # Use sample data as fallback
            self.setup_sample_data()
            # Update settings display with sample data
            self.update_settings_display()
    
    def update_loading_status(self, message: str):
        """Update main content with loading status"""
        try:
            main_content = self.query_one("#main-content", Static)
            main_content.update(f"[bold cyan]Data Status[/bold cyan]\n\n{message}")
        except Exception:
            pass  # Widget not ready yet
    
    def setup_sample_data(self):
        """Setup sample data when database is unavailable"""
        # Create a sample property for demonstration
        sample_data = {
            'address1': ['123 Sample St', '456 Demo Ave'],
            'purchase_price': [250000, 300000],
            'square_ft': [1200, 1500],
            'built_in': [2010, 2015],
            'total_rent': [2000, 2500],
            'monthly_cash_flow_y2': [300, 450],
            'CoC_y2': [0.10, 0.15],
            'cap_rate_y2': [0.05, 0.07],
            'deal_score': [12, 18],
            'mobility_score': [75, 85]
        }
        
        self.properties_df = pd.DataFrame(sample_data)
        self.properties_count = len(self.properties_df)
        self.update_loading_status("Using sample data (database unavailable)")
    
    async def load_assumptions(self):
        """Load assumptions from Supabase"""
        try:
            response = self.supabase.table('assumptions').select('*').eq('id', 1).limit(1).single().execute()
            if response.data:
                self.assumptions_data = {
                    "property_tax_rate": float(response.data["property_tax_rate"]),
                    "home_insurance_rate": float(response.data["home_insurance_rate"]),
                    "vacancy_rate": float(response.data["vacancy_rate"]),
                    "repair_savings_rate": float(response.data["repair_savings_rate"]),
                    "closing_costs_rate": float(response.data["closing_costs_rate"]),
                    "appreciation_rate": float(response.data["appreciation_rate"]),
                    "rent_appreciation_rate": float(response.data["rent_appreciation_rate"])
                }
        except Exception as e:
            # Keep default values if loading fails  
            raise Exception(f"Failed to load assumptions: {str(e)}")
    
    async def load_loan_data(self, loan_id: int):
        """Load loan data from Supabase"""
        try:
            # Import LoansProvider if available, otherwise use default data
            from loans import LoansProvider
            loan_provider = LoansProvider(supabase_client=self.supabase, console=None)
            loan = loan_provider.get_loan_by_id(loan_id)
            
            self.current_loan = loan.name
            self.current_loan_data = {
                "interest_rate": loan.interest_rate,
                "down_payment_rate": loan.down_payment_rate,
                "loan_length_years": loan.years,
                "mip_upfront_rate": loan.mip_upfront_rate,
                "mip_annual_rate": loan.mip_annual_rate
            }
        except Exception as e:
            # Keep default values if loading fails
            raise Exception(f"Failed to load loan data: {str(e)}")
    
    async def load_properties_data(self):
        """Load and calculate property data from Supabase"""
        try:
            # Load properties from Supabase
            properties_response = self.supabase.table('properties').select('*').execute()
            if not properties_response.data:
                raise Exception("No properties found in database")
                
            df = pd.DataFrame(properties_response.data)
            
            # Load rent estimates
            rents_response = self.supabase.table('rent_estimates').select('*').execute()
            rents_df = pd.DataFrame(rents_response.data)
            
            # Process the data (simplified version of reload_dataframe from run.py)
            df = self.calculate_property_metrics(df, rents_df)
            
            self.properties_df = df
            self.properties_count = len(df)
            
        except Exception as e:
            # Raise error to trigger fallback to sample data
            raise Exception(f"Failed to load properties: {str(e)}")
    
    def calculate_property_metrics(self, properties_df: pd.DataFrame, rents_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate all property investment metrics"""
        df = properties_df.copy()
        
        # Get current loan and assumption values
        loan_data = self.current_loan_data
        assumptions = self.assumptions_data
        
        # Ensure required columns exist with defaults
        required_columns = {
            'purchase_price': 0,
            'square_ft': 1,
            'built_in': 2020,
            'address1': 'Unknown'
        }
        
        for col, default_val in required_columns.items():
            if col not in df.columns:
                df[col] = default_val
        
        # Basic property calculations with safe division
        df["cost_per_sqrft"] = df["purchase_price"] / df["square_ft"].replace(0, 1)  # Avoid division by zero
        df["home_age"] = 2025 - df["built_in"]
        
        # Financial calculations
        df["closing_costs"] = df["purchase_price"] * assumptions["closing_costs_rate"]
        df["down_payment"] = df["purchase_price"] * loan_data["down_payment_rate"]
        df["loan_amount"] = df["purchase_price"] - df["down_payment"] + (df["purchase_price"] * loan_data["mip_upfront_rate"])
        
        # Calculate monthly payments
        df["monthly_mortgage"] = df["loan_amount"].apply(
            lambda x: calculate_mortgage(x, loan_data["interest_rate"], loan_data["loan_length_years"])
        )
        df["monthly_mip"] = (df["loan_amount"] * loan_data["mip_annual_rate"]) / 12
        df["monthly_taxes"] = (df["purchase_price"] * assumptions["property_tax_rate"]) / 12
        df["monthly_insurance"] = (df["purchase_price"] * assumptions["home_insurance_rate"]) / 12
        df["cash_needed"] = df["closing_costs"] + df["down_payment"]
        
        # Add rent data if available
        if not rents_df.empty and "address1" in rents_df.columns and "rent_estimate" in rents_df.columns:
            try:
                rent_summary = rents_df.groupby("address1")["rent_estimate"].agg(["sum", "min"]).reset_index()
                rent_summary.columns = ["address1", "total_rent", "min_rent"]
                rent_summary["net_rent_y1"] = rent_summary["total_rent"] - rent_summary["min_rent"]
                df = df.merge(rent_summary, on="address1", how="left")
            except Exception:
                # If rent data processing fails, add default columns
                df["total_rent"] = 0
                df["min_rent"] = 0
                df["net_rent_y1"] = 0
        else:
            # Add default rent columns if no rent data
            df["total_rent"] = 0
            df["min_rent"] = 0
            df["net_rent_y1"] = 0
            
            # Calculate cash flows and metrics
            df["monthly_vacancy_costs"] = df["total_rent"] * assumptions["vacancy_rate"]
            df["monthly_repair_costs"] = df["total_rent"] * assumptions["repair_savings_rate"]
            df["operating_expenses"] = (df["monthly_vacancy_costs"] + df["monthly_repair_costs"] + 
                                      df["monthly_taxes"] + df["monthly_insurance"])
            df["total_monthly_cost"] = df["monthly_mortgage"] + df["monthly_mip"] + df["operating_expenses"]
            
            # Cash flows
            df["monthly_cash_flow_y1"] = df["net_rent_y1"] - df["total_monthly_cost"]
            df["monthly_cash_flow_y2"] = df["total_rent"] - df["total_monthly_cost"]
            
            # Investment metrics
            df["monthly_NOI"] = df["total_rent"] - df["operating_expenses"]
            df["cap_rate_y2"] = (df["monthly_NOI"] * 12) / df["purchase_price"]
            df["CoC_y2"] = (df["monthly_cash_flow_y2"] * 12) / df["cash_needed"]
            df["GRM_y2"] = df["purchase_price"] / (df["total_rent"] * 12)
            df["MGR_PP"] = df["total_rent"] / df["purchase_price"]
            df["OpEx_Rent"] = df["operating_expenses"] / df["total_rent"]
            df["DSCR"] = df["total_rent"] / df["monthly_mortgage"]
            df["deal_score"] = df.apply(deal_score_property, axis=1)
            df["mobility_score"] = df.apply(mobility_score, axis=1)
        
        return df
    
    def create_properties_table(self) -> str:
        """Create a formatted table view of properties"""
        if self.properties_df.empty:
            return "[bold red]No properties data available[/bold red]"
        
        df = self.properties_df.copy()
        
        # Select key columns for the table view
        display_columns = [
            'address1', 'purchase_price', 'total_rent', 'monthly_cash_flow_y2', 
            'CoC_y2', 'cap_rate_y2', 'deal_score', 'mobility_score'
        ]
        
        # Filter to only available columns
        available_columns = [col for col in display_columns if col in df.columns]
        table_df = df[available_columns].copy()
        
        # Format the data for display
        if 'purchase_price' in table_df.columns:
            table_df['purchase_price'] = table_df['purchase_price'].apply(format_currency)
        if 'total_rent' in table_df.columns:
            table_df['total_rent'] = table_df['total_rent'].apply(format_currency)
        if 'monthly_cash_flow_y2' in table_df.columns:
            table_df['monthly_cash_flow_y2'] = table_df['monthly_cash_flow_y2'].apply(format_currency)
        if 'CoC_y2' in table_df.columns:
            table_df['CoC_y2'] = table_df['CoC_y2'].apply(format_percentage)
        if 'cap_rate_y2' in table_df.columns:
            table_df['cap_rate_y2'] = table_df['cap_rate_y2'].apply(format_percentage)
        if 'deal_score' in table_df.columns:
            table_df['deal_score'] = table_df['deal_score'].apply(format_number)
        if 'mobility_score' in table_df.columns:
            table_df['mobility_score'] = table_df['mobility_score'].apply(format_number)
        
        # Create header
        header = "[bold green]Property Investment Analysis[/bold green]\n"
        header += f"[dim]Showing {len(table_df)} properties | Last updated: {self.last_updated.strftime('%H:%M:%S')}[/dim]\n\n"
        
        # Create table rows
        table_content = header
        
        # Column headers
        if available_columns:
            # Format column names for display
            display_names = {
                'address1': 'Address',
                'purchase_price': 'Price',
                'total_rent': 'Rent',
                'monthly_cash_flow_y2': 'Cash Flow',
                'CoC_y2': 'CoC Return',
                'cap_rate_y2': 'Cap Rate',
                'deal_score': 'Deal Score',
                'mobility_score': 'Mobility'
            }
            
            headers = [display_names.get(col, col) for col in available_columns]
            table_content += " | ".join(f"[bold cyan]{h:>12}[/bold cyan]" for h in headers) + "\n"
            table_content += "-" * (15 * len(headers) + (len(headers) - 1) * 3) + "\n"
            
            # Add data rows with color coding
            for _, row in table_df.head(10).iterrows():  # Limit to first 10 rows for display
                formatted_row = []
                for col in available_columns:
                    value = str(row[col])
                    
                    # Color code based on performance metrics
                    if col == 'monthly_cash_flow_y2' and 'monthly_cash_flow_y2' in df.columns:
                        original_value = df.loc[row.name, col] if row.name in df.index else 0
                        if original_value > 400:
                            value = f"[green]{value}[/green]"
                        elif original_value > 0:
                            value = f"[yellow]{value}[/yellow]"
                        else:
                            value = f"[red]{value}[/red]"
                    elif col == 'deal_score' and 'deal_score' in df.columns:
                        original_value = df.loc[row.name, col] if row.name in df.index else 0
                        if original_value >= 15:
                            value = f"[green]{value}[/green]"
                        elif original_value >= 10:
                            value = f"[yellow]{value}[/yellow]"
                        else:
                            value = f"[red]{value}[/red]"
                    elif col == 'CoC_y2' and 'CoC_y2' in df.columns:
                        original_value = df.loc[row.name, col] if row.name in df.index else 0
                        if original_value > 0.12:
                            value = f"[green]{value}[/green]"
                        elif original_value > 0.08:
                            value = f"[yellow]{value}[/yellow]"
                        else:
                            value = f"[red]{value}[/red]"
                    
                    formatted_row.append(f"{value:>12}")
                
                table_content += " | ".join(formatted_row) + "\n"
            
            if len(table_df) > 10:
                table_content += f"\n[dim]... and {len(table_df) - 10} more properties[/dim]\n"
        
        table_content += "\n[bold]Legend:[/bold] [green]Good[/green] | [yellow]Fair[/yellow] | [red]Poor[/red]"
        table_content += "\n[dim]Press [bold]2[/bold] to search for a specific property[/dim]"
        
        return table_content
    
    def create_property_details(self, property_index: int) -> str:
        """Create detailed analysis view for a specific property"""
        if self.properties_df.empty or property_index >= len(self.properties_df):
            return "[bold red]Property not found[/bold red]"
        
        prop = self.properties_df.iloc[property_index]
        
        # Property header
        details = "[bold green]Property Analysis Report[/bold green]\n"
        details += f"[bold cyan]{prop.get('address1', 'Unknown Address')}[/bold cyan]\n"
        details += f"[dim]Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n\n"
        
        # Basic Property Information
        details += "[bold yellow]🏠 Property Information[/bold yellow]\n"
        details += f"Purchase Price: {format_currency(prop.get('purchase_price', 0))}\n"
        details += f"Square Feet: {prop.get('square_ft', 'N/A'):,}\n"
        details += f"Year Built: {prop.get('built_in', 'N/A')}\n"
        details += f"Home Age: {prop.get('home_age', 'N/A')} years\n"
        details += f"Cost per Sq Ft: {format_currency(prop.get('cost_per_sqrft', 0))}\n\n"
        
        # Financial Summary
        details += "[bold yellow]💰 Financial Summary[/bold yellow]\n"
        details += f"Down Payment: {format_currency(prop.get('down_payment', 0))}\n"
        details += f"Loan Amount: {format_currency(prop.get('loan_amount', 0))}\n"
        details += f"Closing Costs: {format_currency(prop.get('closing_costs', 0))}\n"
        details += f"Cash Needed: {format_currency(prop.get('cash_needed', 0))}\n\n"
        
        # Monthly Cash Flow Analysis
        if 'total_rent' in prop and not pd.isna(prop['total_rent']):
            details += "[bold yellow]📊 Monthly Cash Flow Analysis[/bold yellow]\n"
            details += f"Total Monthly Rent: {format_currency(prop.get('total_rent', 0))}\n"
            details += f"Monthly Mortgage: {format_currency(prop.get('monthly_mortgage', 0))}\n"
            details += f"Monthly Taxes: {format_currency(prop.get('monthly_taxes', 0))}\n"
            details += f"Monthly Insurance: {format_currency(prop.get('monthly_insurance', 0))}\n"
            details += f"Monthly MIP: {format_currency(prop.get('monthly_mip', 0))}\n"
            details += f"Operating Expenses: {format_currency(prop.get('operating_expenses', 0))}\n"
            details += "─" * 40 + "\n"
            
            # Cash flows with color coding
            cf_y1 = prop.get('monthly_cash_flow_y1', 0)
            cf_y2 = prop.get('monthly_cash_flow_y2', 0)
            
            cf_y1_color = "green" if cf_y1 > 0 else "red"
            cf_y2_color = "green" if cf_y2 > 400 else "yellow" if cf_y2 > 0 else "red"
            
            details += f"Cash Flow Year 1: [{cf_y1_color}]{format_currency(cf_y1)}[/{cf_y1_color}]\n"
            details += f"Cash Flow Year 2: [{cf_y2_color}]{format_currency(cf_y2)}[/{cf_y2_color}]\n\n"
        
        # Investment Metrics
        details += "[bold yellow]📈 Investment Metrics[/bold yellow]\n"
        
        # Color code metrics based on performance
        cap_rate = prop.get('cap_rate_y2', 0)
        cap_color = "green" if cap_rate > 0.06 else "yellow" if cap_rate > 0.04 else "red"
        
        coc_return = prop.get('CoC_y2', 0)
        coc_color = "green" if coc_return > 0.12 else "yellow" if coc_return > 0.08 else "red"
        
        details += f"Cap Rate: [{cap_color}]{format_percentage(cap_rate)}[/{cap_color}]\n"
        details += f"Cash-on-Cash Return: [{coc_color}]{format_percentage(coc_return)}[/{coc_color}]\n"
        details += f"Gross Rent Multiplier: {format_number(prop.get('GRM_y2', 0))}\n"
        details += f"Monthly Gross Rent %: {format_percentage(prop.get('MGR_PP', 0))}\n"
        details += f"Operating Expense Ratio: {format_percentage(prop.get('OpEx_Rent', 0))}\n"
        details += f"Debt Service Coverage: {format_number(prop.get('DSCR', 0))}\n\n"
        
        # Scoring
        deal_score = prop.get('deal_score', 0)
        mobility_score = prop.get('mobility_score', 0)
        
        score_color = "green" if deal_score >= 15 else "yellow" if deal_score >= 10 else "red"
        
        details += "[bold yellow]🎯 Property Scores[/bold yellow]\n"
        details += f"Deal Score: [{score_color}]{format_number(deal_score)}/23[/{score_color}]\n"
        details += f"Mobility Score: {format_number(mobility_score)}/100\n\n"
        
        # Performance Rating
        if deal_score >= 15:
            rating = "[bold green]⭐ EXCELLENT DEAL[/bold green]"
        elif deal_score >= 12:
            rating = "[bold yellow]⚡ GOOD DEAL[/bold yellow]"
        elif deal_score >= 8:
            rating = "[bold orange]⚠️  FAIR DEAL[/bold orange]"
        else:
            rating = "[bold red]❌ POOR DEAL[/bold red]"
        
        details += f"[bold yellow]📊 Overall Rating[/bold yellow]\n{rating}\n\n"
        
        # Navigation help
        details += "[dim]Press [bold]1[/bold] to return to all properties | Press [bold]5[/bold] to refresh data[/dim]"
        
        return details
        
    def compose(self) -> ComposeResult:
        """Create the app layout"""
        yield Header()
        yield Container(
            Vertical(
                # Main content area
                Static("Welcome to Property Deal Analyzer!", id="main-content"),
                # Bottom area with main content and compact settings
                Horizontal(
                    Container(
                        Static("Loading...", id="compact-settings"),
                        id="settings-container"
                    ),
                    id="bottom-bar"
                ),
                id="main-area"
            ),
            id="body"
        )
        yield Footer()
    
    def on_mount(self) -> None:
        """Called when app starts"""
        self.title = "Property Deal Analyzer"
        self.sub_title = "Real Estate Investment Analysis Tool"
        
        # Update settings display after widgets are ready
        self.set_timer(0.1, self.update_settings_display)
        
        
        # Start data loading after UI is ready
        self.set_timer(1.0, self.load_all_data)
    
    def update_settings_display(self):
        """Update the compact settings panel with current information"""
        try:
            # Create compact settings display
            compact_widget = self.query_one("#compact-settings", Static)
            loan_data = self.current_loan_data
            assumptions = self.assumptions_data
            
            # Ultra-compact format: everything in 2-3 lines
            compact_info = f"""[bold cyan]{self.current_loan}[/bold cyan] | Rate: {format_percentage(loan_data.get('interest_rate', 0))} | Down: {format_percentage(loan_data.get('down_payment_rate', 0))} | {loan_data.get('loan_length_years', 30)}yr
[bold magenta]Tax: {format_percentage(assumptions.get('property_tax_rate', 0))} | Ins: {format_percentage(assumptions.get('home_insurance_rate', 0))} | Vac: {format_percentage(assumptions.get('vacancy_rate', 0))} | Repair: {format_percentage(assumptions.get('repair_savings_rate', 0))}[/bold magenta]
[dim]Props: {self.properties_count} | Updated: {self.last_updated.strftime('%H:%M:%S')}[/dim]"""
            
            compact_widget.update(compact_info)
            
        except Exception as e:
            # Handle case where widgets aren't ready yet - show debug info in main content
            try:
                main_content = self.query_one("#main-content", Static)
                main_content.update(f"[red]Settings display error: {str(e)}[/red]\n\nTrying to update settings but widget not ready yet...")
            except Exception:
                pass
    
    
    def watch_current_loan(self, old_loan: str, new_loan: str) -> None:
        """React to loan changes"""
        del old_loan, new_loan  # Mark as intentionally unused
        self.update_settings_display()
    
    def watch_properties_count(self, old_count: int, new_count: int) -> None:
        """React to properties count changes"""
        del old_count, new_count  # Mark as intentionally unused
        self.update_settings_display()
    
    def watch_last_updated(self, old_time: datetime, new_time: datetime) -> None:
        """React to last updated time changes"""
        del old_time, new_time  # Mark as intentionally unused
        self.update_settings_display()
    
    def action_show_all_properties(self) -> None:
        """Show all properties view"""
        main_content = self.query_one("#main-content", Static)
        
        if self.properties_df.empty:
            main_content.update("[bold yellow]Loading properties data...[/bold yellow]\n\nPlease wait while we fetch property information.")
            return
            
        # Create properties table
        table_content = self.create_properties_table()
        main_content.update(table_content)
    
    def action_show_property_search(self) -> None:
        """Show single property search"""
        main_content = self.query_one("#main-content", Static)
        
        if self.properties_df.empty:
            main_content.update("[bold yellow]No Properties Available[/bold yellow]\n\nPlease refresh data (press 5) to load properties.")
            return
        
        # Show first property as example, or could implement selection
        property_details = self.create_property_details(0)  # First property
        main_content.update(property_details)
    
    def action_add_property(self) -> None:
        """Add new property"""
        main_content = self.query_one("#main-content", Static)
        main_content.update("[bold yellow]Add New Property[/bold yellow]\n\nProperty addition form will be here...")
    
    def action_manage_loans(self) -> None:
        """Manage loans"""
        main_content = self.query_one("#main-content", Static)
        main_content.update("[bold purple]Loan Management[/bold purple]\n\nLoan management interface will be here...")
    
    def action_refresh_data(self) -> None:
        """Refresh all data"""
        main_content = self.query_one("#main-content", Static)
        main_content.update("[bold cyan]Refreshing Data...[/bold cyan]\n\nLoading latest data from database...")
        
        # Trigger async data reload with timer
        self.set_timer(0.1, self.load_all_data)
        
        # Update last refresh time
        self.last_updated = datetime.now()
    
    def action_show_help(self) -> None:
        """Show help screen"""
        main_content = self.query_one("#main-content", Static)
        help_text = """[bold green]Property Deal Analyzer - Help[/bold green]

[bold]Keyboard Shortcuts:[/bold]
• [cyan]1[/cyan] - All Properties
• [cyan]2[/cyan] - Single Property Search  
• [cyan]3[/cyan] - Add New Property
• [cyan]4[/cyan] - Manage Loans
• [cyan]5[/cyan] - Refresh Data
• [cyan]?[/cyan] - Show This Help
• [cyan]q[/cyan] - Quit Application

[bold]Navigation:[/bold]
Use the number keys to quickly access different sections.
The settings panel on the right shows your current loan and assumptions.

[bold]Features:[/bold]
• Real-time data updates
• Property investment analysis  
• Loan comparison tools
• Phase 1 qualification filters
"""
        main_content.update(help_text)

def main():
    """Entry point for the Textual app"""
    app = PropertyAnalyzerApp()
    app.run()

if __name__ == "__main__":
    main()