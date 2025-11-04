"""
Rent Research Module using Tavily + o1-mini

This module provides comprehensive rental market analysis for properties using
Tavily API for web search and o1-mini for intelligent reasoning and analysis.
"""

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import openai
from pydantic import BaseModel, create_model
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from supabase import Client
from tavily import TavilyClient


@dataclass
class ResearchConfig:
    """Configuration for rent research operations"""

    reasoning_model: str = "gpt-5"
    max_tokens: int = 120000
    search_cost_per_query: float = 0.008  # Tavily cost
    reasoning_cost_per_input_token: float = 1.25 / 1000000
    reasoning_cost_per_output_token: float = 10 / 1000000
    searches_per_property: int = 12


class RentEstimates(BaseModel):
    """Pydantic model for structured rent estimate outputs"""

    rent_estimate: float
    rent_estimate_high: float
    rent_estimate_low: float


class RentResearcher:
    """Handles rent research operations using Tavily + o1-mini"""

    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console
        self.config = ResearchConfig()

        # Initialize OpenAI client for reasoning
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.openai_client = openai.OpenAI(api_key=openai_api_key)

        # Initialize Tavily client for search
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY environment variable not set")
        self.tavily_client = TavilyClient(api_key=tavily_api_key)

    def _calculate_cost(
        self, num_searches: int, input_tokens: int, output_tokens: int
    ) -> Decimal:
        """Calculate the total cost of searches + reasoning"""
        search_cost = num_searches * self.config.search_cost_per_query
        reasoning_input_cost = input_tokens * self.config.reasoning_cost_per_input_token
        reasoning_output_cost = (
            output_tokens * self.config.reasoning_cost_per_output_token
        )
        total_cost = search_cost + reasoning_input_cost + reasoning_output_cost
        return Decimal(str(total_cost)).quantize(Decimal("0.0001"))

    def _generate_search_queries(self, property_data: Dict[str, Any]) -> List[str]:
        """Generate targeted search queries for comprehensive rental analysis"""

        address = property_data.get("address1", "Unknown Address")
        beds = property_data.get("beds", 0)
        baths = property_data.get("baths", 0)
        units = property_data.get("units", 1)

        # Extract city/area from address for location-based searches
        location = address.split(",")[0] if "," in address else address

        queries = [
            # Comparable rental properties
            f"{beds} bedroom {baths} bathroom rental near {location}",
            f"duplex rental prices {location}"
            if units == 2
            else f"{units} unit rental {location}",
            f"rental comps {location} {beds}bed {baths}bath",
            # Market data and trends
            f"{location} rental market report 2024 2025",
            f"{location} average rent prices trends",
            f"{location} rental vacancy rates market analysis",
            # Neighborhood analysis
            f"{location} neighborhood walkability transit score",
            f"{location} rental demand supply market conditions",
            f"{location} property values rental yield analysis",
            # Historical and seasonal data
            f"{location} rental price history 12 months",
            f"{location} seasonal rental pricing trends",
            f"{location} rental market forecast 2025",
        ]

        return queries

    def _perform_searches(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Perform Tavily searches for all queries"""

        search_results = []
        total_queries = len(queries)
        successful_searches = 0

        self.console.print(
            f"\n[bold cyan]🔍 Starting Tavily search for {total_queries} queries...[/bold cyan]\n"
        )

        for i, query in enumerate(queries, 1):
            # Pre-search logging
            self.console.print(
                f'[cyan]🔍 [{i}/{total_queries}] Searching:[/cyan] [white]"{query}"[/white]'
            )

            try:
                response = self.tavily_client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5,
                    include_raw_content="markdown",
                    chunks_per_source=5,
                )

                if response and "results" in response:
                    results_count = len(response["results"])
                    sources_count = len(
                        set(result.get("url", "") for result in response["results"])
                    )

                    for result in response["results"]:
                        search_results.append(
                            {
                                "query": query,
                                "title": result.get("title", ""),
                                "url": result.get("url", ""),
                                "content": result.get("content", ""),
                                "raw_content": result.get("raw_content", ""),
                                "score": result.get("score", 0),
                            }
                        )

                    # Post-search success logging
                    self.console.print(
                        f"[green]   ✅ Found {results_count} results from {sources_count} sources[/green]\n"
                    )
                    successful_searches += 1
                else:
                    # Post-search no results logging
                    self.console.print("[yellow]   ❌ No results found[/yellow]\n")

            except Exception as e:
                # Enhanced error logging
                self.console.print(f"[red]   ❌ Search failed: {str(e)}[/red]\n")
                continue

        # Overall search statistics summary
        total_results = len(search_results)
        failed_searches = total_queries - successful_searches

        self.console.print("[bold green]📊 Search Summary:[/bold green]")
        self.console.print(
            f"[green]   • Successful searches: {successful_searches}/{total_queries}[/green]"
        )
        if failed_searches > 0:
            self.console.print(
                f"[yellow]   • Failed searches: {failed_searches}[/yellow]"
            )
        self.console.print(
            f"[cyan]   • Total results collected: {total_results} data points[/cyan]\n"
        )

        return search_results
    
    def _create_rent_comp_md_table(self, address1):
        table = ""

        # get rent_estimates based on address1
        response = self.supabase.table('rent_estimates').select('*').eq('address1', address1).execute()

        if not hasattr(response, "data") or not response.data:
            return "No rent estimates found for this property.\n"

        for rent_estimate in response.data:
            # Create section header for this unit
            unit_config = f"{rent_estimate.get('beds', 'NA')}-bed {rent_estimate.get('baths', 'NA')}-bath"
            unit_num = rent_estimate.get('unit_num', 'NA')
            table += f"Unit {unit_num} - {unit_config}\n"
            
            # Query for comparables with smart filtering and ordering
            query2 = (
                self.supabase.table("comparable_rents")
                .select("*, rent_comp_to_rent_estimate!inner(*)")
                .eq("rent_comp_to_rent_estimate.estimate_id", rent_estimate['id'])
                .gte("rent_comp_to_rent_estimate.correlation", 0.7)  # Filter by correlation > 0.7
                .lte("rent_comp_to_rent_estimate.distance", 2.0)    # Filter by distance < 2 miles
                .limit(15)  # Limit to top 15 comparables
            )
            response2 = query2.execute()

            if not hasattr(response2, "data") or not response2.data:
                table += "No comparable rents found for this unit.\n\n"
                continue
            
            # Create markdown table header (optimized with 6 columns)
            table += "| Address | Config | Sq Ft | Rent | Dist | Corr |\n"
            table += "|---------|--------|-------|------|------|------|\n"
            
            # Add each comparable as a table row
            for comp in response2.data:
                # Extract street name only from address (remove city/state)
                full_address = comp.get('address', 'NA')
                if full_address != 'NA' and ',' in full_address:
                    address = full_address.split(',')[0].strip()
                else:
                    address = full_address
                
                # Combine beds/baths into config format (e.g., "2/1")
                beds = comp.get('beds', 'NA')
                baths = comp.get('baths', 'NA')
                config = f"{beds}/{baths}" if beds != 'NA' and baths != 'NA' else 'NA'
                
                square_feet = comp.get('square_feet', 'NA')
                rent_price = comp.get('rent_price', 'NA')
                
                # Get distance and correlation from the many-to-many relationship
                relationship_data = comp.get('rent_comp_to_rent_estimate', [])
                if relationship_data and len(relationship_data) > 0:
                    distance = relationship_data[0].get('distance', 'NA')
                    correlation = relationship_data[0].get('correlation', 'NA')
                else:
                    distance = 'NA'
                    correlation = 'NA'
                
                # Format the table row with optimized columns
                table += f"| {address} | {config} | {square_feet} | {rent_price} | {distance} | {correlation} |\n"
            
            table += "\n"

        return table

    def _create_analysis_prompt(
        self,
        property_data: Dict[str, Any],
        search_results: List[Dict[str, Any]],
        unit_configs: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        address = property_data.get("address1", "Unknown Address")
        purchase_price = property_data.get("purchase_price", 0)
        beds = property_data.get("beds", 0)
        baths = property_data.get("baths", 0)
        square_ft = property_data.get("square_ft", 0)
        units = property_data.get("units", 1)
        built_in = property_data.get("built_in", "Unknown")

        # markdown table with comparable rents
        rent_comp_md_table = self._create_rent_comp_md_table(address1=address)

        # Compile search data
        search_data = "\n\n".join(
            [
                f"**Query**: {result['query']}\n**Source**: {result['title']} ({result['url']})\n**Content**: {result['content'][:1000]}..."
                for result in search_results[:25]  # More data for o1-mini's reasoning
            ]
        )

        # Create unit configuration details if available
        unit_details = ""
        if unit_configs:
            unit_details = "\n\n# Unit Configuration Details\n"
            for config in unit_configs:
                unit_details += f"- **{config['beds']}-bed {config['baths']}-bath units**: {config['unit_count']} units "
                unit_nums = [str(unit["unit_num"]) for unit in config["units"]]
                unit_details += f"(Unit numbers: {', '.join(unit_nums)})\n"

        prompt = f"""
Analyze this rental property investment using the market research data. Provide comprehensive insights with specific dollar amounts and confidence levels.

# Property Details
- **Address**: {address}
- **Purchase Price**: ${purchase_price:,}
- **Bedrooms**: {beds} | **Bathrooms**: {baths} | **Square Footage**: {square_ft:,} sq ft
- **Units**: {units} | **Year Built**: {built_in}{unit_details}

# Market Research Data
## Web search data
{search_data}

## Comparable rents (filtered by correlation >0.7, distance <2mi)
{rent_comp_md_table}

# Analysis Requirements

## 1. Executive Summary
- Key findings and actionable recommendations
- **Specific recommended rent range with confidence level**
- Market positioning and investment viability

## 2. Market Rate & Comparable Analysis
- Current market rental rates by unit configuration
- Rent per square foot benchmarks from comparables
- Distance/location premium/discount factors
- **Specific rent ranges with justification for each unit type**

## 3. Historical Trends & Forecasting
- 6-12 month rental trend analysis
- Year-over-year percentage changes and market direction
- **Quantified trend data with growth projections**

## 4. Neighborhood & Location Analysis
- Walkability, transit, accessibility impact on rents
- Local amenities and employment center effects
- **Location-based rental premiums/discounts**

## 5. Competitive Positioning
- Properties with superior/inferior features and their premiums/discounts
- Market gaps and positioning opportunities
- **Strategic rental positioning recommendations**

## 6. Per-Unit Rent Recommendations
- **Individual Unit Rent Recommendations**: Specific dollar amounts for EACH unit by number and configuration
- Unit-specific factors affecting pricing
- Optimal lease terms and timing by unit type

## 7. Risk Assessment & Performance Projections
- Vacancy risk factors and competition analysis
- Economic sensitivity and regulatory risks
- **Quantified risk factors and market performance rankings**

# Output Requirements
- Include specific dollar amounts and percentages throughout
- Provide confidence levels for major recommendations
- Focus on actionable, investment-grade insights with clear professional formatting

Generate a data-driven analysis with specific, actionable rental pricing recommendations.
"""
        return prompt.strip()

    def _create_estimate_extraction_prompt(
        self, report: str, unit_configs: List[Dict[str, Any]]
    ) -> str:
        # Create unit-specific field descriptions
        unit_descriptions = []
        for config in unit_configs:
            for unit in config["units"]:
                unit_num = unit["unit_num"]
                config_key = config["config_key"]
                base_name = f"unit_{unit_num}_{config_key}"

                unit_descriptions.append(f"""
**Unit {unit_num} ({config['beds']}-bed {config['baths']}-bath)**:
- {base_name}_rent_estimate: Primary recommended monthly rent for this specific unit
- {base_name}_rent_estimate_high: Upper bound/optimistic rent for this unit
- {base_name}_rent_estimate_low: Lower bound/conservative rent for this unit""")

        unit_instructions = "\n".join(unit_descriptions)

        prompt = f"""
Analyze the following rental market research report and extract specific per-unit rent estimates for each individual unit in the property.

# Research Report to Analyze:
{report}

# Unit Configuration:
This property has the following units that need individual rent estimates:
{unit_instructions}

# Extraction Instructions:
You must provide rent estimates for EACH individual unit listed above. Each unit should have three values:
1. **Primary Estimate (_rent_estimate)**: The most recommended monthly rent for that specific unit
2. **High Estimate (_rent_estimate_high)**: Upper bound/optimistic rent for that unit
3. **Low Estimate (_rent_estimate_low)**: Lower bound/conservative rent for that unit

# Analysis Requirements:
- Provide only numeric values for monthly rental amounts (no dollar signs or commas)
- Extract per-unit estimates, NOT total property rent
- If the report provides unit-specific recommendations, use those directly
- If the report only provides total or average rents, intelligently allocate based on:
  * Unit size (bedrooms/bathrooms)
  * Typical market premiums for larger units
  * Any unit-specific factors mentioned in the report
- If ranges are provided (e.g., "$2,400-$2,800"), use the middle as _rent_estimate, upper as _rent_estimate_high, lower as _rent_estimate_low
- If only one estimate is provided, create a reasonable range (±5-10% for high/low estimates)
- Use your judgment based on comparable properties and market data in the report

# Context for Analysis:
- Focus on the most data-driven recommendations in the report
- Prioritize estimates supported by comparable property analysis
- Consider market conditions, property features, and location factors
- Account for differences between unit configurations when allocating rents
- If units have the same configuration, they should have similar (but not necessarily identical) rents
"""
        return prompt.strip()

    def _analyze_with_reasoning_model(self, prompt: str) -> Dict[str, Any]:
        try:
            response = self.openai_client.chat.completions.create(
                model=self.config.reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=self.config.max_tokens,
            )

            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            return {
                "content": content,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "success": True,
            }

        except Exception as e:
            return {
                "content": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "success": False,
                "error": str(e),
            }

    def _generate_rent_estimates_with_reasoning_model(
        self, prompt: str, response_format_model
    ) -> Dict[str, Any]:
        """Generate rent estimates using structured outputs with Pydantic"""
        try:
            response = self.openai_client.beta.chat.completions.parse(
                model=self.config.reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                response_format=response_format_model,
                max_completion_tokens=4000,
            )

            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Check for refusal
            if response.choices[0].message.refusal:
                return {
                    "estimates": None,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "success": False,
                    "error": f"Model refused to generate estimates: {response.choices[0].message.refusal}",
                }

            # Get the parsed result
            estimates = response.choices[0].message.parsed
            if estimates:
                # Convert the dynamic model to a dictionary
                estimates_dict = estimates.model_dump()
                return {
                    "estimates": estimates_dict,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "success": True,
                }
            else:
                return {
                    "estimates": None,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "success": False,
                    "error": "Failed to parse structured response",
                }

        except Exception as e:
            return {
                "estimates": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "success": False,
                "error": f"API call failed: {str(e)}",
            }

    def _sanitize_content(self, content: str) -> str:
        """Sanitize content to remove problematic characters for PostgreSQL storage"""
        if not content:
            return content
            
        try:
            # Remove null bytes which cause PostgreSQL errors
            sanitized = content.replace('\u0000', '')
            
            # Remove other problematic control characters except common whitespace
            sanitized = ''.join(char for char in sanitized 
                              if ord(char) >= 32 or char in '\n\r\t')
            
            # Ensure valid UTF-8 encoding
            sanitized = sanitized.encode('utf-8', errors='ignore').decode('utf-8')
            
            return sanitized
            
        except Exception as e:
            self.console.print(f"[yellow]Warning: Content sanitization failed: {str(e)}[/yellow]")
            # Fallback: return empty string if sanitization fails completely
            return ""

    def _store_report(
        self,
        property_id: str,
        report_content: str,
        prompt_used: str,
        cost: Decimal,
        status: str = "completed",
    ) -> Optional[str]:
        """Store the research report in the database"""

        try:
            # Sanitize content to prevent PostgreSQL Unicode errors
            sanitized_content = self._sanitize_content(report_content)
            sanitized_prompt = self._sanitize_content(prompt_used)
            
            # Log if significant content was removed during sanitization
            if len(sanitized_content) < len(report_content) * 0.9:
                self.console.print(f"[yellow]Warning: Significant content removed during sanitization for {property_id}[/yellow]")
            
            result = (
                self.supabase.table("research_reports")
                .insert(
                    {
                        "property_id": property_id,
                        "report_content": sanitized_content,
                        "prompt_used": sanitized_prompt,
                        "status": status,
                        "api_cost": float(cost),
                        "research_type": "rental_comparison",
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    }
                )
                .execute()
            )

            if result.data:
                return result.data[0]["id"]
            return None

        except Exception as e:
            # Enhanced error logging to help with debugging
            error_details = {
                'message': getattr(e, 'message', str(e)),
                'code': getattr(e, 'code', 'Unknown'),
                'hint': getattr(e, 'hint', None),
                'details': getattr(e, 'details', None)
            }
            self.console.print(f"[red]Error storing report: {error_details}[/red]")
            return None

    def generate_rent_research(self, property_id: str) -> Optional[str]:
        try:
            property_response = (
                self.supabase.table("properties")
                .select("*")
                .eq("address1", property_id)
                .single()
                .execute()
            )
            if not property_response.data:
                self.console.print(f"[red]Property not found: {property_id}[/red]")
                return None
            property_data = property_response.data
        except Exception as e:
            self.console.print(f"[red]Error fetching property data: {str(e)}[/red]")
            return None

        # Create progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                "[cyan]Initializing rental research...", total=None
            )

            # Generate search queries
            progress.update(task, description="[cyan]Generating search queries...")
            queries = self._generate_search_queries(property_data)

            # Perform web searches
            progress.update(
                task,
                description=f"[cyan]Searching market data ({len(queries)} queries)...",
            )
            search_results = self._perform_searches(queries)

            if not search_results:
                progress.update(task, description="[red]No search results found!")
                self.console.print("[red]No market data found for analysis.[/red]")
                self._store_report(
                    property_id,
                    "No market data found for analysis",
                    "NA",
                    Decimal("0.0000"),
                    "failed",
                )
                return None

            progress.update(
                task,
                description=f"[cyan]Deep reasoning analysis with {self.config.reasoning_model} ({len(search_results)} data points)...",
            )

            # Get unit configurations for more detailed analysis
            unit_configs = self._get_unit_configurations(property_id)

            analysis_prompt = self._create_analysis_prompt(
                property_data, search_results, unit_configs
            )
            result = self._analyze_with_reasoning_model(analysis_prompt)

            if not result["success"]:
                progress.update(task, description="[red]Analysis failed!")
                error_msg = result.get("error", "Unknown error")
                self.console.print(f"[red]Analysis failed: {error_msg}[/red]")
                self._store_report(
                    property_id,
                    f"Analysis failed: {error_msg}",
                    analysis_prompt,
                    Decimal("0.0000"),
                    "failed",
                )
                return None

            # Calculate total cost
            num_searches = len(queries)
            cost = self._calculate_cost(
                num_searches, result["input_tokens"], result["output_tokens"]
            )

            progress.update(task, description="[green]Storing research report...")

            # Store successful report
            report_id = self._store_report(property_id, result["content"], analysis_prompt, cost)

            progress.update(task, description="[green]Research completed successfully!")

            # Display cost information
            search_cost = num_searches * self.config.search_cost_per_query
            reasoning_cost = cost - Decimal(str(search_cost))

            self.console.print(
                Panel(
                    f"[green]Research completed successfully![/green]\n\n"
                    f"**Market Data Sources**: {len(search_results)} data points from {num_searches} searches\n"
                    f"**Reasoning Tokens**: {result['input_tokens']:,} input, {result['output_tokens']:,} output\n"
                    f"**Search Cost**: ${search_cost:.4f} ({num_searches} × $0.008)\n"
                    f"**o1-mini Reasoning Cost**: ${reasoning_cost:.4f}\n"
                    f"**Total API Cost**: ${cost:.4f}\n"
                    f"**Report ID**: {report_id}",
                    title="Research Summary",
                    border_style="green",
                )
            )

            return report_id

    def generate_rent_estimates_from_report(self, report_id: str) -> Dict[str, Any]:
        """Generate rent estimates from an existing research report"""
        try:
            result = (
                self.supabase.table("research_reports")
                .select("*")
                .eq("id", report_id)
                .single()
                .execute()
            )
            if not result.data:
                return {
                    "success": False,
                    "error": f"Report not found: {report_id}",
                    "estimates": None,
                    "cost": 0,
                }
        except Exception as e:
            self.console.print(
                f"[red]Error fetching report {report_id}: {str(e)}[/red]"
            )
            return {
                "success": False,
                "error": f"Database error: {str(e)}",
                "estimates": None,
                "cost": 0,
            }

        report_content = result.data["report_content"]
        property_id = result.data["property_id"]

        if not report_content:
            return {
                "success": False,
                "error": "Report has no content",
                "estimates": None,
                "cost": 0,
            }

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        ) as progress:
            progress.add_task(
                "[cyan]Generating rental estimates from report...", total=None
            )

            # Get unit configurations for this property
            unit_configs = self._get_unit_configurations(property_id)
            if not unit_configs:
                return {
                    "success": False,
                    "error": f"No unit configurations found for property {property_id}",
                    "estimates": None,
                    "cost": 0,
                }

            # Create dynamic Pydantic model
            dynamic_model = self._create_dynamic_rent_model(unit_configs)

            # Create the extraction prompt with unit configurations
            extraction_prompt = self._create_estimate_extraction_prompt(
                report_content, unit_configs
            )

            # Generate estimates using the reasoning model with dynamic response format
            extraction_result = self._generate_rent_estimates_with_reasoning_model(
                extraction_prompt, dynamic_model
            )

            if extraction_result["success"]:
                # Calculate cost for this operation
                reasoning_cost = self._calculate_cost(
                    0,
                    extraction_result["input_tokens"],
                    extraction_result["output_tokens"],
                )

                # Get existing estimates for comparison
                existing_estimates = self._get_existing_estimates(
                    property_id, unit_configs
                )

                # Create summary for display
                unit_count = sum(len(config["units"]) for config in unit_configs)

                self.console.print(
                    Panel(
                        f"[green]Per-unit rent estimates generated successfully![/green]\n\n"
                        f"Reasoning Tokens: {extraction_result['input_tokens']:,} input, {extraction_result['output_tokens']:,} output\n"
                        f"API Cost: ${reasoning_cost:.4f}\n"
                        f"Units Processed: {unit_count} individual units\n"
                        f"Database Updates: Manual confirmation required",
                        title="Per-Unit Estimate Generation Summary",
                        border_style="green",
                    )
                )

                return {
                    "success": True,
                    "estimates": extraction_result["estimates"],
                    "existing_estimates": existing_estimates,
                    "unit_configs": unit_configs,
                    "cost": float(reasoning_cost),
                    "tokens_used": {
                        "input": extraction_result["input_tokens"],
                        "output": extraction_result["output_tokens"],
                    },
                }
            else:
                self.console.print(
                    f"[red]Failed to generate estimates: {extraction_result['error']}[/red]"
                )
                return {
                    "success": False,
                    "error": extraction_result["error"],
                    "estimates": None,
                    "cost": 0,
                }

        return {
            "success": False,
            "error": "Unknown error occurred",
            "estimates": None,
            "cost": 0,
        }

    def display_report(self, report_content: str):
        # Create markdown object
        markdown = Markdown(report_content)

        with self.console.pager(styles=True):
            self.console.print(
                Panel(
                    markdown,
                    title="[bold cyan]Rental Market Research Report[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

    def get_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        try:
            result = (
                self.supabase.table("research_reports")
                .select("*")
                .eq("id", report_id)
                .single()
                .execute()
            )
            return result.data
        except Exception as e:
            self.console.print(f"[red]Error fetching report: {str(e)}[/red]")
            return None

    def get_reports_for_property(self, property_id: str) -> list:
        try:
            result = (
                self.supabase.table("research_reports")
                .select("*")
                .eq("property_id", property_id)
                .order("created_at", desc=True)
                .execute()
            )
            return result.data
        except Exception as e:
            self.console.print(f"[red]Error fetching reports: {str(e)}[/red]")
            return []

    def _get_unit_configurations(self, property_id: str) -> List[Dict[str, Any]]:
        """Fetch unit configurations from rent_estimates table for the property"""
        try:
            result = (
                self.supabase.table("rent_estimates")
                .select("*")
                .eq("address1", property_id)
                .execute()
            )
            if not result.data:
                return []

            # Group units by configuration and count them
            unit_configs = []
            config_map = {}

            for unit in result.data:
                beds = int(unit.get("beds", 0))
                baths = int(unit.get("baths", 0))
                config_key = f"{beds}bed_{baths}bath"

                if config_key not in config_map:
                    config_map[config_key] = {
                        "beds": beds,
                        "baths": baths,
                        "config_key": config_key,
                        "units": [],
                    }

                config_map[config_key]["units"].append(
                    {"unit_num": int(unit.get("unit_num", 1)), "id": unit.get("id")}
                )

            # Convert to list format
            for config in config_map.values():
                config["unit_count"] = len(config["units"])
                unit_configs.append(config)

            return unit_configs

        except Exception as e:
            self.console.print(
                f"[red]Error fetching unit configurations: {str(e)}[/red]"
            )
            return []

    def _get_existing_estimates(
        self, property_id: str, unit_configs: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, float]]:
        """Fetch existing rent estimates from the database for comparison"""
        try:
            result = (
                self.supabase.table("rent_estimates")
                .select("*")
                .eq("address1", property_id)
                .execute()
            )
            if not result.data:
                return {}

            existing_estimates = {}

            for unit_data in result.data:
                unit_num = int(unit_data.get("unit_num", 1))
                beds = int(unit_data.get("beds", 0))
                baths = int(unit_data.get("baths", 0))
                config_key = f"{beds}bed_{baths}bath"
                base_name = f"unit_{unit_num}_{config_key}"

                existing_estimates[base_name] = {
                    "rent_estimate": float(unit_data.get("rent_estimate") or 0),
                    "rent_estimate_high": float(
                        unit_data.get("rent_estimate_high") or 0
                    ),
                    "rent_estimate_low": float(unit_data.get("rent_estimate_low") or 0),
                    "unit_id": unit_data.get("id"),
                }

            return existing_estimates

        except Exception as e:
            self.console.print(
                f"[red]Error fetching existing estimates: {str(e)}[/red]"
            )
            return {}

    def _update_rent_estimates_in_db(
        self,
        property_id: str,
        unit_configs: List[Dict[str, Any]],
        estimates_dict: Dict[str, float],
    ) -> bool:
        """Update the rent_estimates table with per-unit results"""
        self.console.print("\n[bold cyan]🔄 Starting database updates...[/bold cyan]")

        try:
            success_count = 0
            total_updates = 0
            failed_units = []

            for config in unit_configs:
                for unit in config["units"]:
                    unit_num = unit["unit_num"]
                    unit_id = unit["id"]
                    config_key = config["config_key"]
                    base_name = f"unit_{unit_num}_{config_key}"

                    # Log which unit we're processing
                    self.console.print(
                        f"[cyan]📝 Processing Unit {unit_num} ({config['beds']}bed-{config['baths']}bath)...[/cyan]"
                    )

                    # Extract the estimates for this unit
                    rent_estimate = estimates_dict.get(f"{base_name}_rent_estimate")
                    rent_estimate_high = estimates_dict.get(
                        f"{base_name}_rent_estimate_high"
                    )
                    rent_estimate_low = estimates_dict.get(
                        f"{base_name}_rent_estimate_low"
                    )

                    if (
                        rent_estimate is not None
                        and rent_estimate_high is not None
                        and rent_estimate_low is not None
                    ):
                        try:
                            # Convert to integers to fix database type error
                            # Round to nearest dollar since rent estimates are typically whole numbers
                            rent_estimate_int = int(round(float(rent_estimate)))
                            rent_estimate_high_int = int(
                                round(float(rent_estimate_high))
                            )
                            rent_estimate_low_int = int(round(float(rent_estimate_low)))

                            self.console.print(
                                f"   [blue]Updating: ${rent_estimate_int} (${rent_estimate_low_int}-${rent_estimate_high_int})[/blue]"
                            )

                            # Update the database record
                            result = (
                                self.supabase.table("rent_estimates")
                                .update(
                                    {
                                        "rent_estimate": rent_estimate_int,
                                        "rent_estimate_high": rent_estimate_high_int,
                                        "rent_estimate_low": rent_estimate_low_int,
                                    }
                                )
                                .eq("id", unit_id)
                                .execute()
                            )

                            if result.data:
                                success_count += 1
                                self.console.print(
                                    f"   [green]✅ Unit {unit_num} updated successfully[/green]"
                                )
                            else:
                                failed_units.append(
                                    f"Unit {unit_num} (no data returned)"
                                )
                                self.console.print(
                                    f"   [red]❌ Unit {unit_num} update failed (no data returned)[/red]"
                                )
                            total_updates += 1

                        except ValueError as ve:
                            failed_units.append(
                                f"Unit {unit_num} (value error: {str(ve)})"
                            )
                            self.console.print(
                                f"   [red]❌ Unit {unit_num} value conversion error: {str(ve)}[/red]"
                            )
                            total_updates += 1
                        except Exception as ue:
                            failed_units.append(
                                f"Unit {unit_num} (update error: {str(ue)})"
                            )
                            self.console.print(
                                f"   [red]❌ Unit {unit_num} database error: {str(ue)}[/red]"
                            )
                            total_updates += 1
                    else:
                        missing_fields = []
                        if rent_estimate is None:
                            missing_fields.append("rent_estimate")
                        if rent_estimate_high is None:
                            missing_fields.append("rent_estimate_high")
                        if rent_estimate_low is None:
                            missing_fields.append("rent_estimate_low")

                        failed_units.append(
                            f"Unit {unit_num} (missing: {', '.join(missing_fields)})"
                        )
                        self.console.print(
                            f"   [yellow]⚠️  Unit {unit_num} skipped - missing: {', '.join(missing_fields)}[/yellow]"
                        )
                        total_updates += 1

            # Final summary
            self.console.print("\n[bold cyan]📊 Database Update Summary:[/bold cyan]")
            if success_count == total_updates:
                self.console.print(
                    f"[green]✅ All {success_count}/{total_updates} units updated successfully[/green]"
                )
                return True
            else:
                self.console.print(
                    f"[yellow]⚠️  {success_count}/{total_updates} units updated successfully[/yellow]"
                )
                if failed_units:
                    self.console.print("[red]Failed units:[/red]")
                    for failed_unit in failed_units:
                        self.console.print(f"   [red]• {failed_unit}[/red]")
                return False

        except Exception as e:
            self.console.print(
                f"[red]💥 Critical error updating rent estimates in database: {str(e)}[/red]"
            )
            return False

    def _create_dynamic_rent_model(self, unit_configs: List[Dict[str, Any]]):
        """Create a dynamic Pydantic model based on unit configurations"""
        fields = {}

        for config in unit_configs:
            config_key = config["config_key"]

            # For each unit in this configuration
            for i, unit in enumerate(config["units"]):
                unit_num = unit["unit_num"]

                # Create field names for this specific unit
                base_name = f"unit_{unit_num}_{config_key}"

                fields[f"{base_name}_rent_estimate"] = (float, ...)
                fields[f"{base_name}_rent_estimate_high"] = (float, ...)
                fields[f"{base_name}_rent_estimate_low"] = (float, ...)

        # Create and return the dynamic model
        DynamicRentEstimates = create_model("DynamicRentEstimates", **fields)
        return DynamicRentEstimates
