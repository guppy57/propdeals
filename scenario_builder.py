from dataclasses import dataclass
from typing import Optional
from supabase import Client
from rich.console import Console
from InquirerPy import inquirer
import questionary

from helpers import validate_percentage

@dataclass
class Scenario:
    id: Optional[int] = None
    address1: str
    loan_id: int
    assumption_id: int
    percent_below_asking: float
    seller_pays_cc: bool
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
      
    def collect_scenario_details(self, properties_df, loans, assumptions):
        property_choices = [row["address1"] for row in properties_df]
        loan_choices = [loan.name for loan in loans]
        assumption_choices = [assumption.name for assumption in assumptions]

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
        )

        if loan_choice is None:
            self.console.print("Deal creation cancelled...", style="yellow")
            return None
        
        loan_id = next(l for l in loans if l.name == loan_choice)

        assumption_choice = inquirer.fuzzy(
            message="Select an assumption",
            choices=assumption_choices,
            default="",
            multiselect=False,
            validate=None,
            invalid_message="Invalid input"
        )

        if assumption_choice is None:
            self.console.print("Deal creation cancelled...", style="yellow")
            return None
        
        assumption_id = next(a for a in assumptions if a.name == assumption_choice)

        pba_raw = questionary.text("Percent below asking price", validate=validate_percentage)
        percent_below_asking = float(pba_raw) / 100

      