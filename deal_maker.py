from dataclasses import dataclass

from supabase import Client
from rich.console import Console
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Any, List

class BuyerClosingCostsPaidBy(str, Enum):
    BUYER = "buyer"
    SELLER = "seller"

class UtilitiesPaidBy(str, Enum):
    OWNER = "owner"
    TENANT = "tenant"
    SPLIT = "split"

class PropertyManagementType(str, Enum):
    SELF_MANAGED = "self-managed"
    PROPERTY_MANAGER = "property-manager"
    HYBRID = "hybrid"

@dataclass
class Deal:
    id: Optional[int] = None
    name: str = ""
    address1: str = ""
    scenario_name: str = ""
    offer_price: Decimal = Decimal("0")
    loan_id: Optional[int] = None
    assumption_set_id: Optional[int] = None
    offer_date: Optional[date] = None
    closing_date: Optional[date] = None
    days_to_close: Optional[int] = None
    override_assumptions: bool = False
    assumption_overrides: Optional[Dict[str, Any]] = None
    buyer_closing_costs_paid_by: Optional[BuyerClosingCostsPaidBy] = None
    seller_closing_cost_percent: Optional[Decimal] = None  # CHECK BETWEEN 0 AND 3
    seller_repair_credits: Decimal = Decimal("0")
    tack_seller_costs_to_price: bool = False
    other_closing_costs: Decimal = Decimal("0")
    using_homestyle_loan: bool = False
    renovation_budget_override: Optional[Decimal] = None
    renovation_scope: Optional[Dict[str, Any]] = None
    initial_repairs_budget: Decimal = Decimal("0")
    using_iowa_second_home_loan: bool = False
    has_actual_rent_data: bool = False
    rent_data: Optional[Dict[str, Any]] = None
    additional_income: Optional[Dict[str, Any]] = None
    utilities_paid_by: Optional[UtilitiesPaidBy] = None
    property_management_type: Optional[PropertyManagementType] = None
    property_management_percent: Optional[Decimal] = None  # Often auto-calculated
    appeal_property_tax: bool = False
    insurance_deductible: Optional[Decimal] = None
    insurance_premium: Optional[Decimal] = None
    rent_up_period_days: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    notes: Optional[str] = None

class DealMakerProvider:
    def __init__(self, supabase: Client, console: Console):
        self.supabase = supabase
        self.console = console
    
    def get_deals(self) -> Optional[List[Deal]]:
        try:
            response = self.supabase.table("deals").select("*").limit(10000).execute()
            if not response:
                self.console.print("[red]Deals not found[/red]")
                return None
            return [Deal(**loan_dict) for loan_dict in response.data]
        except Exception as e:
            self.console.print(f"[red]Error getting deals: {str(e)}[/red]")
            return None
    
    def get_deal_by_id(self, id) -> Optional[Deal]:
        try:
            response = self.supabase.table("deals").select("*").eq("id", id).limit(1).single().execute()
            if not response:
                self.console.print(f"[red]Deal {id} not found[/red]")
                return None
            return Deal(**response.data)
        except Exception as e:
            self.console.print(f"[red]Error getting deal {id}: {str(e)}[/red]")
            return None
    
    def collect_deal_details(self) -> Loan:
        pass

    def build_deal(properties_df):
        # INPUTS
        # 1. Property Address
        # 2. Loan Type
        # 3. Assumption set
        # 3.1. Do you want to override anything in assumptions? (Y/N) 
        # 3.1.1. If so, we go through a list of all assumptions and ovveride any
        # 4. Price we want to pay
        # 5. Who pays buyers' closing costs (buyer or seller)
        # 6. If seller, what percent (1-3%)
        # 6.1. Do we expect seller credits for repairs (Reduces cash needed, but I suppose it helps with reducing rennovation budget?)
        # 7. Tack on seller's increased closing costs to price (Y/N)
        # 8. Using homestyle renovation loan
        # 8.1. Do we have a specific rennovation budget (ovverides auto-calculated budget for homestyle rennovation)
        # 8.2. Rennovation scope (cosmetic only, HVAC, plumbing, electrical, roof, foundation, major repairs, kitchen/bath updates, full gut rennovation) (this way we can scenario-out different rennovation projects for a property, so store this in JSON in scenarios table)
        # 9. Using Iowa 2nd Home Loan
        # 10. Do we have actual rent data (if so, we it will ask us to input the rent for each unit, then the unit we're living in and all of this data will be stored as a JSON in the scenarios table (e.g. { unit_1: 300, total_rent: 400 })))
        # 11. Does this property generate additional income? (parking fees, coin laundry, storage units, pet fees) (if we say, all of these default to 0)
        # 12. Who pays for utilities (certain multi-family calculations may have owner paying. SFH assumes splitting rent)
        # 13. How will this property be managed (default is self-managed, but if 'property manager' then a 8-10% of rent cost will be applied to OpEx, or 'hybrid' 5% if you find tenants and manager maintains)
        # Any other closing costs?
        # Closing date (can we asked as "Days to Close", homestyle would need 60-75, conventional would need typical 30)
        # Offer date (date we put the offer in on)
        # Rent-Up Period (time between closing date and whne the property gets rented and would affect True Y1 Costs, factor in the first mortgage payment based on closing date)
        # Initial repairs budget (outside of any rennovation work)
        # Plan to appeal property tax assessment?
        # Insurance deductible (auto-generate premium amounts per deductible based on the property in question)

        # AUTO-GENERATED 
        # Scenario Name based on key inputs
        # First mortgage payment (calculated based on Closing Date input)

        pass