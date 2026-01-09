from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Dict, Optional, Any, List

from supabase import Client
from rich.console import Console

import pandas as pd
import questionary
from InquirerPy import inquirer
from rich.panel import Panel

from assumptions import Assumption
from display import (
    display_property_overview_panel,
    display_property_rent_estimates_table,
    display_property_investment_metrics_table,
    display_investment_requirements_panel
)
from helpers import validate_decimal, validate_positive_decimal, validate_percentage, validate_date
from loans import Loan

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

    def _collect_assumption_overrides(self, assumption: Assumption) -> Optional[Dict[str, Any]]:
        """
        Allow user to override specific assumption values.
        Present list of all assumption fields and allow selection until done.
        """
        overrides = {}

        # Create field choices from assumption fields
        field_choices = [
            "appreciation_rate",
            "rent_appreciation_rate",
            "property_tax_rate",
            "home_insurance_rate",
            "vacancy_rate",
            "repair_savings_rate",
            "capex_reserve_rate",
            "closing_costs_rate",
            "discount_rate",
            "federal_tax_rate",
            "selling_costs_rate",
            "longterm_capital_gains_tax_rate",
            "residential_depreciation_period_yrs",
            "land_value_prcnt",
            "utility_electric_base",
            "utility_gas_base",
            "utility_water_base",
            "utility_trash_base",
            "utility_internet_base",
            "utility_baseline_sqft",
            "Done (finish overrides)"
        ]

        while True:
            field = questionary.select(
                "Select field to override (or Done)",
                choices=field_choices
            ).ask()

            if field == "Done (finish overrides)":
                break

            # Get current value
            current_value = getattr(assumption, field)

            # Collect new value based on type
            if isinstance(current_value, float):
                new_value_str = questionary.text(
                    f"Override {field} (current: {current_value})",
                    validate=validate_decimal
                ).ask()
                if new_value_str:
                    overrides[field] = float(new_value_str)
            elif isinstance(current_value, int):
                new_value_str = questionary.text(
                    f"Override {field} (current: {current_value})",
                    validate=lambda x: x.isdigit()
                ).ask()
                if new_value_str:
                    overrides[field] = int(new_value_str)
            elif isinstance(current_value, bool):
                overrides[field] = questionary.confirm(
                    f"Override {field} (current: {current_value})"
                ).ask()
            else:  # string
                new_value = questionary.text(
                    f"Override {field} (current: {current_value})"
                ).ask()
                if new_value:
                    overrides[field] = new_value

            # Remove from choices so we don't override twice
            field_choices.remove(field)

        return overrides if overrides else None

    def _collect_renovation_scope(self) -> Dict[str, bool]:
        """
        Collect renovation scope using multi-select checkboxes.
        Returns dict of renovation categories.
        """
        renovation_categories = [
            "cosmetic_only",
            "hvac",
            "plumbing",
            "electrical",
            "roof",
            "foundation",
            "major_structural_repairs",
            "kitchen_updates",
            "bathroom_updates",
            "full_gut_renovation"
        ]

        # Use inquirer.checkbox for multi-select
        selected_categories = inquirer.checkbox(
            message="Select renovation scope (use space to select, enter to confirm)",
            choices=renovation_categories,
            default=[]
        ).execute()

        # Convert to dict format
        scope = {cat: (cat in selected_categories) for cat in renovation_categories}

        return scope

    def _collect_rent_data(self, num_units: int) -> Dict[str, Any]:
        """
        Collect actual rent data per unit.
        Ask for rent amount for each unit, then which unit is owner-occupied.
        """
        rent_data = {}

        self.console.print(f"[cyan]Collecting rent data for {num_units} units[/cyan]")

        unit_rents = {}
        for i in range(1, num_units + 1):
            rent_str = questionary.text(
                f"Rent for Unit {i} ($/month)",
                validate=validate_decimal
            ).ask()
            unit_rents[f"unit_{i}"] = float(rent_str) if rent_str else 0.0

        # Total rent
        total_rent = sum(unit_rents.values())
        rent_data["unit_rents"] = unit_rents
        rent_data["total_rent"] = total_rent

        # Which unit is owner-occupied?
        has_owner_unit = questionary.confirm(
            "Is one unit owner-occupied?"
        ).ask()

        if has_owner_unit:
            unit_choices = [f"Unit {i}" for i in range(1, num_units + 1)]
            owner_unit = questionary.select(
                "Which unit is owner-occupied?",
                choices=unit_choices
            ).ask()
            rent_data["owner_occupied_unit"] = owner_unit
        else:
            rent_data["owner_occupied_unit"] = None

        return rent_data

    def _collect_additional_income(self) -> Optional[Dict[str, float]]:
        """
        Collect additional income sources.
        """
        income = {}

        income_sources = [
            ("parking_fees", "Parking fees ($/month)"),
            ("laundry_income", "Laundry income ($/month)"),
            ("storage_fees", "Storage unit fees ($/month)"),
            ("pet_fees", "Pet fees ($/month)"),
            ("other", "Other income ($/month)")
        ]

        for key, label in income_sources:
            has_source = questionary.confirm(f"Do you have {label.lower()}?").ask()
            if has_source:
                amount_str = questionary.text(
                    label,
                    validate=validate_decimal
                ).ask()
                income[key] = float(amount_str) if amount_str else 0.0
            else:
                income[key] = 0.0

        return income if any(income.values()) else None

    def _generate_scenario_name(self,
                                property_address: str,
                                loan: Loan,
                                offer_price: Decimal,
                                using_homestyle: bool,
                                renovation_scope: Optional[Dict[str, bool]]) -> str:
        """
        Auto-generate scenario name from key inputs.
        Format: "{Address_Short}_{LoanType}_{Price}k_{Special_Modifier}_{Timestamp}"

        Example: "123MainSt_FHA_250k_Homestyle_0108"
        """
        # Shorten address (first part before comma/space)
        address_short = property_address.split(',')[0].replace(' ', '')[:15]

        # Loan type abbreviation
        loan_type_short = loan.name[:10]

        # Price in thousands
        price_k = int(offer_price / 1000)

        # Special modifiers
        modifiers = []
        if using_homestyle:
            # Check if full gut or major renovation
            if renovation_scope and renovation_scope.get("full_gut_renovation"):
                modifiers.append("FullGut")
            elif renovation_scope and renovation_scope.get("major_structural_repairs"):
                modifiers.append("MajorReno")
            else:
                modifiers.append("Homestyle")

        # Combine
        parts = [address_short, loan_type_short, f"{price_k}k"]
        if modifiers:
            parts.extend(modifiers)

        scenario_name = "_".join(parts)

        # Add timestamp to ensure uniqueness
        timestamp = datetime.now().strftime("%m%d")
        scenario_name = f"{scenario_name}_{timestamp}"

        return scenario_name

    def collect_deal_details(
        self,
        df: pd.DataFrame,
        rents: pd.DataFrame,
        loan: dict,
        assumptions: dict
    ) -> Optional[Deal]:
        """
        Collect all deal details from user input through interactive prompts.

        Displays comprehensive property analysis after property selection to help
        user make informed decisions about deal parameters.

        Args:
            df: DataFrame with all properties and calculated metrics
            rents: DataFrame with rent estimates per unit/room
            loan: Dict with current session loan parameters
            assumptions: Dict with investment assumptions

        Returns:
            Deal object if successful, None if user cancels or error occurs.
        """
        try:
            from loans import LoansProvider
            from assumptions import AssumptionsProvider

            # Initialize providers
            loans_provider = LoansProvider(self.supabase, self.console)
            assumptions_provider = AssumptionsProvider(self.supabase, self.console)

            self.console.print("[cyan]Creating new deal scenario...[/cyan]\n")

            # 1. PROPERTY SELECTION (inquirer.fuzzy)
            properties_response = self.supabase.table("properties").select("address1, units").limit(10000).execute()
            if not properties_response.data:
                self.console.print("[red]No properties found[/red]")
                return None

            property_choices = [row["address1"] for row in properties_response.data]
            property_address = inquirer.fuzzy(
                message="Type to search properties",
                choices=property_choices,
                default="",
                multiselect=False,
                validate=None,
                invalid_message="Invalid input",
            ).execute()

            if property_address is None:
                self.console.print("[yellow]Deal creation cancelled[/yellow]")
                return None

            # Get property info for later use
            selected_property = next(p for p in properties_response.data if p["address1"] == property_address)
            num_units = selected_property.get("units", 0)

            # Display comprehensive property analysis
            try:
                # Lookup full property row in DataFrame
                row = df[df["address1"] == property_address].iloc[0]

                # Get rent estimates for this property
                property_rents = rents[rents["address1"] == property_address]

                # Determine property type
                is_single_family = int(row["units"]) == 0

                # Check if rent data exists
                if property_rents.empty:
                    self.console.print(
                        "\n[yellow]⚠ Warning: No rent estimates found for this property.[/yellow]"
                    )
                    self.console.print(
                        "[dim]Some analysis panels may be incomplete.[/dim]\n"
                    )

                # Display property analysis panels
                self.console.print("\n[bold cyan]═══ Property Analysis ═══[/bold cyan]\n")

                display_property_overview_panel(self.console, row)

                if not property_rents.empty:
                    display_property_rent_estimates_table(self.console, property_rents, is_single_family)

                display_property_investment_metrics_table(self.console, row, is_single_family)
                display_investment_requirements_panel(self.console, row, assumptions, loan)

                self.console.print("\n[bold cyan]═══════════════════════[/bold cyan]\n")

            except IndexError:
                self.console.print(
                    f"\n[red]Error: Property '{property_address}' not found in DataFrame.[/red]"
                )
                self.console.print(
                    "[yellow]Continuing without property analysis display...[/yellow]\n"
                )
            except Exception as e:
                self.console.print(
                    f"\n[red]Error displaying property analysis: {str(e)}[/red]"
                )
                self.console.print(
                    "[yellow]Continuing without property analysis display...[/yellow]\n"
                )

            # 2. LOAN SELECTION (inquirer.fuzzy)
            loans = loans_provider.get_loans()
            if not loans:
                self.console.print("[red]No loans found[/red]")
                return None

            loan_choices = [f"{loan.name} ({loan.interest_rate*100:.2f}%)" for loan in loans]
            loan_display = inquirer.fuzzy(
                message="Type to search loan types",
                choices=loan_choices,
                default="",
                multiselect=False,
                validate=None,
                invalid_message="Invalid input",
            ).execute()

            if loan_display is None:
                self.console.print("[yellow]Deal creation cancelled[/yellow]")
                return None

            selected_loan = next(l for l in loans if f"{l.name} ({l.interest_rate*100:.2f}%)" == loan_display)

            # 3. ASSUMPTIONS SELECTION (inquirer.fuzzy)
            assumptions = assumptions_provider.get_assumptions()
            if not assumptions:
                self.console.print("[red]No assumption sets found[/red]")
                return None

            assumption_choices = [assumption.description for assumption in assumptions]
            assumption_display = inquirer.fuzzy(
                message="Type to search assumption sets",
                choices=assumption_choices,
                default="",
                multiselect=False,
                validate=None,
                invalid_message="Invalid input",
            ).execute()

            if assumption_display is None:
                self.console.print("[yellow]Deal creation cancelled[/yellow]")
                return None

            selected_assumption = next(a for a in assumptions if a.description == assumption_display)

            # 4. OVERRIDE ASSUMPTIONS?
            override_assumptions = questionary.confirm(
                "Do you want to override any assumptions?",
                default=False
            ).ask()

            assumption_overrides = None
            if override_assumptions:
                assumption_overrides = self._collect_assumption_overrides(selected_assumption)

            # 5. OFFER PRICE (required)
            offer_price_str = questionary.text(
                "Offer price ($)",
                validate=validate_positive_decimal
            ).ask()
            offer_price = Decimal(offer_price_str.replace(",", ""))

            # 6. BUYER CLOSING COSTS PAID BY (enum)
            buyer_closing_costs_paid_by_value = questionary.select(
                "Who pays buyer's closing costs?",
                choices=["buyer", "seller"]
            ).ask()

            # 7. SELLER CLOSING COST PERCENT (conditional)
            seller_closing_cost_percent = None
            if buyer_closing_costs_paid_by_value == "seller":
                seller_pct_str = questionary.text(
                    "Seller closing cost percent (0-3%)",
                    default="",
                    validate=lambda x: x == "" or (validate_percentage(x) and 0 <= float(x) <= 3)
                ).ask()
                if seller_pct_str:
                    seller_closing_cost_percent = Decimal(seller_pct_str) / 100

            # 8. SELLER REPAIR CREDITS
            seller_repair_credits_str = questionary.text(
                "Seller repair credits ($)",
                default="0",
                validate=validate_decimal
            ).ask()
            seller_repair_credits = Decimal(seller_repair_credits_str.replace(",", ""))

            # 9. TACK SELLER COSTS TO PRICE?
            tack_seller_costs_to_price = questionary.confirm(
                "Tack seller's increased closing costs to price?",
                default=False
            ).ask()

            # 10. OTHER CLOSING COSTS
            other_closing_costs_str = questionary.text(
                "Other closing costs ($)",
                default="0",
                validate=validate_decimal
            ).ask()
            other_closing_costs = Decimal(other_closing_costs_str.replace(",", ""))

            # 11. USING HOMESTYLE LOAN?
            using_homestyle_loan = questionary.confirm(
                "Using Homestyle renovation loan?",
                default=False
            ).ask()

            renovation_scope = None
            renovation_budget_override = None
            if using_homestyle_loan:
                renovation_scope = self._collect_renovation_scope()

                has_budget_override = questionary.confirm(
                    "Do you have a specific renovation budget?"
                ).ask()
                if has_budget_override:
                    budget_str = questionary.text(
                        "Renovation budget override ($)",
                        validate=validate_positive_decimal
                    ).ask()
                    renovation_budget_override = Decimal(budget_str.replace(",", ""))

            # 12. INITIAL REPAIRS BUDGET
            initial_repairs_str = questionary.text(
                "Initial repairs budget ($)",
                default="0",
                validate=validate_decimal
            ).ask()
            initial_repairs_budget = Decimal(initial_repairs_str.replace(",", ""))

            # 13. USING IOWA 2ND HOME LOAN?
            using_iowa_second_home_loan = questionary.confirm(
                "Using Iowa 2nd Home Loan?",
                default=False
            ).ask()

            # 14. HAS ACTUAL RENT DATA?
            has_actual_rent_data = questionary.confirm(
                "Do you have actual rent data for this property?",
                default=False
            ).ask()

            rent_data = None
            if has_actual_rent_data:
                if num_units and num_units > 0:
                    rent_data = self._collect_rent_data(num_units)
                else:
                    self.console.print("[yellow]Cannot collect rent data: property units not available[/yellow]")

            # 15. ADDITIONAL INCOME?
            has_additional_income = questionary.confirm(
                "Does this property generate additional income?",
                default=False
            ).ask()

            additional_income = None
            if has_additional_income:
                additional_income = self._collect_additional_income()

            # 16. UTILITIES PAID BY (enum)
            utilities_paid_by_value = questionary.select(
                "Who pays utilities?",
                choices=["owner", "tenant", "split"]
            ).ask()

            # 17. PROPERTY MANAGEMENT TYPE (enum)
            property_management_type_value = questionary.select(
                "Property management approach",
                choices=["self-managed", "property-manager", "hybrid"]
            ).ask()

            # 18. CLOSING DATE
            closing_date_str = questionary.text(
                "Closing date (YYYY-MM-DD)",
                default="",
                validate=validate_date
            ).ask()
            closing_date = date.fromisoformat(closing_date_str) if closing_date_str else None

            # 19. OFFER DATE
            offer_date_str = questionary.text(
                "Offer date (YYYY-MM-DD)",
                default="",
                validate=validate_date
            ).ask()
            offer_date = date.fromisoformat(offer_date_str) if offer_date_str else None

            # 20. Calculate days_to_close
            days_to_close = None
            if offer_date and closing_date:
                days_to_close = (closing_date - offer_date).days

            # 21. RENT-UP PERIOD DAYS
            rent_up_period_str = questionary.text(
                "Rent-up period (days between closing and first rent)",
                default="0",
                validate=lambda x: x.isdigit()
            ).ask()
            rent_up_period_days = int(rent_up_period_str)

            # 22. APPEAL PROPERTY TAX?
            appeal_property_tax = questionary.confirm(
                "Plan to appeal property tax assessment?",
                default=False
            ).ask()

            # 23. INSURANCE DEDUCTIBLE + PREMIUM (optional)
            has_insurance_info = questionary.confirm(
                "Do you have insurance deductible/premium information?",
                default=False
            ).ask()

            insurance_deductible = None
            insurance_premium = None
            if has_insurance_info:
                deductible_str = questionary.text(
                    "Insurance deductible ($)",
                    default="",
                    validate=validate_decimal
                ).ask()
                if deductible_str:
                    insurance_deductible = Decimal(deductible_str.replace(",", ""))

                premium_str = questionary.text(
                    "Insurance premium ($/month)",
                    default="",
                    validate=validate_decimal
                ).ask()
                if premium_str:
                    insurance_premium = Decimal(premium_str.replace(",", ""))

            # 24. NOTES (optional)
            notes = questionary.text(
                "Additional notes (optional)",
                default=""
            ).ask()

            # 25. AUTO-GENERATE SCENARIO NAME
            scenario_name = self._generate_scenario_name(
                property_address,
                selected_loan,
                offer_price,
                using_homestyle_loan,
                renovation_scope
            )

            # 26. CREATE DEAL OBJECT
            deal = Deal(
                name=property_address,
                address1=property_address,
                scenario_name=scenario_name,
                offer_price=offer_price,
                loan_id=selected_loan.id,
                assumption_set_id=selected_assumption.id,
                offer_date=offer_date,
                closing_date=closing_date,
                days_to_close=days_to_close,
                override_assumptions=override_assumptions,
                assumption_overrides=assumption_overrides,
                buyer_closing_costs_paid_by=BuyerClosingCostsPaidBy(buyer_closing_costs_paid_by_value),
                seller_closing_cost_percent=seller_closing_cost_percent,
                seller_repair_credits=seller_repair_credits,
                tack_seller_costs_to_price=tack_seller_costs_to_price,
                other_closing_costs=other_closing_costs,
                using_homestyle_loan=using_homestyle_loan,
                renovation_budget_override=renovation_budget_override,
                renovation_scope=renovation_scope,
                initial_repairs_budget=initial_repairs_budget,
                using_iowa_second_home_loan=using_iowa_second_home_loan,
                has_actual_rent_data=has_actual_rent_data,
                rent_data=rent_data,
                additional_income=additional_income,
                utilities_paid_by=UtilitiesPaidBy(utilities_paid_by_value),
                property_management_type=PropertyManagementType(property_management_type_value),
                appeal_property_tax=appeal_property_tax,
                insurance_deductible=insurance_deductible,
                insurance_premium=insurance_premium,
                rent_up_period_days=rent_up_period_days,
                notes=notes if notes else None
            )

            return deal

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Deal creation cancelled by user[/yellow]")
            return None
        except Exception as e:
            self.console.print(f"[red]Unexpected error collecting deal details: {str(e)}[/red]")
            import traceback
            traceback.print_exc()
            return None

    def _display_deal_review_panel(self, deal: Deal):
        """
        Display formatted deal summary for review before saving.
        """
        # Build formatted text
        text = f"[bold cyan]Deal Summary[/bold cyan]\n\n"
        text += f"[yellow]Scenario Name:[/yellow] {deal.scenario_name}\n"
        text += f"[yellow]Property:[/yellow] {deal.address1}\n"
        text += f"[yellow]Offer Price:[/yellow] ${deal.offer_price:,.2f}\n"
        text += f"[yellow]Loan ID:[/yellow] {deal.loan_id}\n"
        text += f"[yellow]Assumption Set ID:[/yellow] {deal.assumption_set_id}\n"
        text += f"[yellow]Offer Date:[/yellow] {deal.offer_date}\n"
        text += f"[yellow]Closing Date:[/yellow] {deal.closing_date}\n"
        text += f"[yellow]Days to Close:[/yellow] {deal.days_to_close}\n\n"

        text += f"[bold]Closing Costs:[/bold]\n"
        text += f"  Paid By: {deal.buyer_closing_costs_paid_by.value if deal.buyer_closing_costs_paid_by else 'N/A'}\n"
        if deal.seller_closing_cost_percent:
            text += f"  Seller Percent: {deal.seller_closing_cost_percent*100:.1f}%\n"
        text += f"  Seller Repair Credits: ${deal.seller_repair_credits:,.2f}\n"
        text += f"  Other Costs: ${deal.other_closing_costs:,.2f}\n\n"

        text += f"[bold]Financing:[/bold]\n"
        text += f"  Homestyle Loan: {deal.using_homestyle_loan}\n"
        text += f"  Iowa 2nd Home Loan: {deal.using_iowa_second_home_loan}\n"
        if deal.renovation_budget_override:
            text += f"  Renovation Budget: ${deal.renovation_budget_override:,.2f}\n"
        text += f"  Initial Repairs: ${deal.initial_repairs_budget:,.2f}\n\n"

        text += f"[bold]Property Management:[/bold]\n"
        text += f"  Type: {deal.property_management_type.value if deal.property_management_type else 'N/A'}\n"
        text += f"  Utilities Paid By: {deal.utilities_paid_by.value if deal.utilities_paid_by else 'N/A'}\n"
        text += f"  Rent-Up Period: {deal.rent_up_period_days} days\n\n"

        if deal.assumption_overrides:
            text += f"[bold]Assumption Overrides:[/bold]\n"
            for key, value in deal.assumption_overrides.items():
                text += f"  {key}: {value}\n"
            text += "\n"

        if deal.notes:
            text += f"[bold]Notes:[/bold]\n{deal.notes}\n"

        self.console.print(Panel(text, title="Deal Review", title_align="left", padding=1))

    def add_deal(self, deal: Deal) -> bool:
        """
        Display deal summary, confirm with user, then save to database.
        Returns True if successful, False otherwise.
        """
        try:
            # Display review panel
            self._display_deal_review_panel(deal)

            # Confirm before saving
            confirm = questionary.confirm(
                "Save this deal to database?"
            ).ask()

            if not confirm:
                self.console.print("[yellow]Deal not saved[/yellow]")
                return False

            # Prepare dict for database (exclude auto-generated fields, convert types)
            deal_dict = {
                "name": deal.name,
                "address1": deal.address1,
                "scenario_name": deal.scenario_name,
                "offer_price": float(deal.offer_price),
                "loan_id": deal.loan_id,
                "assumption_set_id": deal.assumption_set_id,
                "offer_date": deal.offer_date.isoformat() if deal.offer_date else None,
                "closing_date": deal.closing_date.isoformat() if deal.closing_date else None,
                "days_to_close": deal.days_to_close,
                "override_assumptions": deal.override_assumptions,
                "assumption_overrides": deal.assumption_overrides,
                "buyer_closing_costs_paid_by": deal.buyer_closing_costs_paid_by.value if deal.buyer_closing_costs_paid_by else None,
                "seller_closing_cost_percent": float(deal.seller_closing_cost_percent) if deal.seller_closing_cost_percent else None,
                "seller_repair_credits": float(deal.seller_repair_credits),
                "tack_seller_costs_to_price": deal.tack_seller_costs_to_price,
                "other_closing_costs": float(deal.other_closing_costs),
                "using_homestyle_loan": deal.using_homestyle_loan,
                "renovation_budget_override": float(deal.renovation_budget_override) if deal.renovation_budget_override else None,
                "renovation_scope": deal.renovation_scope,
                "initial_repairs_budget": float(deal.initial_repairs_budget),
                "using_iowa_second_home_loan": deal.using_iowa_second_home_loan,
                "has_actual_rent_data": deal.has_actual_rent_data,
                "rent_data": deal.rent_data,
                "additional_income": deal.additional_income,
                "utilities_paid_by": deal.utilities_paid_by.value if deal.utilities_paid_by else None,
                "property_management_type": deal.property_management_type.value if deal.property_management_type else None,
                "property_management_percent": float(deal.property_management_percent) if deal.property_management_percent else None,
                "appeal_property_tax": deal.appeal_property_tax,
                "insurance_deductible": float(deal.insurance_deductible) if deal.insurance_deductible else None,
                "insurance_premium": float(deal.insurance_premium) if deal.insurance_premium else None,
                "rent_up_period_days": deal.rent_up_period_days,
                "notes": deal.notes
            }

            # Insert into database
            response = self.supabase.table("deals").insert(deal_dict).execute()

            if hasattr(response, "data") and response.data:
                self.console.print(
                    f"[green]Deal '{deal.scenario_name}' saved successfully![/green]"
                )
                return True
            else:
                self.console.print("[red]Failed to save deal - no data returned[/red]")
                return False

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Save cancelled by user[/yellow]")
            return False
        except Exception as e:
            self.console.print(f"[red]Error saving deal: {str(e)}[/red]")
            import traceback
            traceback.print_exc()
            return False

    def extend_deals_df_with_data(
        self,
        properties_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Create deal-centric DataFrame with loan, assumption, and property data attached.

        Fetches all deals, loans, and assumptions, converts each to DataFrame, and merges
        with properties_df. Each row represents a deal with full context from all related
        data sources.

        Merge keys:
        - Loans: Merged on loan_id (deals.loan_id = loans.id)
        - Assumptions: Merged on assumption_set_id (deals.assumption_set_id = assumptions.id)
        - Properties: Merged on address1 (deals.address1 = properties.address1)

        Column naming:
        - Deal columns: No prefix (e.g., scenario_name, offer_price)
        - Loan columns: "loan_" prefix (e.g., loan_name, loan_interest_rate)
        - Assumption columns: "assumption_" prefix (e.g., assumption_description, assumption_appreciation_rate)
        - Property columns: "prop_" prefix (e.g., prop_list_price, prop_sqft)

        Dict columns (assumption_overrides, renovation_scope, rent_data, additional_income)
        are preserved as dict objects in the DataFrame.

        Args:
            properties_df: Properties DataFrame with address1 column

        Returns:
            Deal-centric DataFrame with loan, assumption, and property columns.
            Returns empty DataFrame if no deals found or on error.

        Example:
            # Load properties
            df = reload_dataframe()

            # Create comprehensive deal view
            deal_maker = DealMakerProvider(supabase, console)
            deals_df = deal_maker.extend_deals_df_with_data(df)

            # Access data from all sources
            deals_df["scenario_name"]                    # Deal column
            deals_df["loan_name"]                        # Loan column
            deals_df["loan_interest_rate"]               # Loan column
            deals_df["assumption_description"]           # Assumption column
            deals_df["assumption_appreciation_rate"]     # Assumption column
            deals_df["prop_list_price"]                  # Property column

            # Compare scenarios for same property
            same_property = deals_df[deals_df["address1"] == "123 Main St"]
            print(same_property[["scenario_name", "offer_price", "loan_name", "prop_list_price"]])

            # Access dict columns
            deals_df["renovation_scope"].apply(lambda x: x.get("hvac") if isinstance(x, dict) else None)
        """
        try:
            # Step 1: Fetch deals
            deals = self.get_deals()
            if not deals or len(deals) == 0:
                self.console.print("[yellow]No deals found, returning empty DataFrame[/yellow]")
                return pd.DataFrame()

            # Step 1b: Fetch loans
            from loans import LoansProvider
            loans_provider = LoansProvider(self.supabase, self.console)
            loans = loans_provider.get_loans()

            # Step 1c: Fetch assumptions
            from assumptions import AssumptionsProvider
            assumptions_provider = AssumptionsProvider(self.supabase, self.console)
            assumptions = assumptions_provider.get_assumptions()

            # Step 2: Convert Deal objects to DataFrame
            deals_data = []
            for deal in deals:
                deal_dict = {
                    # Core identifiers
                    "id": deal.id,
                    "address1": deal.address1,
                    "scenario_name": deal.scenario_name,
                    "loan_id": deal.loan_id,
                    "assumption_set_id": deal.assumption_set_id,

                    # Financial fields - convert Decimal to float
                    "offer_price": float(deal.offer_price) if deal.offer_price else None,
                    "seller_closing_cost_percent": float(deal.seller_closing_cost_percent) if deal.seller_closing_cost_percent else None,
                    "seller_repair_credits": float(deal.seller_repair_credits) if deal.seller_repair_credits else None,
                    "other_closing_costs": float(deal.other_closing_costs) if deal.other_closing_costs else None,
                    "renovation_budget_override": float(deal.renovation_budget_override) if deal.renovation_budget_override else None,
                    "initial_repairs_budget": float(deal.initial_repairs_budget) if deal.initial_repairs_budget else None,
                    "insurance_deductible": float(deal.insurance_deductible) if deal.insurance_deductible else None,
                    "insurance_premium": float(deal.insurance_premium) if deal.insurance_premium else None,
                    "property_management_percent": float(deal.property_management_percent) if deal.property_management_percent else None,

                    # Enum fields - extract .value
                    "buyer_closing_costs_paid_by": deal.buyer_closing_costs_paid_by.value if deal.buyer_closing_costs_paid_by else None,
                    "utilities_paid_by": deal.utilities_paid_by.value if deal.utilities_paid_by else None,
                    "property_management_type": deal.property_management_type.value if deal.property_management_type else None,

                    # Boolean flags
                    "override_assumptions": deal.override_assumptions,
                    "tack_seller_costs_to_price": deal.tack_seller_costs_to_price,
                    "using_homestyle_loan": deal.using_homestyle_loan,
                    "using_iowa_second_home_loan": deal.using_iowa_second_home_loan,
                    "has_actual_rent_data": deal.has_actual_rent_data,
                    "appeal_property_tax": deal.appeal_property_tax,

                    # Integer fields
                    "rent_up_period_days": deal.rent_up_period_days,
                    "days_to_close": deal.days_to_close,

                    # Date/DateTime fields
                    "offer_date": deal.offer_date,
                    "closing_date": deal.closing_date,
                    "created_at": deal.created_at,
                    "updated_at": deal.updated_at,

                    # Dict fields - keep as dicts
                    "assumption_overrides": deal.assumption_overrides,
                    "renovation_scope": deal.renovation_scope,
                    "rent_data": deal.rent_data,
                    "additional_income": deal.additional_income,

                    # Optional text fields
                    "notes": deal.notes,
                    "created_by": deal.created_by,
                }
                deals_data.append(deal_dict)

            # Create DataFrame
            deals_df = pd.DataFrame(deals_data)
            self.console.print(f"[cyan]Converted {len(deals_df)} deals to DataFrame[/cyan]")

            # Step 2b: Convert loans to DataFrame and merge
            if loans and len(loans) > 0:
                loans_data = []
                for loan in loans:
                    loan_dict = asdict(loan)
                    loans_data.append(loan_dict)

                loans_df = pd.DataFrame(loans_data)

                # Rename 'id' to 'loan_id' for merging
                loans_df = loans_df.rename(columns={'id': 'loan_id'})

                # Prefix all loan columns except loan_id with "loan_"
                loan_rename_dict = {
                    col: f"loan_{col}"
                    for col in loans_df.columns
                    if col != "loan_id"
                }
                loans_df = loans_df.rename(columns=loan_rename_dict)

                self.console.print(f"[cyan]Converted {len(loans_df)} loans to DataFrame[/cyan]")

                # Merge loans with deals
                extended_deals_df = deals_df.merge(
                    loans_df,
                    on="loan_id",
                    how="left"
                )

                # Report merge results
                deals_with_loans = extended_deals_df["loan_name"].notna().sum()
                deals_without_loans = len(extended_deals_df) - deals_with_loans

                self.console.print(f"[cyan]  - {deals_with_loans} deals matched to loans[/cyan]")
                if deals_without_loans > 0:
                    self.console.print(f"[yellow]  - {deals_without_loans} deals without matching loan data[/yellow]")
            else:
                self.console.print("[yellow]No loans found in database[/yellow]")
                extended_deals_df = deals_df.copy()

            # Step 2c: Convert assumptions to DataFrame and merge
            if assumptions and len(assumptions) > 0:
                assumptions_data = []
                for assumption in assumptions:
                    assumption_dict = asdict(assumption)
                    assumptions_data.append(assumption_dict)

                assumptions_df = pd.DataFrame(assumptions_data)

                # Rename 'id' to 'assumption_set_id' for merging
                assumptions_df = assumptions_df.rename(columns={'id': 'assumption_set_id'})

                # Prefix all assumption columns except assumption_set_id with "assumption_"
                assumption_rename_dict = {
                    col: f"assumption_{col}"
                    for col in assumptions_df.columns
                    if col != "assumption_set_id"
                }
                assumptions_df = assumptions_df.rename(columns=assumption_rename_dict)

                self.console.print(f"[cyan]Converted {len(assumptions_df)} assumptions to DataFrame[/cyan]")

                # Merge assumptions with deals
                extended_deals_df = extended_deals_df.merge(
                    assumptions_df,
                    on="assumption_set_id",
                    how="left"
                )

                # Report merge results
                deals_with_assumptions = extended_deals_df["assumption_description"].notna().sum()
                deals_without_assumptions = len(extended_deals_df) - deals_with_assumptions

                self.console.print(f"[cyan]  - {deals_with_assumptions} deals matched to assumptions[/cyan]")
                if deals_without_assumptions > 0:
                    self.console.print(f"[yellow]  - {deals_without_assumptions} deals without matching assumption data[/yellow]")
            else:
                self.console.print("[yellow]No assumptions found in database[/yellow]")

            # Step 3: Validate properties DataFrame
            if "address1" not in properties_df.columns:
                self.console.print("[red]Error: properties_df must have 'address1' column[/red]")
                return pd.DataFrame()

            if len(properties_df) == 0:
                self.console.print("[yellow]Warning: properties_df is empty[/yellow]")

            # Step 4: Prefix property columns
            properties_df_for_merge = properties_df.copy()
            rename_dict = {
                col: f"prop_{col}"
                for col in properties_df_for_merge.columns
                if col != "address1"
            }
            properties_df_for_merge = properties_df_for_merge.rename(columns=rename_dict)
            self.console.print(f"[cyan]Prepared {len(properties_df_for_merge.columns) - 1} property columns for merge[/cyan]")

            # Step 5: Merge deals with properties
            extended_deals_df = extended_deals_df.merge(
                properties_df_for_merge,
                on="address1",
                how="left"
            )

            # Report results
            deals_with_properties = extended_deals_df["prop_list_price"].notna().sum() if "prop_list_price" in extended_deals_df.columns else 0
            deals_without_properties = len(extended_deals_df) - deals_with_properties

            self.console.print(
                f"[green]Created deal-centric DataFrame: {len(extended_deals_df)} deals total[/green]"
            )
            self.console.print(
                f"[cyan]  - {deals_with_properties} deals matched to properties[/cyan]"
            )
            if deals_without_properties > 0:
                self.console.print(
                    f"[yellow]  - {deals_without_properties} deals without matching property data[/yellow]"
                )

            return extended_deals_df

        except Exception as e:
            self.console.print(f"[red]Error creating deal-centric DataFrame: {str(e)}[/red]")
            import traceback
            traceback.print_exc()
            return pd.DataFrame()

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