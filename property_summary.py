import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import openai
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from supabase import Client


@dataclass
class PropertySummaryConfig:
    """Configuration for property summary operations"""

    reasoning_model: str = "gpt-5.1"
    max_tokens: int = 16000  # Much shorter than risk assessment
    reasoning_cost_per_input_token: float = 1.25 / 1000000
    reasoning_cost_per_output_token: float = 10 / 1000000


class PropertySummaryClient:
    """Handles property narrative summary report generation"""

    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console
        self.config = PropertySummaryConfig()

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

    def _get_neighborhood_summary(self, property_data: Dict[str, Any]) -> str:
        """Fetch neighborhood grade and brief summary"""
        neighborhood = property_data.get("neighborhood")
        grade = property_data.get("neighborhood_letter_grade")

        if not neighborhood:
            return "No neighborhood assigned"

        grade_text = f" (Grade: {grade})" if grade else ""

        try:
            # Get brief excerpt from neighborhood report
            response = self.supabase.table("research_reports").select("report_content").eq(
                "research_type", f"{neighborhood}_neighborhood_report"
            ).order("created_at", desc=True).limit(1).execute()

            if response.data and len(response.data) > 0:
                report = response.data[0]["report_content"]
                # Get first 500 characters for context
                excerpt = report[:500] + "..." if len(report) > 500 else report
                return f"{neighborhood}{grade_text}\n\n{excerpt}"
            else:
                return f"{neighborhood}{grade_text} - No detailed analysis available"
        except Exception:
            return f"{neighborhood}{grade_text}"

    def _get_rent_summary(self, property_id: str, property_data: Dict[str, Any]) -> str:
        """Get detailed rent estimate summary with per-unit/room breakdown"""
        is_sfh = property_data.get("units", 1) == 0
        total_rent = property_data.get("total_rent", 0)
        min_rent = property_data.get("min_rent", 0)
        net_rent_y1 = property_data.get("net_rent_y1", 0)

        lines = []

        # Fetch per-unit/room rent estimates from database
        try:
            response = self.supabase.table("rent_estimates").select("*").eq(
                "address1", property_id
            ).order("unit_num").execute()

            if response.data and len(response.data) > 0:
                if is_sfh:
                    lines.append("**Per-Room Pricing (While House-Hacking, Year 1)**:")
                    lines.append("You'll rent out individual rooms while living in one yourself.\n")
                else:
                    lines.append("**Per-Unit Rent Estimates**:\n")

                for unit in response.data:
                    unit_num = unit.get("unit_num", "?")
                    beds = unit.get("beds", "?")
                    baths = unit.get("baths", "?")
                    rent_low = unit.get("rent_estimate_low")
                    rent_primary = unit.get("rent_estimate")
                    rent_high = unit.get("rent_estimate_high")

                    unit_label = f"Room {unit_num}" if is_sfh else f"Unit {unit_num}"
                    lines.append(f"- **{unit_label}** ({beds} bed, {baths} bath):")
                    if rent_primary:
                        lines.append(f"  - Primary estimate: ${int(rent_primary):,}/mo")
                        if rent_low and rent_high:
                            lines.append(f"  - Range: ${int(rent_low):,} - ${int(rent_high):,}/mo")

                # Show totals
                lines.append(f"\n**Totals**:")
                lines.append(f"- Total monthly rent (all {'rooms' if is_sfh else 'units'}): ${total_rent:,.0f}")
                lines.append(f"- Your {'room' if is_sfh else 'unit'} (cheapest): ${min_rent:,.0f}")
                lines.append(f"- Net rent from tenants (Year 1): ${net_rent_y1:,.0f}")

                # For SFH, add property-wide rent explanation
                if is_sfh:
                    rent_estimate = property_data.get("rent_estimate")
                    if rent_estimate:
                        lines.append(f"\n**Property-Wide Rent (After Moving Out, Year 2+)**:")
                        lines.append(f"When you move out, you'll rent the entire property (not by room).")
                        rent_estimate_low = property_data.get("rent_estimate_low")
                        rent_estimate_high = property_data.get("rent_estimate_high")
                        lines.append(f"- Primary estimate: ${int(rent_estimate):,}/mo")
                        if rent_estimate_low and rent_estimate_high:
                            lines.append(f"- Range: ${int(rent_estimate_low):,} - ${int(rent_estimate_high):,}/mo")

                return "\n".join(lines)
            else:
                return "Rent estimates not available"
        except Exception as e:
            return f"Error fetching rent estimates: {str(e)}"

    def _get_key_assessment_notes(self, property_data: Dict[str, Any]) -> list:
        """Extract key property assessment concerns"""
        concerns = []

        # Check major issues
        if property_data.get("in_flood_zone"):
            concerns.append("In flood zone")

        if property_data.get("has_open_pulled_permits"):
            concerns.append("Has open/pulled permits")

        if property_data.get("has_work_done_wo_permits"):
            concerns.append("Unpermitted work identified")

        if property_data.get("has_hao"):
            concerns.append("HOA present")

        if property_data.get("has_deed_restrictions"):
            concerns.append("Deed restrictions exist")

        # Check turnover rate if available
        turnover = property_data.get("historical_turnover_rate")
        if turnover and turnover > 50:
            concerns.append(f"High turnover rate ({turnover}%/year)")

        # Check days on market
        listed_date = property_data.get("listed_date")
        if listed_date:
            try:
                if isinstance(listed_date, str):
                    listed_datetime = datetime.fromisoformat(listed_date.replace('Z', '+00:00').split('T')[0])
                else:
                    listed_datetime = datetime.fromisoformat(str(listed_date))
                days_on_market = (datetime.now() - listed_datetime).days
                if days_on_market > 90:
                    concerns.append(f"{days_on_market} days on market")
            except (ValueError, AttributeError):
                pass

        return concerns

    def _build_summary_prompt(self, property_id: str, property_data: Dict[str, Any]) -> str:
        """Build the narrative summary prompt"""

        # Property overview
        address = property_data.get("address1", "Unknown")
        purchase_price = property_data.get("purchase_price")
        beds = property_data.get("beds", "?")
        baths = property_data.get("baths", "?")
        sqft = property_data.get("square_ft")
        year_built = property_data.get("built_in")
        units = property_data.get("units", 1)
        property_type = "Single Family Home" if units == 0 else f"{units}-Unit Multi-Family"

        # Financial data - Year 1 (House Hacking)
        cash_needed = property_data.get("cash_needed")
        monthly_cf_y1 = property_data.get("monthly_cash_flow_y1")
        after_tax_cf_y1 = property_data.get("after_tax_cash_flow_y1")
        coc_y1 = property_data.get("CoC_y1")
        piti = property_data.get("piti")
        total_monthly_cost_y1 = property_data.get("total_monthly_cost_y1")
        DSCR = property_data.get("DSCR")
        fha_self_sufficiency = property_data.get("fha_self_sufficiency_ratio")

        # Financial data - Year 2 (Full Rental)
        monthly_cf_y2 = property_data.get("monthly_cash_flow_y2")
        after_tax_cf_y2 = property_data.get("after_tax_cash_flow_y2")
        coc_y2 = property_data.get("CoC_y2")
        cap_rate_y2 = property_data.get("cap_rate_y2")

        # Long-term projections
        payback_period = property_data.get("payback_period_years")
        equity_10yr = property_data.get("10y_forecast")
        equity_20yr = property_data.get("20y_forecast")

        # Format values
        purchase_price_str = f"${purchase_price:,}" if purchase_price else "Not set"
        sqft_str = f"{sqft:,} sqft" if sqft else "Not set"
        year_built_str = str(year_built) if year_built else "Not set"
        home_age = datetime.now().year - year_built if year_built else None

        cash_needed_str = f"${cash_needed:,.0f}" if cash_needed else "Not calculated"
        piti_str = f"${piti:,.0f}" if piti else "Not calculated"
        total_cost_y1_str = f"${total_monthly_cost_y1:,.0f}" if total_monthly_cost_y1 else "Not calculated"

        cf_y1_str = f"${monthly_cf_y1:,.0f}" if monthly_cf_y1 else "Not calculated"
        cf_after_tax_y1_str = f"${after_tax_cf_y1:,.0f}" if after_tax_cf_y1 else "Not calculated"
        coc_y1_str = f"{coc_y1:.1f}%" if coc_y1 else "Not calculated"

        cf_y2_str = f"${monthly_cf_y2:,.0f}" if monthly_cf_y2 else "Not calculated"
        cf_after_tax_y2_str = f"${after_tax_cf_y2:,.0f}" if after_tax_cf_y2 else "Not calculated"
        coc_y2_str = f"{coc_y2:.1f}%" if coc_y2 else "Not calculated"
        cap_rate_y2_str = f"{cap_rate_y2:.1f}%" if cap_rate_y2 else "Not calculated"

        DSCR_str = f"{DSCR:.2f}" if DSCR else "Not calculated"
        fha_str = f"{fha_self_sufficiency:.2f}" if fha_self_sufficiency else "Not calculated"

        payback_str = f"{payback_period:.1f} years" if payback_period else "Not calculated"
        equity_10yr_str = f"${equity_10yr:,.0f}" if equity_10yr else "Not calculated"
        equity_20yr_str = f"${equity_20yr:,.0f}" if equity_20yr else "Not calculated"

        # Get supporting data
        neighborhood_summary = self._get_neighborhood_summary(property_data)
        rent_summary = self._get_rent_summary(property_id, property_data)
        key_concerns = self._get_key_assessment_notes(property_data)
        concerns_text = ", ".join(key_concerns) if key_concerns else "None identified"

        prompt = f"""You are a direct, no-nonsense real estate analyst. Create a concise narrative summary for a 24-year-old first-time house hacker evaluating this property.

# Property Overview

**Address**: {address}
**Type**: {property_type}
**Price**: {purchase_price_str}
**Size**: {beds} bed, {baths} bath, {sqft_str}
**Built**: {year_built_str} ({home_age} years old)

# Financial Snapshot

**Investment Required**: {cash_needed_str} at closing

**Year 1 (House Hacking - You Live There)**:
- Monthly costs (PITI + OpEx): {total_cost_y1_str}
- Your monthly cash flow: {cf_y1_str} ({cf_after_tax_y1_str} after tax)
- Cash-on-Cash return: {coc_y1_str}
- DSCR: {DSCR_str}
- FHA Self-Sufficiency: {fha_str}

**Year 2+ (Full Rental - You Move Out)**:
- Monthly cash flow: {cf_y2_str} ({cf_after_tax_y2_str} after tax)
- Cash-on-Cash return: {coc_y2_str}
- Cap rate: {cap_rate_y2_str}

**Long-term Trajectory**:
- Payback period: {payback_str}
- Projected equity in 10 years: {equity_10yr_str}
- Projected equity in 20 years: {equity_20yr_str}

# Rent Estimates

{rent_summary}

**Note**: These rent estimates are based on detailed research and analysis of 25+ comparable properties in the area, considering bedroom/bathroom count, location, amenities, and current market conditions.

# Neighborhood

{neighborhood_summary}

# Property Assessment Flags

{concerns_text}

---

# Instructions

Write a direct, no-nonsense narrative summary with these **3 sections with loose headers**:

## The Bottom Line
One paragraph that clearly states: Is this a good deal or not? What's the verdict on financial viability? Cut through the noise and give the straight truth.

## The House-Hacking Play
One paragraph covering: What's it like to live here Year 1? What will your actual costs be? How does the house-hacking math work? Does this neighborhood feel right for a 24-year-old?

## The Full Rental Picture
One paragraph covering: What happens when you move out? How does this perform as a full rental investment? What's the long-term trajectory look like (5-10-20 years)? What are the key risks or concerns to watch?

# Critical Requirements

- **Direct tone**: "This property cash flows well but has X risk" NOT "This property may potentially offer favorable returns"
- **Use specific numbers**: Reference actual values from the data above
- **Investment trajectory framing**: Frame it as a journey from house-hacking (Year 1) to full rental (Year 2+)
- **Be concise**: Total output should be 1-3 short paragraphs with section headers
- **Include the good, bad, and ugly**: Don't sugarcoat issues, but also highlight strengths
- **Focus on what matters**: Cash flow, risks, neighborhood quality, long-term potential
- **No fluff**: Every sentence should add value

# What NOT to do

- Don't write generic advice that could apply to any property
- Don't use hedging language ("may", "might", "potentially" unless there's genuine uncertainty)
- Don't list every single data point - synthesize and prioritize
- Don't be verbose - this is a quick executive summary, not a full report

Output ONLY the 3-section narrative. No preamble, no "here's the summary" - just start with "## The Bottom Line" and go.
"""

        return prompt

    def generate_summary(self, property_id: str) -> Optional[str]:
        """
        Generate a narrative summary report for a property.

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
            self.console.print("[cyan]Building property summary prompt...[/cyan]")
            prompt = self._build_summary_prompt(property_id, property_data)

            # Generate summary with LLM
            self.console.print("[cyan]Generating property summary (this may take 15-30 seconds)...[/cyan]")

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

            self.console.print("\n[green]✓ Property summary generated successfully![/green]")
            self.console.print(f"[cyan]Input tokens: {input_tokens:,} | Output tokens: {output_tokens:,} | Cost: ${cost}[/cyan]\n")

            # Store report
            self.console.print("[cyan]Saving summary to database...[/cyan]")
            sanitized_content = self._sanitize_content(report_content)
            sanitized_prompt = self._sanitize_content(prompt)

            result = self.supabase.table("research_reports").insert({
                "property_id": property_id,
                "report_content": sanitized_content,
                "prompt_used": sanitized_prompt,
                "status": "completed",
                "api_cost": float(cost),
                "research_type": "property_narrative_summary",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()

            if result.data and len(result.data) > 0:
                report_id = result.data[0]["id"]
                self.console.print(f"[green]✓ Summary saved successfully (ID: {report_id})[/green]\n")
                return report_id
            else:
                self.console.print("[red]Failed to save summary[/red]")
                return None

        except Exception as e:
            self.console.print(f"[red]Error generating property summary: {str(e)}[/red]")
            import traceback
            traceback.print_exc()
            return None
