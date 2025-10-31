"""
Rent Research Module using Tavily + o1-mini

This module provides comprehensive rental market analysis for properties using
Tavily API for web search and o1-mini for intelligent reasoning and analysis.
"""

import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

import openai
from tavily import TavilyClient
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.progress import Progress, SpinnerColumn, TextColumn
from supabase import Client


@dataclass
class ResearchConfig:
    """Configuration for rent research operations"""
    reasoning_model: str = "o1-mini"
    max_tokens: int = 65536  # o1-mini supports up to 65k output tokens
    search_cost_per_query: float = 0.008  # Tavily cost
    reasoning_cost_per_input_token: float = 0.000003  # o1-mini input
    reasoning_cost_per_output_token: float = 0.000012  # o1-mini output
    timeout_seconds: int = 180  # o1-mini can take longer for reasoning
    searches_per_property: int = 12


class RentResearcher:
    """Handles rent research operations using Tavily + o1-mini"""
    
    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console
        self.config = ResearchConfig()
        
        # Initialize OpenAI client for reasoning
        openai.api_key = os.getenv("OPENAI_API_KEY")
        if not openai.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        self.openai_client = openai.OpenAI(api_key=openai.api_key)
        
        # Initialize Tavily client for search
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise ValueError("TAVILY_API_KEY environment variable not set")
        self.tavily_client = TavilyClient(api_key=tavily_api_key)
    
    def _calculate_cost(self, num_searches: int, input_tokens: int, output_tokens: int) -> Decimal:
        """Calculate the total cost of searches + reasoning"""
        search_cost = num_searches * self.config.search_cost_per_query
        reasoning_input_cost = input_tokens * self.config.reasoning_cost_per_input_token
        reasoning_output_cost = output_tokens * self.config.reasoning_cost_per_output_token
        total_cost = search_cost + reasoning_input_cost + reasoning_output_cost
        return Decimal(str(total_cost)).quantize(Decimal('0.0001'))
    
    def _generate_search_queries(self, property_data: Dict[str, Any]) -> List[str]:
        """Generate targeted search queries for comprehensive rental analysis"""
        
        address = property_data.get('address1', 'Unknown Address')
        beds = property_data.get('beds', 0)
        baths = property_data.get('baths', 0)
        units = property_data.get('units', 1)
        
        # Extract city/area from address for location-based searches
        location = address.split(',')[0] if ',' in address else address
        
        queries = [
            # Comparable rental properties
            f"{beds} bedroom {baths} bathroom rental near {location}",
            f"duplex rental prices {location}" if units == 2 else f"{units} unit rental {location}",
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
            f"{location} rental market forecast 2025"
        ]
        
        return queries
    
    def _perform_searches(self, queries: List[str]) -> List[Dict[str, Any]]:
        """Perform Tavily searches for all queries"""
        
        search_results = []
        
        for query in queries:
            try:
                response = self.tavily_client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5,
                    include_raw_content="markdown",
                    chunks_per_source=5
                )
                
                if response and 'results' in response:
                    for result in response['results']:
                        search_results.append({
                            'query': query,
                            'title': result.get('title', ''),
                            'url': result.get('url', ''),
                            'content': result.get('content', ''),
                            'raw_content': result.get('raw_content', ''),
                            'score': result.get('score', 0)
                        })
                        
            except Exception as e:
                self.console.print(f"[yellow]Search failed for query '{query}': {str(e)}[/yellow]")
                continue
        
        return search_results
    
    def _create_analysis_prompt(self, property_data: Dict[str, Any], search_results: List[Dict[str, Any]]) -> str:
        """Create comprehensive analysis prompt for o1-mini"""
        
        address = property_data.get('address1', 'Unknown Address')
        purchase_price = property_data.get('purchase_price', 0)
        beds = property_data.get('beds', 0)
        baths = property_data.get('baths', 0)
        square_ft = property_data.get('square_ft', 0)
        units = property_data.get('units', 1)
        built_in = property_data.get('built_in', 'Unknown')
        
        # Compile search data
        search_data = "\n\n".join([
            f"**Query**: {result['query']}\n**Source**: {result['title']} ({result['url']})\n**Content**: {result['content'][:1000]}..."
            for result in search_results[:25]  # More data for o1-mini's reasoning
        ])
        
        prompt = f"""
Analyze this rental property investment using the market research data provided below. Apply deep reasoning to provide comprehensive insights.

# Property Details
- **Address**: {address}
- **Purchase Price**: ${purchase_price:,}
- **Bedrooms**: {beds}
- **Bathrooms**: {baths}
- **Square Footage**: {square_ft:,} sq ft
- **Number of Units**: {units}
- **Year Built**: {built_in}

# Market Research Data
{search_data}

# Analysis Requirements

Provide a comprehensive rental analysis report in markdown format. Use your reasoning capabilities to synthesize the data and provide deep insights:

## 1. Executive Summary
- Key findings and actionable recommendations
- **Specific recommended rent range with confidence level**
- Market positioning assessment
- Investment viability summary

## 2. Comparable Properties Analysis
- Identify and analyze 5-8 most relevant comparable properties
- Calculate rent per square foot benchmarks
- Analyze property features that affect pricing
- Distance and location premium/discount factors
- **Provide specific rent ranges with justification**

## 3. Market Rate Analysis
- Current market rental rates for this specific property type
- Price per square foot analysis by unit configuration
- Unit configuration premium/discounts (studio, 1BR, 2BR, etc.)
- Seasonal rental variations and optimal timing
- **Specific dollar amounts for each unit type**

## 4. Historical Trends & Market Forecasting
- 6-12 month rental trend analysis with specific data points
- Year-over-year percentage changes
- Market direction and 12-month growth projections
- Economic factors driving price changes
- **Quantified trend data with percentages**

## 5. Neighborhood & Location Analysis
- Walkability, transit, and accessibility scores
- Local amenities impact on rental premiums
- Employment centers and school district effects
- Demographic analysis and tenant demand patterns
- **Location-based rental premiums/discounts**

## 6. Competitive Positioning & Strategy
- Properties with superior amenities and their exact premiums
- Properties with inferior features and their discounts
- Market gaps and positioning opportunities
- Competitive advantages of this property
- **Strategic rental positioning recommendations**

## 7. Rental Optimization Recommendations
- **Recommended Monthly Rent Range**: Provide specific dollar amounts for each unit
- Property improvement ROI analysis for rent increases
- Marketing strategies and tenant acquisition approaches
- Optimal lease terms and rental timing
- **Cost-benefit analysis of improvements**

## 8. Risk Assessment & Market Intelligence
- Vacancy risk factors and mitigation strategies
- Competition analysis and market saturation
- Economic sensitivity and demand elasticity
- Regulatory and market risks
- **Quantified risk factors with probabilities**

## 9. Comparative Analysis Summary
- How this property compares to market average
- Percentile ranking in local market
- Value proposition for tenants
- Investment performance projections
- **Specific performance metrics and rankings**

## 10. Historical Trend Analysis
- Multi-year rental growth patterns
- Seasonal demand cycles
- Market cycle positioning
- Future growth catalysts
- **Historical data analysis with projections**

# Reasoning Approach
Use your advanced reasoning to:
1. Cross-reference data points for accuracy
2. Identify patterns and correlations in the market data
3. Calculate weighted averages and statistical insights
4. Consider multiple scenarios and their implications
5. Provide confidence intervals for recommendations

# Output Requirements
- Include specific dollar amounts and percentages throughout
- Provide confidence levels for all major recommendations
- Cite sources and data quality assessments
- Focus on actionable, investment-grade insights
- Use clear headings and professional formatting

Generate a comprehensive, data-driven analysis that demonstrates deep reasoning and provides specific, actionable recommendations for rental pricing optimization.
"""
        return prompt.strip()
    
    def _analyze_with_reasoning_model(self, prompt: str) -> Dict[str, Any]:
        """Use o1-mini to analyze search results and generate comprehensive report"""
        
        try:
            response = self.openai_client.chat.completions.create(
                model=self.config.reasoning_model,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                max_completion_tokens=self.config.max_tokens
                # Note: o1-mini doesn't use system messages or temperature
            )
            
            content = response.choices[0].message.content
            input_tokens = response.usage.prompt_tokens
            output_tokens = response.usage.completion_tokens
            
            return {
                "content": content,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "success": True
            }
            
        except Exception as e:
            return {
                "content": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "success": False,
                "error": str(e)
            }
    
    def _store_report(self, property_id: str, report_content: str, 
                          cost: Decimal, status: str = "completed") -> Optional[str]:
        """Store the research report in the database"""
        
        try:
            result = self.supabase.table('research_reports').insert({
                'property_id': property_id,
                'report_content': report_content,
                'status': status,
                'api_cost': float(cost),
                'research_type': 'rental_comparison',
                'created_at': datetime.now(timezone.utc).isoformat()
            }).execute()
            
            if result.data:
                return result.data[0]['id']
            return None
            
        except Exception as e:
            self.console.print(f"[red]Error storing report: {str(e)}[/red]")
            return None
    
    def generate_rent_research(self, property_id: str) -> Optional[str]:
        """
        Generate comprehensive rent research for a property
        
        Args:
            property_id: The property address/ID to research
            
        Returns:
            The report ID if successful, None if failed
        """
        
        # Get property data
        try:
            property_response = self.supabase.table('properties').select('*').eq('address1', property_id).single().execute()
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
            
            task = progress.add_task("[cyan]Initializing rental research...", total=None)
            
            # Generate search queries
            progress.update(task, description="[cyan]Generating search queries...")
            queries = self._generate_search_queries(property_data)
            
            # Perform web searches
            progress.update(task, description=f"[cyan]Searching market data ({len(queries)} queries)...")
            search_results = self._perform_searches(queries)
            
            if not search_results:
                progress.update(task, description="[red]No search results found!")
                self.console.print("[red]No market data found for analysis.[/red]")
                self._store_report(property_id, "No market data found for analysis", Decimal('0.0000'), "failed")
                return None
            
            progress.update(task, description=f"[cyan]Deep reasoning analysis with o1-mini ({len(search_results)} data points)...")
            
            # Create analysis prompt
            analysis_prompt = self._create_analysis_prompt(property_data, search_results)
            
            # Analyze with reasoning model
            result = self._analyze_with_reasoning_model(analysis_prompt)
            
            if not result["success"]:
                progress.update(task, description="[red]Analysis failed!")
                error_msg = result.get('error', 'Unknown error')
                self.console.print(f"[red]Analysis failed: {error_msg}[/red]")
                self._store_report(property_id, f"Analysis failed: {error_msg}", Decimal('0.0000'), "failed")
                return None
            
            # Calculate total cost
            num_searches = len(queries)
            cost = self._calculate_cost(num_searches, result['input_tokens'], result['output_tokens'])
            
            progress.update(task, description="[green]Storing research report...")
            
            # Store successful report
            report_id = self._store_report(
                property_id, 
                result["content"], 
                cost
            )
            
            progress.update(task, description="[green]Research completed successfully!")
            
            # Display cost information
            search_cost = num_searches * self.config.search_cost_per_query
            reasoning_cost = cost - Decimal(str(search_cost))
            
            self.console.print(Panel(
                f"[green]Research completed successfully![/green]\n\n"
                f"**Market Data Sources**: {len(search_results)} data points from {num_searches} searches\n"
                f"**Reasoning Tokens**: {result['input_tokens']:,} input, {result['output_tokens']:,} output\n"
                f"**Search Cost**: ${search_cost:.4f} ({num_searches} × $0.008)\n"
                f"**o1-mini Reasoning Cost**: ${reasoning_cost:.4f}\n"
                f"**Total API Cost**: ${cost:.4f}\n"
                f"**Report ID**: {report_id}",
                title="Research Summary",
                border_style="green"
            ))
            
            return report_id
    
    def display_report(self, report_content: str):
        """Display a research report using Rich markdown rendering"""
        
        # Create markdown object
        markdown = Markdown(report_content)
        
        # Display with panel
        self.console.print(Panel(
            markdown,
            title="[bold cyan]Rental Market Research Report[/bold cyan]",
            border_style="cyan",
            padding=(1, 2)
        ))
    
    def get_report_by_id(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a research report by ID"""
        
        try:
            result = self.supabase.table('research_reports').select('*').eq('id', report_id).single().execute()
            return result.data
        except Exception as e:
            self.console.print(f"[red]Error fetching report: {str(e)}[/red]")
            return None
    
    def get_reports_for_property(self, property_id: str) -> list:
        """Get all research reports for a property"""
        
        try:
            result = self.supabase.table('research_reports').select('*').eq('property_id', property_id).order('created_at', desc=True).execute()
            return result.data
        except Exception as e:
            self.console.print(f"[red]Error fetching reports: {str(e)}[/red]")
            return []


# Convenience function for standalone usage
def run_rent_research(property_id: str, supabase_client: Client, 
                          console: Console) -> Optional[str]:
    """
    Convenience function to run rent research for a property
    
    Args:
        property_id: The property address/ID to research
        supabase_client: Supabase client instance
        console: Rich console instance
        
    Returns:
        Report ID if successful, None if failed
    """
    
    researcher = RentResearcher(supabase_client, console)
    return researcher.generate_rent_research(property_id)