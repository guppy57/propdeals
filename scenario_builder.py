from dataclasses import dataclass
from supabase import Client
from rich.console import Console
from InquirerPy import inquirer
import questionary

from helpers import validate_percentage
from dataframe_helpers import (
    apply_calculations_on_dataframe,
    apply_investment_calculations
)

@dataclass
class Scenario:
    id: str
    address1: str
    loan_id: int
    assumption_id: int
    percent_below_asking: float
    seller_closing_credits: int
    seller_credits: int
    rennovation_budget: int
    initial_repair_budget: int
    owner_pays_utilities: bool

class ScenarioBuilderProvider:
    def __init__(self, supabase: Client, console: Console):
        self.supabase = supabase
        self.console = console
    
    def get_scenarios(self):
        try:
            response = self.supabase.table("scenarios").select("*").limit(10000).execute()
            if not response:
                self.console.print("Scenarios not found", style="red")
                return None
            return [Scenario(**scenario_dict) for scenario_dict in response.data]
        except Exception as e:
            self.console.print(f"Error getting scenarios: {str(e)}", style="red")
      
    def add_new_scenario(self, properties_df, loans, assumptions):
        property_choices = list(properties_df["address1"])
        loan_choices = [loan.name for loan in loans]
        assumption_choices = [assumption.description for assumption in assumptions]

        name = questionary.text("Scenario Name").ask()

        address1 = inquirer.fuzzy(
            message="Select a property",
            choices=property_choices,
            default="",
            multiselect=False,
            validate=None,
            invalid_message="Invalid input"
        ).execute()

        if address1 is None:
            self.console.print("Deal creation cancelled...", style="yellow")
            return None
        
        loan_choice = inquirer.fuzzy(
            message="Select a loan",
            choices=loan_choices,
            default="",
            multiselect=False,
            validate=None,
            invalid_message="Invalid input"
        ).execute()

        if loan_choice is None:
            self.console.print("Deal creation cancelled...", style="yellow")
            return None
        
        loan = next(l for l in loans if l.name == loan_choice)

        assumption_choice = inquirer.fuzzy(
            message="Select an assumption",
            choices=assumption_choices,
            default="",
            multiselect=False,
            validate=None,
            invalid_message="Invalid input"
        ).execute()

        if assumption_choice is None:
            self.console.print("Deal creation cancelled...", style="yellow")
            return None
        
        assumption = next(a for a in assumptions if a.description == assumption_choice)

        pba_raw = questionary.text("Percent below asking price", validate=validate_percentage).ask()
        percent_below_asking = float(pba_raw) / 100

        scc_raw = questionary.text("Seller closing credits").ask()
        sc_raw = questionary.text("Any other seller credits").ask()
        rb_raw = questionary.text("Total rennovation budget").ask()
        irb_raw = questionary.text("Initial repairs/rennovation budget for rent-readiness").ask()
        owner_pays_utilities = questionary.confirm("Will the owner pay utilities?").ask()

        new_scenario = {
            "id": name,
            "address1": address1,
            "loan_id": loan.id,
            "assumption_id": assumption.id,
            "percent_below_asking": percent_below_asking,
            "seller_closing_credits": int(scc_raw),
            "seller_credits": int(sc_raw),
            "rennovation_budget": int(rb_raw),
            "initial_repair_budget": int(irb_raw),
            "owner_pays_utilities": owner_pays_utilities
        }

        try:
            response = self.supabase.table("scenarios").insert(new_scenario).execute()
            if hasattr(response, "data"):
                self.console.print(f"Response data: {response.data}", style="green")
                return True
            else:
                self.console.print("Response has no 'data' attribute", style="green")
        except Exception as e:
            self.console.print(f"Exception: {e}", style="bold red")
            self.console.print(f"Exception type: {type(e)}", style="bold red")

        return False

    def get_calculated_scenarios_df(self):
        pass