import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import openai
import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from supabase import Client
from tavily import TavilyClient


@dataclass
class NeighborhoodResearchConfig:
    """Configuration for neighborhood research operations"""

    reasoning_model: str = "gpt-5"
    max_tokens: int = 120000
    search_cost_per_query: float = 0.008  # Tavily cost
    reasoning_cost_per_input_token: float = 1.25 / 1000000
    reasoning_cost_per_output_token: float = 10 / 1000000
    searches_per_neighborhood: int = 6


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

  # use elementary, middle school, high school ratings to create an average for the property

  def is_neighborhood_assessment_complete(self, address1: str) -> bool:
    return False

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
      self.console.print(f"[yellow]Warning: Error checking neighborhood analysis for '{neighborhood_name}': {str(e)}[/yellow]")
      return False

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
      # Query property_neighborhood with a join to neighborhoods table
      # Supabase syntax: table.select('col1, col2, foreign_table(foreign_col)')
      response = supabase.table('property_neighborhood')\
        .select('address1, neighborhoods(name)')\
        .execute()

      if not response.data:
        # No neighborhoods found, return empty dataframe with correct columns
        return pd.DataFrame(columns=['address1', 'neighborhood'])

      # Convert to dataframe
      neighborhoods_df = pd.DataFrame(response.data)

      # Handle the nested structure from Supabase join
      # The 'neighborhoods' column contains a dict like {'name': 'downtown'}
      if 'neighborhoods' in neighborhoods_df.columns:
        neighborhoods_df['neighborhood'] = neighborhoods_df['neighborhoods'].apply(
          lambda x: x['name'] if x and isinstance(x, dict) and 'name' in x else None
        )
        # Keep only the columns we need
        neighborhoods_df = neighborhoods_df[['address1', 'neighborhood']]
      else:
        # Fallback if structure is different
        return pd.DataFrame(columns=['address1', 'neighborhood'])

      # Remove any rows where neighborhood is None
      neighborhoods_df = neighborhoods_df.dropna(subset=['neighborhood'])

      return neighborhoods_df

    except Exception as e:
      print(f"Error fetching neighborhoods: {e}")
      # Return empty dataframe on error
      return pd.DataFrame(columns=['address1', 'neighborhood'])

  def _calculate_cost(self, num_searches: int, input_tokens: int, output_tokens: int) -> Decimal:
    """Calculate the total cost of searches + reasoning"""
    search_cost = num_searches * self.config.search_cost_per_query
    reasoning_input_cost = input_tokens * self.config.reasoning_cost_per_input_token
    reasoning_output_cost = output_tokens * self.config.reasoning_cost_per_output_token
    total_cost = search_cost + reasoning_input_cost + reasoning_output_cost
    return Decimal(str(total_cost)).quantize(Decimal("0.0001"))

  def _generate_neighborhood_search_queries(self, neighborhood: str, city: str) -> List[str]:
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
        'message': getattr(e, 'message', str(e)),
        'code': getattr(e, 'code', 'Unknown'),
        'hint': getattr(e, 'hint', None),
        'details': getattr(e, 'details', None)
      }
      self.console.print(f"[red]Error storing report: {error_details}[/red]")
      return None

  def generate_neighborhood_research(self, address1: str) -> tuple[Optional[str], bool]:
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
        self.supabase.table('property_neighborhood')
        .select('neighborhoods(name)')
        .eq('address1', address1)
        .single()
        .execute()
      )
      if not neighborhood_response.data or not neighborhood_response.data.get('neighborhoods'):
        self.console.print(f"[red]No neighborhood found for property: {address1}[/red]")
        return (None, False)

      neighborhood_dict = neighborhood_response.data['neighborhoods']
      if not isinstance(neighborhood_dict, dict) or 'name' not in neighborhood_dict:
        self.console.print(f"[red]Invalid neighborhood data structure[/red]")
        return (None, False)

      neighborhood_name = neighborhood_dict['name']
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
        existing_report_id = existing_report.data[0]['id']
        self.console.print(
          f"[green]✓ Existing neighborhood report found for '{neighborhood_name}'[/green]"
        )
        self.console.print(f"[cyan]Report ID: {existing_report_id}[/cyan]")
        return (existing_report_id, True)
    except Exception as e:
      self.console.print(f"[yellow]Warning: Could not check for existing reports: {str(e)}[/yellow]")
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
      queries = self._generate_neighborhood_search_queries(neighborhood_name, city)

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

**Output Format (follow exactly):**

# {neighborhood_name} Neighborhood Report

**Overall Grade:** [A/B/C/D/F] | **Investor Recommendation:** [Strong Buy / Buy / Hold / Caution / Avoid]

## Quick Stats
- **Median Home Price:** $X (X% YoY change)
- **Median Rent (2BR):** $X (X% YoY change)
- **Rent-to-Price Ratio:** X%
- **Vacancy Rate:** X%
- **Owner/Renter Split:** X% / X%
- **Median Household Income:** $X
- **Crime Rate vs City Avg:** X% higher/lower

## Demand Drivers
[2-3 sentences on what drives rental demand: proximity to employers, universities, hospitals, transit, downtown, etc.]

## Market Trend
[2-3 sentences on price/rent trajectory, days on market, investor activity, whether appreciating or stagnant]

## Risk Factors
[Bullet list of 2-4 specific concerns: crime trends, declining population, major employer leaving, flood zone, etc. Write "None significant" if none found]

## Catalysts
[Bullet list of 2-4 positive developments: new transit, employer expansion, rezoning, revitalization projects, etc. Write "None identified" if none found]

## Tenant Profile
[1-2 sentences: Who rents here? Young professionals, students, families, Section 8, mixed?]

---

**Rules:**
- Use ONLY information from the search results. If data is unavailable, write "Data unavailable"
- Be specific with numbers—no vague language like "relatively high"
- Keep total length under 400 words
- Grade criteria: A = strong appreciation + low crime + high demand; B = solid fundamentals; C = mixed signals; D = significant concerns; F = avoid
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
        address1,
        neighborhood_name,
        result["content"],
        analysis_prompt,
        cost
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