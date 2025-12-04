import os
import questionary
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import openai
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from supabase import Client

from editor import edit_multiline_text


# Field configuration: maps user-friendly label to (db_field_name, field_type)
FIELD_CONFIG = {
    # County Records
    "Obtained county records": ("obtained_county_records", "boolean"),
    "County record notes": ("county_record_notes", "editor"),
    "Historical Turnover Rate": ("historical_turnover_rate", "float"),
    "Average Ownership Duration": ("average_ownership_duration", "float"),

    # Restrictions
    "Has deed restrictions": ("has_deed_restrictions", "boolean"),
    "Has HOA": ("has_hao", "boolean"),
    "Has historic preservation": ("has_historic_preservation", "boolean"),

    # Property Details
    "Setbacks": ("setbacks", "editor"),
    "Has easements": ("has_easements", "boolean"),
    "Easements": ("easements", "editor"),
    "In flood zone": ("in_flood_zone", "boolean"),
    "Year Built": ("built_in", "integer"),
    "Zillow Link": ("zillow_link", "text"),
    "Days in Market": ("listed_date", "days_to_date"),

    # Permits
    "Has open/pulled permits": ("has_open_pulled_permits", "boolean"),
    "Has work done without permits": ("has_work_done_wo_permits", "boolean"),
    "Permit notes": ("permit_notes", "editor"),

    # Purchase History
    "Last purchase price": ("last_purchase_price", "float"),
    "Last purchase date": ("last_purchase_date", "date"),

    # Other Notes
    "Whitepages notes": ("whitepages_notes", "editor"),
}


def handle_editor_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle text editor fields"""
    console.print(f"[cyan]Opening editor for {field_label}... (save and quit to continue)[/cyan]")

    try:
        new_value = edit_multiline_text(current_value or "", field_label)
    except Exception as e:
        console.print(f"[red]Error opening editor: {str(e)}[/red]")
        return None

    # Show preview of changes
    console.print("\n" + "="*50)
    console.print("[yellow]BEFORE:[/yellow]")
    console.print(current_value if current_value else "[dim](empty)[/dim]")
    console.print("\n[green]AFTER:[/green]")
    console.print(new_value if new_value else "[dim](empty)[/dim]")
    console.print("="*50 + "\n")

    return new_value if new_value else None


def handle_boolean_field(field_label: str, field_name: str, current_value: bool, console: Console):
    """Handle boolean fields"""
    current_display = "Yes" if current_value else "No" if current_value is False else "Not set"

    new_value = questionary.confirm(
        f"{field_label} (currently: {current_display})",
        default=current_value if current_value is not None else False
    ).ask()

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_display}")
    console.print(f"[green]New:[/green] {'Yes' if new_value else 'No'}\n")

    return new_value


def handle_integer_field(field_label: str, field_name: str, current_value: int, console: Console):
    """Handle integer fields"""
    default_str = str(current_value) if current_value is not None else ""

    new_value_str = questionary.text(
        f"{field_label} (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str,
        validate=lambda x: x == "" or x.isdigit()
    ).ask()

    if new_value_str == "":
        new_value = None
    else:
        new_value = int(new_value_str)

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


def handle_float_field(field_label: str, field_name: str, current_value: float, console: Console):
    """Handle float/double precision fields"""
    default_str = str(current_value) if current_value is not None else ""

    def validate_float(text):
        if text == "":
            return True
        try:
            float(text)
            return True
        except ValueError:
            return False

    new_value_str = questionary.text(
        f"{field_label} (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str,
        validate=validate_float
    ).ask()

    if new_value_str == "":
        new_value = None
    else:
        new_value = float(new_value_str)

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


def handle_date_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle date fields (YYYY-MM-DD format)"""
    default_str = str(current_value) if current_value is not None else ""

    def validate_date(text):
        if text == "":
            return True
        # Basic validation for YYYY-MM-DD format
        parts = text.split('-')
        if len(parts) != 3:
            return False
        try:
            year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
            # Basic range checks
            if not (1900 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31):
                return False
            return True
        except ValueError:
            return False

    new_value_str = questionary.text(
        f"{field_label} (YYYY-MM-DD) (currently: {current_value if current_value is not None else 'Not set'})",
        default=default_str,
        validate=validate_date
    ).ask()

    new_value = new_value_str if new_value_str else None

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value is not None else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value is not None else 'Not set'}\n")

    return new_value


def handle_text_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle single-line text fields"""
    default_str = str(current_value) if current_value is not None else ""

    new_value_str = questionary.text(
        f"{field_label} (currently: {current_value if current_value else 'Not set'})",
        default=default_str
    ).ask()

    new_value = new_value_str if new_value_str else None

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_value if current_value else 'Not set'}")
    console.print(f"[green]New:[/green] {new_value if new_value else 'Not set'}\n")

    return new_value


def handle_days_to_date_field(field_label: str, field_name: str, current_value: str, console: Console):
    """Handle days-to-date conversion fields (accepts days in market, stores as date)"""
    # Calculate current days in market if date exists
    current_days = None
    current_display = "Not set"

    if current_value:
        try:
            # Parse the date string
            if isinstance(current_value, str):
                listed_datetime = datetime.fromisoformat(current_value.replace('Z', '+00:00').split('T')[0])
            else:
                listed_datetime = datetime.fromisoformat(str(current_value))

            # Calculate days in market
            current_days = (datetime.now() - listed_datetime).days
            current_display = f"{current_days} days (listed on {listed_datetime.date()})"
        except (ValueError, AttributeError):
            current_display = f"Invalid date: {current_value}"

    default_str = str(current_days) if current_days is not None else ""

    def validate_integer(text):
        if text == "":
            return True
        return text.isdigit()

    new_value_str = questionary.text(
        f"{field_label} (enter days in market) (currently: {current_display})",
        default=default_str,
        validate=validate_integer
    ).ask()

    if new_value_str == "":
        new_value = None
    else:
        # Convert days to date: today - days_input = listing_date
        days_in_market = int(new_value_str)
        listing_date = date.today() - timedelta(days=days_in_market)
        new_value = listing_date.isoformat()

    # Show preview
    console.print(f"\n[yellow]Current:[/yellow] {current_display}")
    if new_value:
        new_days = int(new_value_str)
        console.print(f"[green]New:[/green] {new_days} days in market (listing date: {new_value})")
    else:
        console.print("[green]New:[/green] Not set")
    console.print()

    return new_value


def edit_property_assessment(property_id: str, supabase_client: Client, console: Console):
    """
    Edit property assessment fields using appropriate input methods.

    Args:
        property_id: The address1 of the property to edit
        supabase_client: Supabase client instance
        console: Rich console instance for formatted output
    """
    while True:
        # Fetch current property data first (so we can show checkmarks)
        try:
            response = supabase_client.table("properties").select("*").eq("address1", property_id).single().execute()
            current_data = response.data
        except Exception as e:
            console.print(f"[red]Error fetching property data: {str(e)}[/red]")
            break

        # Build menu with checkmarks for fields that have values
        display_choices = []
        label_to_field = {}  # Map display label back to actual field label

        for field_label in FIELD_CONFIG.keys():
            field_name, field_type = FIELD_CONFIG[field_label]
            current_value = current_data.get(field_name)

            # Determine if field has a value
            has_value = False
            if current_value is not None:
                # Empty strings count as null
                if isinstance(current_value, str):
                    has_value = bool(current_value.strip())
                else:
                    has_value = True

            # Add checkmark or spacing
            indicator = "✓ " if has_value else "  "
            display_label = f"{indicator}{field_label}"
            display_choices.append(display_label)
            label_to_field[display_label] = field_label

        display_choices.append("Go Back")

        field_choice_display = questionary.select(
            "Which field would you like to edit?",
            choices=display_choices
        ).ask()

        if field_choice_display == "Go Back":
            break

        # Get the actual field label (strip indicator)
        field_choice = label_to_field[field_choice_display]

        # Get field configuration
        field_name, field_type = FIELD_CONFIG[field_choice]
        current_value = current_data.get(field_name)

        # Handle the field based on its type
        new_value = None

        if field_type == "editor":
            new_value = handle_editor_field(field_choice, field_name, current_value, console)
        elif field_type == "boolean":
            new_value = handle_boolean_field(field_choice, field_name, current_value, console)
        elif field_type == "integer":
            new_value = handle_integer_field(field_choice, field_name, current_value, console)
        elif field_type == "float":
            new_value = handle_float_field(field_choice, field_name, current_value, console)
        elif field_type == "date":
            new_value = handle_date_field(field_choice, field_name, current_value, console)
        elif field_type == "text":
            new_value = handle_text_field(field_choice, field_name, current_value, console)
        elif field_type == "days_to_date":
            new_value = handle_days_to_date_field(field_choice, field_name, current_value, console)
        else:
            console.print(f"[red]Unknown field type: {field_type}[/red]")
            continue

        # If handling returned None (e.g., error occurred), skip save
        if new_value is None and field_type == "editor":
            continue

        # Confirm the change
        if questionary.confirm("Save this change to the database?").ask():
            try:
                update_response = supabase_client.table("properties").update({
                    field_name: new_value
                }).eq("address1", property_id).execute()

                if hasattr(update_response, "data"):
                    console.print(f"[green]✓ Successfully updated {field_choice}[/green]")
                else:
                    console.print("[yellow]Update completed but response has no 'data' attribute[/yellow]")
            except Exception as e:
                console.print(f"[red]Error updating property: {str(e)}[/red]")
        else:
            console.print("[yellow]Change not saved[/yellow]")


@dataclass
class RiskAssessmentConfig:
    """Configuration for risk assessment operations"""

    reasoning_model: str = "gpt-5.1"
    max_tokens: int = 120000
    reasoning_cost_per_input_token: float = 1.25 / 1000000
    reasoning_cost_per_output_token: float = 10 / 1000000


class RiskAssessmentClient:
    """Handles risk assessment report generation for properties"""

    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console
        self.config = RiskAssessmentConfig()

        # Initialize OpenAI client
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.openai_client = openai.OpenAI(api_key=openai_api_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate the total cost of LLM reasoning"""
        input_cost = input_tokens * self.config.reasoning_cost_per_input_token
        output_cost = output_tokens * self.config.reasoning_cost_per_output_token
        total_cost = input_cost + output_cost
        return Decimal(str(total_cost)).quantize(Decimal("0.0001"))

    def _sanitize_content(self, content: str) -> str:
        """Sanitize content to prevent database errors"""
        # Remove null bytes (PostgreSQL doesn't like these)
        sanitized = content.replace('\u0000', '')

        # Remove other control characters except newlines and tabs
        sanitized = ''.join(
            char for char in sanitized
            if ord(char) >= 32 or char in '\n\r\t'
        )

        # Ensure valid UTF-8
        sanitized = sanitized.encode('utf-8', errors='ignore').decode('utf-8')

        return sanitized

    def _format_property_assessment_fields(self, property_data: Dict[str, Any]) -> str:
        """Format property assessment fields for the prompt"""
        lines = []

        for field_label, (field_name, field_type) in FIELD_CONFIG.items():
            value = property_data.get(field_name)

            # Special handling for days_to_date fields (convert date to days)
            if field_type == "days_to_date" and value:
                try:
                    # Parse the date string
                    if isinstance(value, str):
                        listed_datetime = datetime.fromisoformat(value.replace('Z', '+00:00').split('T')[0])
                    else:
                        listed_datetime = datetime.fromisoformat(str(value))

                    # Calculate days on market
                    days_on_market = (datetime.now() - listed_datetime).days
                    display_value = f"{days_on_market} days"
                except (ValueError, AttributeError):
                    display_value = "Invalid date"
            # Format the value appropriately
            elif value is None:
                display_value = "Not set"
            elif isinstance(value, bool):
                display_value = "Yes" if value else "No"
            elif isinstance(value, str):
                display_value = value.strip() if value.strip() else "Not set"
            else:
                display_value = str(value)

            lines.append(f"- **{field_label}**: {display_value}")

        return "\n".join(lines)

    def _get_neighborhood_analysis(self, property_data: Dict[str, Any]) -> str:
        """Fetch neighborhood analysis for the property"""
        neighborhood = property_data.get("neighborhood")

        if not neighborhood:
            return "N/A - No neighborhood assigned"

        try:
            # Look for neighborhood report
            response = self.supabase.table("research_reports").select("report_content").eq(
                "research_type", f"{neighborhood}_neighborhood_report"
            ).order("created_at", desc=True).limit(1).execute()

            if response.data and len(response.data) > 0:
                # Return first 2000 characters of the report
                report = response.data[0]["report_content"]
                if len(report) > 2000:
                    return report[:2000] + "\n\n...(truncated for brevity)"
                return report
            else:
                return "N/A - No neighborhood analysis available"
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not fetch neighborhood analysis: {str(e)}[/yellow]")
            return "N/A - Error fetching neighborhood analysis"

    def _get_rent_estimates(self, property_id: str, property_data: Dict[str, Any]) -> str:
        """Format rent estimates for the prompt"""
        lines = []
        is_sfh = property_data.get("units", 1) == 0

        # Get per-unit/room rent estimates
        try:
            response = self.supabase.table("rent_estimates").select("*").eq(
                "address1", property_id
            ).order("unit_num").execute()

            if response.data and len(response.data) > 0:
                lines.append("### Per-Unit/Room Rent Estimates:")
                for unit in response.data:
                    unit_num = unit.get("unit_num", "?")
                    beds = unit.get("beds", "?")
                    baths = unit.get("baths", "?")
                    rent = unit.get("rent_estimate")
                    rent_high = unit.get("rent_estimate_high")
                    rent_low = unit.get("rent_estimate_low")

                    unit_label = f"Room {unit_num}" if is_sfh else f"Unit {unit_num}"
                    lines.append(f"- **{unit_label}** ({beds} bed, {baths} bath):")
                    lines.append(f"  - Primary Estimate: ${int(rent):,}" if rent else "  - Primary Estimate: Not set")
                    lines.append(f"  - High Estimate: ${int(rent_high):,}" if rent_high else "  - High Estimate: Not set")
                    lines.append(f"  - Low Estimate: ${int(rent_low):,}" if rent_low else "  - Low Estimate: Not set")
            else:
                lines.append("No per-unit/room rent estimates available")
        except Exception as e:
            self.console.print(f"[yellow]Warning: Could not fetch rent estimates: {str(e)}[/yellow]")
            lines.append("Error fetching rent estimates")

        # For single family homes, also include property-wide estimates
        if is_sfh:
            lines.append("\n### Property-Wide Rent Estimate (entire house):")
            rent_estimate = property_data.get("rent_estimate")
            rent_estimate_high = property_data.get("rent_estimate_high")
            rent_estimate_low = property_data.get("rent_estimate_low")

            if rent_estimate:
                lines.append(f"- Primary Estimate: ${int(rent_estimate):,}")
                lines.append(f"- High Estimate: ${int(rent_estimate_high):,}" if rent_estimate_high else "- High Estimate: Not set")
                lines.append(f"- Low Estimate: ${int(rent_estimate_low):,}" if rent_estimate_low else "- Low Estimate: Not set")
            else:
                lines.append("No property-wide rent estimate available")

        return "\n".join(lines)

    def _build_risk_assessment_prompt(self, property_id: str, property_data: Dict[str, Any]) -> str:
        """Build the comprehensive risk assessment prompt"""

        # Property overview
        address = property_data.get("address1", "Unknown")
        purchase_price = property_data.get("purchase_price")
        beds = property_data.get("beds", "?")
        baths = property_data.get("baths", "?")
        sqft = property_data.get("square_ft")
        year_built = property_data.get("built_in")
        units = property_data.get("units", 1)
        property_type = "Single Family Home" if units == 0 else f"{units}-Unit Multi-Family"

        # Extract all financial data from property_data
        # Loan & Mortgage
        down_payment = property_data.get("down_payment")
        loan_amount = property_data.get("loan_amount")
        monthly_mortgage = property_data.get("monthly_mortgage")

        # PITI Components
        piti = property_data.get("piti")
        monthly_taxes = property_data.get("monthly_taxes")
        monthly_insurance = property_data.get("monthly_insurance")
        monthly_mip = property_data.get("monthly_mip")

        # Operating Expenses (Year 1 - House Hacking)
        operating_expenses_y1 = property_data.get("operating_expenses_y1")
        monthly_vacancy_costs_y1 = property_data.get("monthly_vacancy_costs_y1")
        monthly_repair_costs_y1 = property_data.get("monthly_repair_costs_y1")

        # Cash Flow Details (Year 1)
        total_rent = property_data.get("total_rent")
        min_rent = property_data.get("min_rent")
        net_rent_y1 = property_data.get("net_rent_y1")
        monthly_NOI_y1 = property_data.get("monthly_NOI_y1")
        total_monthly_cost_y1 = property_data.get("total_monthly_cost_y1")
        monthly_cf_y1 = property_data.get("monthly_cash_flow_y1")

        # Investment Costs
        closing_costs = property_data.get("closing_costs")
        cash_needed = property_data.get("cash_needed")

        # Key Ratios
        cap_rate_y1 = property_data.get("cap_rate_y1")
        coc_y1 = property_data.get("CoC_y1")
        DSCR = property_data.get("DSCR")
        ltv_ratio = property_data.get("ltv_ratio")
        fha_self_sufficiency_ratio = property_data.get("fha_self_sufficiency_ratio")

        # Format property overview fields
        purchase_price_str = f"${purchase_price:,}" if purchase_price else "Not set"
        sqft_str = f"{sqft:,} sqft" if sqft else "Not set"
        year_built_str = str(year_built) if year_built else "Not set"

        # Format loan & mortgage fields
        down_payment_str = f"${down_payment:,.0f}" if down_payment else "Not calculated"
        loan_amount_str = f"${loan_amount:,.0f}" if loan_amount else "Not calculated"
        monthly_mortgage_str = f"${monthly_mortgage:,.2f}" if monthly_mortgage else "Not calculated"

        # Format PITI fields
        piti_str = f"${piti:,.2f}" if piti else "Not calculated"
        monthly_taxes_str = f"${monthly_taxes:,.2f}" if monthly_taxes else "Not calculated"
        monthly_insurance_str = f"${monthly_insurance:,.2f}" if monthly_insurance else "Not calculated"
        monthly_mip_str = f"${monthly_mip:,.2f}" if monthly_mip else "Not calculated"

        # Format operating expenses fields
        operating_expenses_y1_str = f"${operating_expenses_y1:,.2f}" if operating_expenses_y1 else "Not calculated"
        monthly_vacancy_costs_y1_str = f"${monthly_vacancy_costs_y1:,.2f}" if monthly_vacancy_costs_y1 else "Not calculated"
        monthly_repair_costs_y1_str = f"${monthly_repair_costs_y1:,.2f}" if monthly_repair_costs_y1 else "Not calculated"

        # Format cash flow fields
        total_rent_str = f"${total_rent:,.2f}" if total_rent else "Not set"
        min_rent_str = f"${min_rent:,.2f}" if min_rent else "Not set"
        net_rent_y1_str = f"${net_rent_y1:,.2f}" if net_rent_y1 else "Not calculated"
        monthly_NOI_y1_str = f"${monthly_NOI_y1:,.2f}" if monthly_NOI_y1 else "Not calculated"
        total_monthly_cost_y1_str = f"${total_monthly_cost_y1:,.2f}" if total_monthly_cost_y1 else "Not calculated"
        monthly_cf_str = f"${monthly_cf_y1:,.2f}" if monthly_cf_y1 else "Not calculated"

        # Format investment costs
        cash_needed_str = f"${cash_needed:,.2f}" if cash_needed else "Not calculated"

        # Format ratios
        cap_rate_str = f"{cap_rate_y1:.2f}%" if cap_rate_y1 else "Not calculated"
        coc_str = f"{coc_y1:.2f}%" if coc_y1 else "Not calculated"
        DSCR_str = f"{DSCR:.2f}" if DSCR else "Not calculated"
        ltv_ratio_str = f"{ltv_ratio:.1%}" if ltv_ratio else "Not calculated"
        fha_self_sufficiency_str = f"{fha_self_sufficiency_ratio:.2f}" if fha_self_sufficiency_ratio else "Not calculated"

        # Build prompt
        prompt = f"""You are a seasoned real estate analyst specializing in house hacking for first-time homebuyers. Analyze this property from the perspective of an owner-occupant who will live in it while renting out other rooms/units.

# PRIMARY DECISION QUESTIONS
1. Should I make an offer on this property vs other opportunities?
2. What are the 3 biggest risks?
3. What offer price accounts for the identified risks?

# Property Overview

**Address**: {address}
**Property Type**: {property_type}
**Purchase Price**: {purchase_price_str}
**Bedrooms**: {beds} | **Bathrooms**: {baths}
**Square Footage**: {sqft_str}
**Year Built**: {year_built_str}

# Buyer Profile

- **First-time homebuyer**, 24-year-old software engineer in Des Moines, Iowa
- **DIY capable** for cosmetic repairs (paint, fixtures, minor fixes)
- **Want to avoid** major rehabs and large system replacements (roof, HVAC, foundation)

# Financial Summary (Year 1 - House Hacking)

| Category | Amount |
|----------|--------|
| **Purchase & Loan** | |
| Purchase Price | {purchase_price_str} |
| Down Payment | {down_payment_str} |
| Loan Amount | {loan_amount_str} |
| LTV Ratio | {ltv_ratio_str} |
| Cash Needed at Closing | {cash_needed_str} |
| | |
| **Monthly PITI** | |
| Principal & Interest | {monthly_mortgage_str} |
| Property Taxes | {monthly_taxes_str} |
| Home Insurance | {monthly_insurance_str} |
| Mortgage Insurance | {monthly_mip_str} |
| **→ Total PITI** | **{piti_str}** |
| | |
| **Rental Income & Expenses** | |
| Total Monthly Rent (all units/rooms) | {total_rent_str} |
| Your Room/Unit Rent (cheapest) | {min_rent_str} |
| Net Rental Income (from tenants) | {net_rent_y1_str} |
| Vacancy Reserve | {monthly_vacancy_costs_y1_str} |
| Repair/Maintenance Reserve | {monthly_repair_costs_y1_str} |
| **→ Total Operating Expenses** | **{operating_expenses_y1_str}** |
| | |
| **Bottom Line** | |
| Total Monthly Costs (PITI + OpEx) | {total_monthly_cost_y1_str} |
| Net Operating Income (NOI) | {monthly_NOI_y1_str} |
| **→ YOUR MONTHLY CASH FLOW** | **{monthly_cf_str}** |
| | |
| **Investment Metrics** | |
| Cap Rate (Year 1) | {cap_rate_str} |
| Cash-on-Cash Return | {coc_str} |
| DSCR | {DSCR_str} |
| FHA Self-Sufficiency Ratio | {fha_self_sufficiency_str} |

# Rent Estimates

{self._get_rent_estimates(property_id, property_data)}

# Property Assessment Data

{self._format_property_assessment_fields(property_data)}

# Neighborhood Analysis

{self._get_neighborhood_analysis(property_data)}

---

# Instructions

Generate a concise **House Hacking Risk Assessment Report** with these 4 sections:

## 1. Go/No-Go Recommendation
- **Risk Score (1-10)** using this rubric:
  - **9-10**: Excellent condition, minimal major system risk, strong rental demand
  - **7-8**: Good fundamentals, minor cosmetic work needed, low-moderate risk
  - **4-6**: Moderate concerns (older systems, legal complications, rental demand questions)
  - **1-3**: Major rehab needed, significant legal restrictions, or high tenant turnover risk
- **Offer Price Recommendation**: At asking price, or what counteroffer?
- **Top 3 Risks**: The biggest concerns specific to THIS property
- **One-Paragraph Summary**: Should I pursue this deal or walk away?

## 2. Critical Risks & Deal-Breakers
- **Major Systems Condition** (focus on big-ticket items):
  - Roof: age, remaining life, replacement cost estimate
  - HVAC: age, condition, replacement cost estimate
  - Foundation: any structural issues, moisture, settling
  - Water heater: age, capacity
  - Plumbing/Electrical: any major red flags (galvanized pipes, knob-and-tube, etc.)
- **Rehab Risk Level**: Move-in ready vs. cosmetic work vs. major rehab required
- **Legal Blockers**:
  - HOA rental restrictions or excessive fees
  - Zoning issues (can you legally rent rooms/units?)
  - Deed restrictions limiting house hacking
  - Permit issues (open/pulled permits, unpermitted work)
  - Flood zone insurance costs
- **Deal-Breaker Issues**: What problems should make a first-time buyer walk away?

## 3. House Hacking Viability
- **Rental Demand**: How easy to find roommates/tenants in this area/neighborhood?
- **Rent Achievability**: Are the estimated rents realistic for this location?
- **Vacancy Risk**: Financial impact if 2-3 months vacant
- **Tenant Management Challenges**: Specific to this property (shared spaces, unit layout, etc.)
- **Financial Resilience**: Can you afford mortgage alone if tenants leave?
- **Property Turnover Concerns**: Why has this property or neighborhood had high turnover?
- **Days on Market Analysis**: What does listing time indicate?

## 4. Action Plan & Next Steps
- **Must-Do Inspections**: Which professional inspections are essential? (especially for major systems)
- **Negotiation Strategy**:
  - What repairs/issues justify price reduction?
  - Specific dollar amounts to request based on identified issues
- **Offer Contingencies**: Inspection, financing, appraisal, HOA approval, etc.
- **Cash Reserve Needed**: Emergency fund recommendation for major repairs (beyond closing costs)
- **Key Questions for Seller**: About systems, repairs, permits, rental history
- **Risk Mitigation**: Specific actions to address the top 3 risks identified in Section 1

---

**Output Format**: Use clear markdown with headers, bullet points, and bold text. Be specific with dollar amounts, percentages, and actionable recommendations. Focus on property-specific insights, not generic advice. Prioritize concerns relevant to a first-time homebuyer doing their first house hack.
"""

        return prompt

    def generate_risk_assessment(self, property_id: str) -> Optional[str]:
        """
        Generate a comprehensive risk assessment report for a property.

        Args:
            property_id: The address1 of the property

        Returns:
            report_id if successful, None if failed
        """
        try:
            # Fetch property data
            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]Fetching property data..."),
                console=self.console,
            ) as progress:
                progress.add_task("fetch", total=None)

                response = self.supabase.table("properties").select("*").eq(
                    "address1", property_id
                ).single().execute()

                if not response.data:
                    self.console.print(f"[red]Property not found: {property_id}[/red]")
                    return None

                property_data = response.data

            # Build prompt
            self.console.print("[cyan]Building risk assessment prompt...[/cyan]")
            prompt = self._build_risk_assessment_prompt(property_id, property_data)

            # Generate analysis with LLM
            self.console.print("[cyan]Generating risk assessment report (this may take 30-60 seconds)...[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[cyan]Analyzing property with AI..."),
                console=self.console,
            ) as progress:
                progress.add_task("analyze", total=None)

                response = self.openai_client.chat.completions.create(
                    model=self.config.reasoning_model,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=self.config.max_tokens,
                )

            report_content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Calculate cost
            cost = self._calculate_cost(input_tokens, output_tokens)

            self.console.print("\n[green]✓ Risk assessment generated successfully![/green]")
            self.console.print(f"[cyan]Input tokens: {input_tokens:,} | Output tokens: {output_tokens:,} | Cost: ${cost}[/cyan]\n")

            # Store report
            self.console.print("[cyan]Saving report to database...[/cyan]")
            sanitized_content = self._sanitize_content(report_content)
            sanitized_prompt = self._sanitize_content(prompt)

            result = self.supabase.table("research_reports").insert({
                "property_id": property_id,
                "report_content": sanitized_content,
                "prompt_used": sanitized_prompt,
                "status": "completed",
                "api_cost": float(cost),
                "research_type": "property_risk_report",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            if result.data and len(result.data) > 0:
                report_id = result.data[0]["id"]
                self.console.print(f"[green]✓ Report saved successfully (ID: {report_id})[/green]\n")
                return report_id
            else:
                self.console.print("[red]Failed to save report[/red]")
                return None

        except Exception as e:
            self.console.print(f"[red]Error generating risk assessment: {str(e)}[/red]")
            import traceback
            traceback.print_exc()
            return None
