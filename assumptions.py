from dataclasses import dataclass
from typing import Optional, List

from supabase import Client
from rich.console import Console

@dataclass
class Assumption:
    id: int
    description: str
    appreciation_rate: float
    rent_appreciation_rate: float
    property_tax_rate: float
    home_insurance_rate: float
    vacancy_rate: float
    repair_savings_rate: float
    capex_reserve_rate: float
    closing_costs_rate: float
    live_in_unit_setting: str
    gross_annual_income: int
    state_tax_code: str
    discount_rate: float
    using_ia_fhb_prog: bool
    ia_fhb_prog_upfront_option: str
    utility_electric_base: float
    utility_gas_base: float
    utility_water_base: float
    utility_trash_base: float
    utility_internet_base: float
    utility_baseline_sqft: int
    land_value_prcnt: float
    federal_tax_rate: float
    selling_costs_rate: float
    longterm_capital_gains_tax_rate: float
    residential_depreciation_period_yrs: float
    default_property_condition_score: int

class AssumptionsProvider:
    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console

    def get_assumptions(self) -> Optional[List[Assumption]]:
        try:
            response = self.supabase.table("assumptions").select("*").limit(10000).execute()
            if not response:
                self.console.print("[red]Assumptions not found[/red]")
                return None
            return [Assumption(**assumption_dict) for assumption_dict in response.data]
        except Exception as e:
            self.console.print(f"[red]Error getting assumptions: {str(e)}[/red]")
            return None

    def get_assumption_by_id(self, id: int) -> Optional[Assumption]:
        try:
            response = (
                self.supabase.table("assumptions")
                .select("*")
                .eq("id", id)
                .limit(1)
                .single()
                .execute()
            )
            if not response:
                self.console.print(f"[red]Assumption set {id} not found[/red]")
                return None
            return Assumption(**response.data)
        except Exception as e:
            self.console.print(f"[red]Error getting assumption set {id}: {str(e)}[/red]")
            return None
