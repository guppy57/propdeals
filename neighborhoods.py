import os
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import openai
import pandas as pd
import requests
from pydantic import BaseModel
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from supabase import Client
from tavily import TavilyClient
from helpers import normalize_neighborhood_name

@dataclass
class NeighborhoodResearchConfig:
    """Configuration for neighborhood research operations"""

    reasoning_model: str = "gpt-5.1"
    instant_model: str = "gpt-5-nano"
    effort: str = "high"
    max_tokens: int = 120000
    search_cost_per_query: float = 0.008  # Tavily cost
    reasoning_cost_per_input_token: float = 1.25 / 1000000
    reasoning_cost_per_output_token: float = 10 / 1000000
    searches_per_neighborhood: int = 6


class NeighborhoodLetterGrade(BaseModel):
    """Pydantic model for neighborhood letter grade extraction"""
    letter_grade: str
    confidence_score: float


class NeighborhoodsClient():
    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console
        self.config = NeighborhoodResearchConfig()

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

    def is_neighborhood_assessment_complete(self, address1: str) -> bool:
        return False
    
    def get_or_create_neighborhood(self, neighborhood_name, supabase):
        """
        Get existing neighborhood ID or create a new neighborhood.
        Uses normalized name for both lookup and storage to ensure consistency.

        Args:
            neighborhood_name: Original neighborhood name from geocoding
            supabase: Supabase client instance

        Returns:
            Tuple of (neighborhood_id, was_created) where was_created is True if newly created
            Returns (None, False) if error
        """
        # Normalize for lookup and storage
        normalized_name = normalize_neighborhood_name(neighborhood_name)
        if not normalized_name:
            return None, False

        try:
            # Check if neighborhood exists in database (exact match on normalized name)
            response = supabase.table('neighborhoods')\
                .select('id, name')\
                .eq('name', normalized_name)\
                .limit(1)\
                .execute()

            if response.data and len(response.data) > 0:
                # Neighborhood exists, return ID
                neighborhood_id = response.data[0]['id']
                return neighborhood_id, False

            # Neighborhood doesn't exist, create it
            insert_response = supabase.table('neighborhoods').insert(
                {'name': normalized_name}
            ).execute()

            if insert_response.data and len(insert_response.data) > 0:
                neighborhood_id = insert_response.data[0]['id']
                return neighborhood_id, True

            return None, False

        except Exception as e:
            self.console.print(f"[red]Error creating/fetching neighborhood '{normalized_name}': {e}[/red]")
            return None, False

    def assign_neighborhood_to_property(self, property_id, neighborhood_id):
        existing_assignment = (
            self.supabase.table("property_neighborhood")
            .select("*")
            .eq("address1", property_id)
            # .eq("neighborhood_id", neighborhood_id)
            .execute()
        )

        if not existing_assignment.data or len(existing_assignment.data) == 0:
            # this property does NOT have any neighborhood assigned to it
            self.supabase.table("property_neighborhood").insert(
                {"address1": property_id, "neighborhood_id": neighborhood_id}
            ).execute()
            return "NEWLY_ASSIGNED"
        else:
            # this property has SOME neighborhood assigned to it
            existing_neighborhood_id = existing_assignment.data[0].get("neighborhood_id")
            if existing_neighborhood_id == neighborhood_id:
                return "ALREADY_ASSIGNED"
            else:
                # change the neighborhood_id on the EXISTING record
                self.supabase.table("property_neighborhood").update({'neighborhood_id': neighborhood_id}).eq('address1', property_id).execute()
                return "NEWLY_ASSIGNED"

    def assign_neighborhood_to_property_using_geocoding(
        self, address1: str, full_address: str
    ) -> Optional[str]:
        """
        Assign a neighborhood to a property using geocoding.

        Args:
            address1: Property address identifier
            full_address: Full address string for geocoding

        Returns:
            Neighborhood name if successful, None otherwise
        """
        try:
            # Get geocode data
            self.console.print(f"[cyan]Getting geocode data for: {full_address}[/cyan]")
            response = requests.get(
                "https://maps.googleapis.com/maps/api/geocode/json",
                params={
                    "key": os.getenv("GOOGLE_KEY"),
                    "address": full_address,
                },
            )

            data = response.json()
            neighborhood = None

            if not data.get("results"):
                self.console.print("[red]No geocode results found for address[/red]")
            else:
                # Extract neighborhood from geocode
                address_components = data["results"][0]["address_components"]

                for component in address_components:
                    if "neighborhood" in component["types"]:
                        neighborhood = component["long_name"]
                        break

                if neighborhood:
                    self.console.print(
                        f"[green]Found neighborhood: {neighborhood}[/green]"
                    )
                else:
                    self.console.print(
                        "[yellow]No neighborhood found in geocode results[/yellow]"
                    )

            # If geocoding failed or no neighborhood found, offer manual input
            if not neighborhood:
                should_enter_manually = Confirm.ask(
                    "[cyan]Would you like to enter a neighborhood name manually?[/cyan]",
                    default=True,
                )

                if should_enter_manually:
                    neighborhood = Prompt.ask(
                        "[cyan]Enter neighborhood name[/cyan]"
                    ).strip()

                    if not neighborhood:
                        self.console.print("[red]No neighborhood name provided[/red]")
                        return None

                    self.console.print(
                        f"[green]Using manually entered neighborhood: {neighborhood}[/green]"
                    )
                else:
                    self.console.print(
                        "[yellow]Neighborhood assignment cancelled[/yellow]"
                    )
                    return None

            normalized_name = normalize_neighborhood_name(neighborhood)
            if not normalized_name:
                return None

            # Get or create neighborhood in database
            neighborhood_response = (
                self.supabase.table("neighborhoods")
                .select("id, name")
                .eq("name", normalized_name)
                .limit(1)
                .execute()
            )

            if neighborhood_response.data and len(neighborhood_response.data) > 0:
                neighborhood_id = neighborhood_response.data[0]["id"]
                self.console.print(
                    f"[green]Using existing neighborhood: {normalized_name}[/green]"
                )
            else:
                # Create new neighborhood
                insert_response = (
                    self.supabase.table("neighborhoods")
                    .insert({"name": normalized_name})
                    .execute()
                )

                if insert_response.data and len(insert_response.data) > 0:
                    neighborhood_id = insert_response.data[0]["id"]
                    self.console.print(
                        f"[green]Created new neighborhood: {normalized_name}[/green]"
                    )
                else:
                    self.console.print("[red]Failed to create neighborhood[/red]")
                    return None

            # Check if relationship already exists
            existing_relationship = (
                self.supabase.table("property_neighborhood")
                .select("*")
                .eq("neighborhood_id", neighborhood_id)
                .eq("address1", address1)
                .limit(1)
                .execute()
            )

            if existing_relationship.data and len(existing_relationship.data) > 0:
                self.console.print(
                    "[yellow]Property-neighborhood relationship already exists[/yellow]"
                )
            else:
                # Create the relationship
                relationship_response = (
                    self.supabase.table("property_neighborhood")
                    .insert({"neighborhood_id": neighborhood_id, "address1": address1})
                    .execute()
                )

                if relationship_response.data:
                    self.console.print(
                        "[green]✓ Created property-neighborhood relationship[/green]"
                    )
                else:
                    self.console.print(
                        "[yellow]Warning: Failed to create property-neighborhood relationship[/yellow]"
                    )
                    return None

            return normalized_name

        except Exception as e:
            self.console.print(f"[red]Error assigning neighborhood: {str(e)}[/red]")

            # Offer manual input as fallback when exception occurs
            should_enter_manually = Confirm.ask(
                "[cyan]Would you like to enter a neighborhood name manually instead?[/cyan]",
                default=True,
            )

            if not should_enter_manually:
                return None

            neighborhood = Prompt.ask("[cyan]Enter neighborhood name[/cyan]").strip()

            if not neighborhood:
                self.console.print("[red]No neighborhood name provided[/red]")
                return None

            normalized_name = normalize_neighborhood_name(neighborhood)
            if not normalized_name:
                self.console.print("[red]Invalid neighborhood name[/red]")
                return None

            try:
                # Get or create neighborhood in database
                neighborhood_response = (
                    self.supabase.table("neighborhoods")
                    .select("id, name")
                    .eq("name", normalized_name)
                    .limit(1)
                    .execute()
                )

                if neighborhood_response.data and len(neighborhood_response.data) > 0:
                    neighborhood_id = neighborhood_response.data[0]["id"]
                    self.console.print(
                        f"[green]Using existing neighborhood: {normalized_name}[/green]"
                    )
                else:
                    # Create new neighborhood
                    insert_response = (
                        self.supabase.table("neighborhoods")
                        .insert({"name": normalized_name})
                        .execute()
                    )

                    if insert_response.data and len(insert_response.data) > 0:
                        neighborhood_id = insert_response.data[0]["id"]
                        self.console.print(
                            f"[green]Created new neighborhood: {normalized_name}[/green]"
                        )
                    else:
                        self.console.print("[red]Failed to create neighborhood[/red]")
                        return None

                # Create the relationship
                relationship_response = (
                    self.supabase.table("property_neighborhood")
                    .insert({"neighborhood_id": neighborhood_id, "address1": address1})
                    .execute()
                )

                if relationship_response.data:
                    self.console.print(
                        "[green]✓ Created property-neighborhood relationship[/green]"
                    )
                    return normalized_name
                else:
                    self.console.print(
                        "[red]Failed to create property-neighborhood relationship[/red]"
                    )
                    return None

            except Exception as db_error:
                self.console.print(f"[red]Database error: {str(db_error)}[/red]")
                return None

    def has_neighborhood_analysis(self, neighborhood_name: str) -> bool:
        """
        Check if a completed neighborhood analysis report exists for a given neighborhood.

        Args:
            neighborhood_name: Name of the neighborhood to check

        Returns:
            True if a completed neighborhood report exists, False otherwise
        """
        # Handle None or empty neighborhood name
        if not neighborhood_name or not isinstance(neighborhood_name, str):
            return False

        try:
            # Check if completed neighborhood report exists for this neighborhood
            report_response = (
                self.supabase.table("research_reports")
                .select("id")
                .eq("research_type", f"{neighborhood_name}_neighborhood_report")
                .eq("status", "completed")
                .limit(1)
                .execute()
            )

            return bool(report_response.data and len(report_response.data) > 0)

        except Exception as e:
            # Log error but return False to indicate no completed report
            self.console.print(
                f"[yellow]Warning: Error checking neighborhood analysis for '{neighborhood_name}': {str(e)}[/yellow]"
            )
            return False

    def has_neighborhood_analysis_batch(
        self, neighborhood_names: List[str]
    ) -> Dict[str, bool]:
        """
        Batch check if completed neighborhood analysis reports exist for multiple neighborhoods.
        This is significantly more efficient than calling has_neighborhood_analysis() in a loop.

        Args:
            neighborhood_names: List of neighborhood names to check

        Returns:
            Dictionary mapping neighborhood name -> bool (True if completed report exists)
        """
        # Initialize result dictionary with False for all neighborhoods
        result = {}

        # Filter out None/empty neighborhoods upfront
        valid_neighborhoods = [
            name for name in neighborhood_names if name and isinstance(name, str)
        ]

        # Initialize all as False (including invalid ones)
        for name in neighborhood_names:
            result[name] = False

        if not valid_neighborhoods:
            return result

        try:
            # Build list of research_type values to check
            research_types = [
                f"{name}_neighborhood_report" for name in valid_neighborhoods
            ]

            # Single query to check all neighborhoods at once
            # Using .in_() to match any of the research types
            report_response = (
                self.supabase.table("research_reports")
                .select("research_type")
                .in_("research_type", research_types)
                .eq("status", "completed")
                .execute()
            )

            # Create set of neighborhoods that have completed reports
            # Extract neighborhood name from "neighborhood_name_neighborhood_report" format
            completed_neighborhoods = {
                report["research_type"].replace("_neighborhood_report", "")
                for report in report_response.data
            }

            # Update result dictionary for neighborhoods with completed reports
            for name in valid_neighborhoods:
                result[name] = name in completed_neighborhoods

        except Exception as e:
            self.console.print(
                f"[yellow]Warning: Error batch checking neighborhood analyses: {str(e)}[/yellow]"
            )
            # Keep all as False on error

        return result

    def is_neighborhood_assessment_complete_batch(
        self, address1_list: List[str]
    ) -> Dict[str, bool]:
        """
        Batch check if neighborhood assessments are complete for multiple properties.

        Args:
            address1_list: List of property addresses to check

        Returns:
            Dictionary mapping address1 -> bool (currently always False)
        """
        # For now, return False for all addresses
        return {address: False for address in address1_list}

    def get_neighborhoods_dataframe(self, supabase):
        """
        Fetch neighborhoods for all properties from the property_neighborhood many-to-many table.

        Args:
            supabase: Supabase client instance

        Returns:
            pandas DataFrame with columns: address1, neighborhood
            Properties without neighborhoods will not be in the dataframe (handled by left merge)
        """
        try:
            response = (
                supabase.table("property_neighborhood")
                .select("address1, neighborhoods(name, letter_grade)")
                .execute()
            )

            if not response.data:
                return pd.DataFrame(
                    columns=["address1", "neighborhood", "neighborhood_letter_grade"]
                )

            neighborhoods_df = pd.DataFrame(response.data)

            if "neighborhoods" in neighborhoods_df.columns:
                neighborhoods_df["neighborhood"] = neighborhoods_df[
                    "neighborhoods"
                ].apply(
                    lambda x: x["name"]
                    if x and isinstance(x, dict) and "name" in x
                    else None
                )
                neighborhoods_df["neighborhood_letter_grade"] = neighborhoods_df[
                    "neighborhoods"
                ].apply(
                    lambda x: x["letter_grade"]
                    if x and isinstance(x, dict) and "letter_grade" in x
                    else None
                )
                neighborhoods_df = neighborhoods_df[
                    ["address1", "neighborhood", "neighborhood_letter_grade"]
                ]
            else:
                return pd.DataFrame(
                    columns=["address1", "neighborhood", "neighborhood_letter_grade"]
                )

            neighborhoods_df = neighborhoods_df.dropna(subset=["neighborhood"])
            return neighborhoods_df

        except Exception as e:
            print(f"Error fetching neighborhoods: {e}")
            # Return empty dataframe on error
            return pd.DataFrame(
                columns=["address1", "neighborhood", "neighborhood_letter_grade"]
            )
    
    def get_neighborhood_for_property(self, address1, supabase):
        try:
            response = (
                supabase.table("property_neighborhood")
                .select("neighborhoods(name)")
                .eq("address1", address1)
                .limit(1)
                .execute()
            )

            if not response.data or len(response.data) == 0:
                return None

            # Access list first, then nested dict
            neighborhood_dict = response.data[0].get("neighborhoods")
            if (
                not neighborhood_dict
                or not isinstance(neighborhood_dict, dict)
                or "name" not in neighborhood_dict
            ):
                return None

            return neighborhood_dict["name"]
        except Exception as e:
            print(f"Error fetching neighborhood for property {address1}: {e}")
            return None

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

    def _generate_neighborhood_search_queries(
        self, neighborhood: str, city: str
    ) -> List[str]:
        """Generate targeted search queries for neighborhood analysis"""
        NEIGHBORHOOD_SEARCH_QUERIES = [
            f"{neighborhood} {city} crime rate statistics",
            f"{neighborhood} {city} real estate market trends 2024 2025",
            f"{neighborhood} {city} rental rates vacancy",
            f"{neighborhood} {city} demographics median income",
            f"{neighborhood} {city} development projects news",
            f"{neighborhood} {city} major employers nearby",
        ]
        return NEIGHBORHOOD_SEARCH_QUERIES

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

    def _analyze_with_reasoning_model(self, prompt: str) -> Dict[str, Any]:
        """Analyze data using OpenAI's reasoning model"""
        try:
            response = self.openai_client.chat.completions.create(
                model=self.config.reasoning_model,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=self.config.max_tokens,
                reasoning_effort=self.config.effort,
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

    def _extract_letter_grade_with_reasoning_model(self, prompt: str) -> Dict[str, Any]:
        """Extract letter grade using structured outputs with Pydantic"""
        try:
            response = self.openai_client.beta.chat.completions.parse(
                model=self.config.instant_model,
                messages=[{"role": "user", "content": prompt}],
                response_format=NeighborhoodLetterGrade,
                max_completion_tokens=4000,
            )

            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens

            # Check for refusal
            if response.choices[0].message.refusal:
                return {
                    "grade": None,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "success": False,
                    "error": f"Model refused to extract grade: {response.choices[0].message.refusal}",
                }

            # Get the parsed result
            grade_data = response.choices[0].message.parsed
            if grade_data:
                return {
                    "grade": grade_data.letter_grade,
                    "confidence_score": grade_data.confidence_score,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "success": True,
                }
            else:
                return {
                    "grade": None,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "success": False,
                    "error": "Failed to parse structured response",
                }

        except Exception as e:
            return {
                "grade": None,
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
            sanitized = content.replace("\u0000", "")

            # Remove other problematic control characters except common whitespace
            sanitized = "".join(
                char for char in sanitized if ord(char) >= 32 or char in "\n\r\t"
            )

            # Ensure valid UTF-8 encoding
            sanitized = sanitized.encode("utf-8", errors="ignore").decode("utf-8")

            return sanitized

        except Exception as e:
            self.console.print(
                f"[yellow]Warning: Content sanitization failed: {str(e)}[/yellow]"
            )
            # Fallback: return empty string if sanitization fails completely
            return ""

    def _store_report(
        self,
        property_id: str,
        neighborhood_name: str,
        report_content: str,
        prompt_used: str,
        cost: Decimal,
        status: str = "completed",
    ) -> Optional[str]:
        """Store the neighborhood research report in the database"""
        try:
            # Sanitize content to prevent PostgreSQL Unicode errors
            sanitized_content = self._sanitize_content(report_content)
            sanitized_prompt = self._sanitize_content(prompt_used)

            # Log if significant content was removed during sanitization
            if len(sanitized_content) < len(report_content) * 0.9:
                self.console.print(
                    f"[yellow]Warning: Significant content removed during sanitization for {property_id}[/yellow]"
                )

            result = (
                self.supabase.table("research_reports")
                .insert(
                    {
                        "property_id": property_id,
                        "report_content": sanitized_content,
                        "prompt_used": sanitized_prompt,
                        "status": status,
                        "api_cost": float(cost),
                        "research_type": f"{neighborhood_name}_neighborhood_report",
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
                "message": getattr(e, "message", str(e)),
                "code": getattr(e, "code", "Unknown"),
                "hint": getattr(e, "hint", None),
                "details": getattr(e, "details", None),
            }
            self.console.print(f"[red]Error storing report: {error_details}[/red]")
            return None

    def generate_neighborhood_research(
        self, address1: str
    ) -> tuple[Optional[str], bool]:
        """
        Generate comprehensive neighborhood research report for a property.
        Checks for existing reports first to avoid regenerating for the same neighborhood.

        Args:
            address1: Property address (primary key)

        Returns:
            Tuple of (report_id, was_existing):
            - report_id: Report ID if successful, None if failed
            - was_existing: True if existing report was found, False if new report was generated
        """
        # Fetch property data
        try:
            property_response = (
                self.supabase.table("properties")
                .select("*")
                .eq("address1", address1)
                .single()
                .execute()
            )
            if not property_response.data:
                self.console.print(f"[red]Property not found: {address1}[/red]")
                return (None, False)
            property_data = property_response.data
        except Exception as e:
            self.console.print(f"[red]Error fetching property data: {str(e)}[/red]")
            return (None, False)

        # Get neighborhood from property_neighborhood table
        try:
            neighborhood_response = (
                self.supabase.table("property_neighborhood")
                .select("neighborhoods(name)")
                .eq("address1", address1)
                .limit(1)
                .execute()
            )

            # Check if neighborhood exists
            if not neighborhood_response.data or len(neighborhood_response.data) == 0:
                self.console.print(
                    f"[yellow]⚠️  No neighborhood assigned for property: {address1}[/yellow]"
                )
                self.console.print(
                    "[yellow]This property needs a neighborhood assignment before running neighborhood analysis.[/yellow]"
                )

                # Prompt user for action
                should_assign = Confirm.ask(
                    "[cyan]Would you like to automatically assign a neighborhood now using geocoding?[/cyan]",
                    default=True,
                )

                if should_assign:
                    # Attempt to assign neighborhood using geocoding
                    full_address = property_data.get("address1", "")
                    neighborhood_name = self.assign_neighborhood_to_property_using_geocoding(
                        address1, full_address
                    )

                    if not neighborhood_name:
                        self.console.print(
                            "[red]Failed to assign neighborhood. Please assign manually and try again.[/red]"
                        )
                        return (None, False)

                    self.console.print(
                        f"[green]✓ Successfully assigned neighborhood: {neighborhood_name}[/green]"
                    )
                    # Continue with analysis below
                else:
                    self.console.print(
                        "[yellow]Neighborhood analysis cancelled. Please assign a neighborhood manually and try again.[/yellow]"
                    )
                    return (None, False)
            else:
                # Neighborhood exists, extract it
                neighborhood_dict = neighborhood_response.data[0].get("neighborhoods")
                if (
                    not neighborhood_dict
                    or not isinstance(neighborhood_dict, dict)
                    or "name" not in neighborhood_dict
                ):
                    self.console.print(
                        "[red]Invalid neighborhood data structure[/red]"
                    )
                    return (None, False)

                neighborhood_name = neighborhood_dict["name"]

        except Exception as e:
            self.console.print(f"[red]Error fetching neighborhood: {str(e)}[/red]")
            return (None, False)

        # Check for existing neighborhood report
        try:
            existing_report = (
                self.supabase.table("research_reports")
                .select("id")
                .eq("research_type", f"{neighborhood_name}_neighborhood_report")
                .eq("status", "completed")
                .limit(1)
                .execute()
            )

            if existing_report.data and len(existing_report.data) > 0:
                existing_report_id = existing_report.data[0]["id"]
                self.console.print(
                    f"[green]✓ Existing neighborhood report found for '{neighborhood_name}'[/green]"
                )
                self.console.print(f"[cyan]Report ID: {existing_report_id}[/cyan]")
                return (existing_report_id, True)
        except Exception as e:
            self.console.print(
                f"[yellow]Warning: Could not check for existing reports: {str(e)}[/yellow]"
            )
            # Continue with new report generation

        # Extract city and state from property address
        full_address = property_data.get("address1", "")
        address_parts = full_address.split(",")

        # Try to extract city (usually second part after first comma)
        if len(address_parts) >= 2:
            city = address_parts[1].strip()
        else:
            city = "Des Moines"  # Default fallback

        # Try to extract state (usually last part)
        if len(address_parts) >= 3:
            state_zip = address_parts[2].strip()
            state = state_zip.split()[0] if state_zip else "IA"
        else:
            state = "IA"  # Default fallback

        # Create progress display
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True,
        ) as progress:
            task = progress.add_task(
                "[cyan]Initializing neighborhood research...", total=None
            )

            # Generate search queries
            progress.update(task, description="[cyan]Generating search queries...")
            queries = self._generate_neighborhood_search_queries(
                neighborhood_name, city
            )

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
                    address1,
                    neighborhood_name,
                    "No market data found for neighborhood analysis",
                    "NA",
                    Decimal("0.0000"),
                    "failed",
                )
                return (None, False)

            progress.update(
                task,
                description=f"[cyan]Deep reasoning analysis with {self.config.reasoning_model} ({len(search_results)} data points)...",
            )

            # Compile search data for prompt
            search_data = "\n\n".join(
                [
                    f"**Query**: {result['query']}\n**Source**: {result['title']} ({result['url']})\n**Content**: {result['content'][:1000]}..."
                    for result in search_results[:25]
                ]
            )

            # Create analysis prompt using the template
            analysis_prompt = f"""
You are a real estate investment analyst. Generate a concise neighborhood report for an investor evaluating rental properties.

**Location:** {neighborhood_name}, {city}, {state}
**Subject Property Address:** {address1}

**Web Research Results:**
{search_data}

---

# {neighborhood_name} Neighborhood Report

**Overall Grade:** [A/B/C/D/F] | **Investor Recommendation:** [Strong Buy / Buy / Hold / Caution / Avoid]

## Quick Stats
- **Median Home Price:** $X (X% YoY change)
- **Median Rent (2BR):** $X (X% YoY change)
- **Rent-to-Price Ratio:** X.X% (rounded to one decimal place)
- **Vacancy Rate:** X.X% (rounded to one decimal place)
- **Owner/Renter Split:** X% / X%
- **Median Household Income:** $X
- **Crime Rate vs City Avg:** X.X% higher/lower (rounded to one decimal place)
  - If any data is not available from search results, write "Data unavailable" for that field.

## Letter Grade Justification
[2-3 sentences explaining why this specific letter grade was assigned. Reference specific data points from Quick Stats that support the grade. Example: "Grade C assigned due to flat price appreciation (1% YoY), average crime rate, and mixed market signals. While rent growth is positive at 4%, high vacancy rate of 10% and limited catalysts prevent a higher grade."]

## Demand Drivers
[2-3 sentences on what drives rental demand, such as proximity to employers, universities, hospitals, transit, downtown, etc. If no information is found, write "Data unavailable".]

## Market Trend
[2-3 sentences on price/rent trajectory, days on market, investor activity, whether appreciating or stagnant. Write "Data unavailable" if not present in results.]

## Risk Factors
- List 2-4 specific concerns such as crime trends, declining population, major employer leaving, flood zone, etc., in bullet format in the order presented. If none found, write "None significant".

## Catalysts
- List 2-4 positive developments such as new transit, employer expansion, rezoning, revitalization projects, etc., in bullet format in the order presented. If none found, write "None identified".

## Tenant Profile
[1-2 sentences: Who rents here? Young professionals, students, families, Section 8, mixed? Write "Data unavailable" if no information found.]

---

**Rules:**
- Use ONLY information from the search results. If data is unavailable for any field, write "Data unavailable" in its place.
- Provide specific numbers as indicated; avoid vague terms like "relatively high"—all figures should adhere to the required format for each field.
- Keep the total word count under 500 words.
- If 'search_data' is blank or lacks information for any required field, return "Data unavailable" for those fields and continue with the report structure as specified.
- Prioritize complete, actionable answers within the length cap, even if the original user request is brief. Do not return prematurely if additional relevant fields can be filled.

**Grading Rubric** (evaluate holistically across all factors):

**Grade A (Strong Buy):**
- Home prices appreciating 5%+ annually
- Crime rate <20% below city average
- Vacancy rate <5%
- Rent-to-price ratio >0.8%
- Strong catalysts (new development, employers, transit)
- No significant risk factors

**Grade B (Buy):**
- Home prices stable or appreciating 2-5% annually
- Crime rate within 20% of city average
- Vacancy rate 5-8%
- Rent-to-price ratio 0.6-0.8%
- Some positive catalysts
- Minor risk factors that are manageable

**Grade C (Hold):**
- Home prices flat or minimal appreciation (0-2%)
- Crime rate 20-40% above city average
- Vacancy rate 8-12%
- Rent-to-price ratio 0.5-0.6%
- Mixed signals on market trend
- Moderate risks present

**Grade D (Caution):**
- Home prices declining or stagnant
- Crime rate >40% above city average
- Vacancy rate >12%
- Rent-to-price ratio <0.5%
- Negative market trends
- Significant risk factors (population decline, major employer exodus)

**Grade F (Avoid):**
- Severe price declines
- Extremely high crime
- Very high vacancy (>15%)
- Multiple severe risk factors with no catalysts
- Fundamentally distressed market

## Output Format

All fields and sections must be rendered exactly as in the template and in the specified order. Use bullet lists for Risk Factors and Catalysts, maintaining their respective specified order. Each percentage-based stat should be displayed as "X.X%" (rounded to one decimal place) with units clearly indicated. If a required section is completely missing, write "Data unavailable".

## Output Verbosity
- Keep the report under 500 words. Limit all narrative sections (e.g., Letter Grade Justification, Demand Drivers, Market Trend, Tenant Profile) to no more than 3 sentences per section.
- For bullet lists (Risk Factors, Catalysts), provide 2-4 bullets, each a single concise line.
- Persist until all sections and required fields are addressed as fully as the input allows, within the length limit.
""".strip()

            result = self._analyze_with_reasoning_model(analysis_prompt)

            if not result["success"]:
                progress.update(task, description="[red]Analysis failed!")
                error_msg = result.get("error", "Unknown error")
                self.console.print(f"[red]Analysis failed: {error_msg}[/red]")
                self._store_report(
                    address1,
                    neighborhood_name,
                    f"Analysis failed: {error_msg}",
                    analysis_prompt,
                    Decimal("0.0000"),
                    "failed",
                )
                return (None, False)

            # Calculate total cost
            num_searches = len(queries)
            cost = self._calculate_cost(
                num_searches, result["input_tokens"], result["output_tokens"]
            )

            progress.update(task, description="[green]Storing research report...")

            # Store successful report
            report_id = self._store_report(
                address1, neighborhood_name, result["content"], analysis_prompt, cost
            )

            progress.update(task, description="[green]Research completed successfully!")

            # Display cost information
            search_cost = num_searches * self.config.search_cost_per_query
            reasoning_cost = cost - Decimal(str(search_cost))

            self.console.print(
                Panel(
                    f"[green]Neighborhood research completed successfully![/green]\n\n"
                    f"**Neighborhood**: {neighborhood_name}\n"
                    f"**Location**: {city}, {state}\n"
                    f"**Market Data Sources**: {len(search_results)} data points from {num_searches} searches\n"
                    f"**Reasoning Tokens**: {result['input_tokens']:,} input, {result['output_tokens']:,} output\n"
                    f"**Search Cost**: ${search_cost:.4f} ({num_searches} × $0.008)\n"
                    f"**{self.config.reasoning_model} Reasoning Cost**: ${reasoning_cost:.4f}\n"
                    f"**Total API Cost**: ${cost:.4f}\n"
                    f"**Report ID**: {report_id}",
                    title="Neighborhood Research Summary",
                    border_style="green",
                )
            )

            return (report_id, False)

    def get_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a specific research report by ID"""
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

    def display_report(self, report_content: str):
        """Display a neighborhood research report using Rich formatting"""
        from rich.markdown import Markdown

        # Create markdown object
        markdown = Markdown(report_content)

        with self.console.pager(styles=True):
            self.console.print(
                Panel(
                    markdown,
                    title="[bold cyan]Neighborhood Research Report[/bold cyan]",
                    border_style="cyan",
                    padding=(1, 2),
                )
            )

    def extract_neighborhood_grade(
        self, report_id: str, show_progress: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Extract letter grade from a neighborhood research report and update the neighborhoods table.

        Args:
            report_id: ID of the research report to extract grade from
            show_progress: Whether to show progress spinner (disable when called from batch operations)

        Returns:
            Dict with letter_grade, confidence_score, cost, and tokens_used if successful, None if failed
        """
        # Fetch the report
        try:
            result = (
                self.supabase.table("research_reports")
                .select("*")
                .eq("id", report_id)
                .single()
                .execute()
            )
            if not result.data:
                self.console.print(f"[red]Report not found: {report_id}[/red]")
                return None

            report_data = result.data
            report_content = report_data["report_content"]
            research_type = report_data.get("research_type", "")
            status = report_data.get("status", "")

            # Verify it's a neighborhood report
            if not research_type.endswith("_neighborhood_report"):
                self.console.print(
                    f"[red]Report is not a neighborhood report (type: {research_type})[/red]"
                )
                return None

            # Verify status is completed
            if status != "completed":
                self.console.print(
                    f"[red]Report is not completed (status: {status})[/red]"
                )
                return None

        except Exception as e:
            self.console.print(f"[red]Error fetching report: {str(e)}[/red]")
            return None

        # Extract neighborhood name from research_type
        neighborhood_name = research_type.replace("_neighborhood_report", "")

        # Debug: Report details
        self.console.print(
            f"[dim]    Report verified: neighborhood='{neighborhood_name}', status='{status}'[/dim]"
        )

        # Create extraction prompt
        extraction_prompt = f"""Analyze the following neighborhood research report and extract the letter grade.

# Research Report:
{report_content}

# Extraction Instructions:
The report contains an "Overall Grade" in the format: **Overall Grade:** [A/B/C/D/F]

Extract:
1. **letter_grade**: Single letter (A, B, C, D, or F) representing the neighborhood grade
2. **confidence_score**: Your confidence in this extraction (0.0 to 1.0)

Base your confidence on:
- Clarity of the grade in the report
- Whether the grade is explicitly stated vs implied
- Consistency throughout the report

Provide only the letter grade (A, B, C, D, or F) without any additional text.
"""

        # Call GPT-5 with structured outputs
        if show_progress:
            self.console.print("[cyan]Analyzing report with GPT-5...[/cyan]")
        extraction_result = self._extract_letter_grade_with_reasoning_model(
            extraction_prompt
        )

        if not extraction_result["success"]:
            self.console.print(
                f"[red]Failed to extract grade: {extraction_result.get('error', 'Unknown error')}[/red]"
            )
            return None

        letter_grade = extraction_result["grade"]
        confidence_score = extraction_result["confidence_score"]

        # Debug: Extraction result
        self.console.print(
            f"[dim]    Extraction successful: grade='{letter_grade}', confidence={confidence_score:.2f}[/dim]"
        )

        # Calculate cost
        reasoning_cost = self._calculate_cost(
            0,
            extraction_result["input_tokens"],
            extraction_result["output_tokens"],
        )

        if show_progress:
            self.console.print("[cyan]Updating neighborhoods table...[/cyan]")

        # Get neighborhood by name to check for existing grade
        try:
            neighborhood_response = (
                self.supabase.table("neighborhoods")
                .select("id, name, letter_grade")
                .eq("name", neighborhood_name)
                .single()
                .execute()
            )

            if not neighborhood_response.data:
                self.console.print(
                    f"[red]Neighborhood not found in database: {neighborhood_name}[/red]"
                )
                return None

            neighborhood_id = neighborhood_response.data["id"]
            previous_grade = neighborhood_response.data.get("letter_grade")

            # Debug: Database lookup
            self.console.print(
                f"[dim]    Found neighborhood in DB: id={neighborhood_id}, previous_grade={previous_grade}[/dim]"
            )

            # Update with new grade (always overwrites)
            update_result = (
                self.supabase.table("neighborhoods")
                .update({"letter_grade": letter_grade})
                .eq("id", neighborhood_id)
                .execute()
            )

            if not update_result.data:
                self.console.print("[red]Failed to update neighborhoods table[/red]")
                return None

        except Exception as e:
            self.console.print(
                f"[red]Error updating neighborhoods table: {str(e)}[/red]"
            )
            return None

        if show_progress:
            self.console.print("[green]Extraction completed![/green]")

            # Determine grade color styling
            if letter_grade in ["A", "B"]:
                grade_style = "green"
            elif letter_grade == "C":
                grade_style = "yellow"
            else:  # D or F
                grade_style = "red"

            # Display results in table format
            results_table = Table(
                title="Neighborhood Letter Grade Extraction",
                show_header=True,
                header_style="bold cyan",
            )
            results_table.add_column("Neighborhood", style="cyan", width=25)
            results_table.add_column("Previous Grade", justify="center", width=14)
            results_table.add_column("New Grade", justify="center", width=14)
            results_table.add_column("Confidence", justify="right", width=12)
            results_table.add_column("API Cost", justify="right", width=12)

            results_table.add_row(
                neighborhood_name,
                previous_grade if previous_grade else "None",
                f"[{grade_style}]{letter_grade}[/{grade_style}]",
                f"{confidence_score:.1%}",
                f"${reasoning_cost:.4f}",
            )

            self.console.print(results_table)

        # Always return results, regardless of show_progress
        return {
            "letter_grade": letter_grade,
            "confidence_score": confidence_score,
            "cost": float(reasoning_cost),
            "tokens_used": {
                "input": extraction_result["input_tokens"],
                "output": extraction_result["output_tokens"],
            },
        }

    def extract_neighborhood_grades_batch(
        self, report_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Extract letter grades for multiple neighborhood reports in batch.

        Args:
            report_ids: Optional list of report IDs to process. If None, processes all completed neighborhood reports.

        Returns:
            Dict with summary of processed reports, successes, failures, and total cost
        """
        # Fetch reports to process
        try:
            if report_ids:
                # Fetch specific reports
                reports = []
                for report_id in report_ids:
                    result = (
                        self.supabase.table("research_reports")
                        .select("*")
                        .eq("id", report_id)
                        .single()
                        .execute()
                    )
                    if result.data:
                        reports.append(result.data)
            else:
                # Fetch all completed neighborhood reports
                result = (
                    self.supabase.table("research_reports")
                    .select("*")
                    .eq("status", "completed")
                    .execute()
                )
                # Filter for neighborhood reports
                reports = [
                    r
                    for r in result.data
                    if r.get("research_type", "").endswith("_neighborhood_report")
                ]

            if not reports:
                self.console.print(
                    "[yellow]No neighborhood reports found to process[/yellow]"
                )
                return {
                    "total_processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "total_cost": 0.0,
                    "results": [],
                }

        except Exception as e:
            self.console.print(f"[red]Error fetching reports: {str(e)}[/red]")
            return {
                "total_processed": 0,
                "successful": 0,
                "failed": 0,
                "total_cost": 0.0,
                "results": [],
            }

        # Process each report with progress bar
        successes = 0
        failures = 0
        total_cost = 0.0
        results = []

        self.console.print(
            f"\n[bold cyan]Processing {len(reports)} neighborhood reports...[/bold cyan]\n"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
        ) as progress:
            for i, report in enumerate(reports, 1):
                report_id = report["id"]
                research_type = report.get("research_type", "")
                neighborhood_name = research_type.replace("_neighborhood_report", "")

                task = progress.add_task(
                    f"[cyan][{i}/{len(reports)}] Processing {neighborhood_name}...",
                    total=None,
                )

                try:
                    # Debug: Log what we're processing
                    self.console.print(
                        f"[dim]  Extracting grade from report {report_id} (type: {research_type})...[/dim]"
                    )

                    result = self.extract_neighborhood_grade(
                        report_id, show_progress=False
                    )

                    if result:
                        successes += 1
                        total_cost += result["cost"]
                        results.append(
                            {
                                "neighborhood": neighborhood_name,
                                "grade": result["letter_grade"],
                                "confidence": result["confidence_score"],
                                "success": True,
                                "error": None,
                            }
                        )
                        progress.update(
                            task,
                            description=f"[green][{i}/{len(reports)}] ✓ {neighborhood_name} - Grade: {result['letter_grade']}[/green]",
                        )
                    else:
                        # Log WHY it failed
                        error_msg = "extract_neighborhood_grade returned None - check logs above for details"
                        self.console.print(f"[yellow]  ⚠ Warning: {error_msg}[/yellow]")

                        failures += 1
                        results.append(
                            {
                                "neighborhood": neighborhood_name,
                                "grade": None,
                                "confidence": None,
                                "success": False,
                                "error": error_msg,
                            }
                        )
                        progress.update(
                            task,
                            description=f"[red][{i}/{len(reports)}] ✗ {neighborhood_name} - Failed[/red]",
                        )

                except Exception as e:
                    # Log the full exception with traceback
                    self.console.print(f"[red]  ✗ Exception: {str(e)}[/red]")
                    import traceback

                    self.console.print(f"[dim]{traceback.format_exc()}[/dim]")

                    failures += 1
                    results.append(
                        {
                            "neighborhood": neighborhood_name,
                            "grade": None,
                            "confidence": None,
                            "success": False,
                            "error": str(e),
                        }
                    )
                    progress.update(
                        task,
                        description=f"[red][{i}/{len(reports)}] ✗ {neighborhood_name} - Error[/red]",
                    )

                progress.remove_task(task)

        # Display batch summary
        self.console.print("\n[bold green]Batch Processing Summary:[/bold green]")

        summary_table = Table(
            title="Neighborhood Grade Extraction Results",
            show_header=True,
            header_style="bold cyan",
        )
        summary_table.add_column("Neighborhood", style="cyan", width=30)
        summary_table.add_column("Grade", justify="center", width=10)
        summary_table.add_column("Confidence", justify="right", width=12)
        summary_table.add_column("Status", justify="center", width=10)

        for result in results:
            if result["success"]:
                grade = result["grade"]
                # Determine grade color
                if grade in ["A", "B"]:
                    grade_display = f"[green]{grade}[/green]"
                elif grade == "C":
                    grade_display = f"[yellow]{grade}[/yellow]"
                else:
                    grade_display = f"[red]{grade}[/red]"

                summary_table.add_row(
                    result["neighborhood"],
                    grade_display,
                    f"{result['confidence']:.1%}",
                    "[green]✓[/green]",
                )
            else:
                summary_table.add_row(
                    result["neighborhood"], "N/A", "N/A", "[red]✗[/red]"
                )

        self.console.print(summary_table)

        # Display statistics
        stats_panel = Panel(
            f"[green]Total Processed: {len(reports)}[/green]\n"
            f"[green]Successful: {successes}[/green]\n"
            f"[red]Failed: {failures}[/red]\n"
            f"[cyan]Total API Cost: ${total_cost:.4f}[/cyan]",
            title="Statistics",
            border_style="green",
        )
        self.console.print(stats_panel)

        return {
            "total_processed": len(reports),
            "successful": successes,
            "failed": failures,
            "total_cost": total_cost,
            "results": results,
        } 