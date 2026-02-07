import os
import requests
import pandas as pd
from supabase import Client
from rich.console import Console
from rich.panel import Panel
from display import display_property_value_comparison
from handlers import handle_rent_research_after_add
from add_property import mark_property_as_researched
from neighborhood_scraper import NeighborhoodScraper
from neighborhoods import NeighborhoodsClient

# RentCast API headers
RENTCAST_HEADERS = {
    "accept": "application/json",
    "X-Api-Key": os.getenv("RENTCAST_KEY"),
}

class ScriptsProvider:
    def __init__(self, supabase_client: Client, console: Console, neighborhood_scraper: NeighborhoodScraper, neighborhood_client: NeighborhoodsClient):
        self.supabase = supabase_client
        self.console = console
        self.neighborhood_scraper = neighborhood_scraper
        self.neighborhood_client = neighborhood_client

    def save_sale_comps_to_db(self, comps, address1):
        """
        Save sales comparables to database.
        Mirrors the pattern from save_property_comps_to_db() in add_property.py.

        Args:
            comps: List of comparable properties from RentCast API
            address1: The subject property's address1

        Returns:
            Number of comparables saved
        """
        comps_saved = 0

        for comp in comps:
            comp_row = {
                "id": comp.get("id"),
                "address": comp.get("formattedAddress"),
                "county": comp.get("county"),
                "latitude": comp.get("latitude"),
                "longitude": comp.get("longitude"),
                "property_type": comp.get("propertyType"),
                "beds": comp.get("bedrooms"),
                "baths": comp.get("bathrooms"),
                "square_feet": comp.get("squareFootage"),
                "lot_size": comp.get("lotSize"),
                "built_in": comp.get("yearBuilt"),
                "rent_price": comp.get("price"),
                "status": comp.get("status"),
                "days_old": comp.get("daysOld"),
            }

            try:
                # Check if this comparable already exists (by id alone)
                existing = (
                    self.supabase.table("comparable_rents")
                    .select("id")
                    .eq("id", comp_row["id"])
                    .execute()
                )

                if not existing.data:
                    # Insert new comparable
                    query = self.supabase.table("comparable_rents").insert(comp_row)
                    response = query.execute()

                    if not hasattr(response, "data"):
                        self.console.print(f"[yellow]Warning: Could not save comparable {comp_row['id']}[/yellow]")

                # Check if relationship already exists (by comp_id AND address1)
                existing_join = (
                    self.supabase.table("sale_comp_to_property")
                    .select("id, distance, correlation")
                    .eq("address1", address1)
                    .eq("comp_id", comp.get("id"))
                    .execute()
                )

                if existing_join.data:
                    # Check if distance/correlation are missing and update if needed
                    existing_record = existing_join.data[0]
                    needs_update = (
                        existing_record.get("distance") is None or
                        existing_record.get("correlation") is None
                    )

                    if needs_update:
                        update_data = {
                            "distance": comp.get("distance"),
                            "correlation": comp.get("correlation")
                        }

                        update_query = (
                            self.supabase.table("sale_comp_to_property")
                            .update(update_data)
                            .eq("id", existing_record["id"])
                        )
                        update_response = update_query.execute()

                        if hasattr(update_response, "data"):
                            comps_saved += 1
                    continue

                # Create new relationship
                join_row = {
                    "comp_id": comp.get("id"),
                    "address1": address1,
                    "distance": comp.get("distance"),
                    "correlation": comp.get("correlation")
                }

                query2 = self.supabase.table("sale_comp_to_property").insert(join_row)
                response2 = query2.execute()

                if hasattr(response2, "data"):
                    comps_saved += 1

            except Exception as e:
                self.console.print(f"[yellow]Error saving comparable {comp_row.get('id', 'unknown')}: {str(e)}[/yellow]")
                continue

        return comps_saved

    def run_add_property_values_script(self, properties_df):
        """
        Add property valuations to all properties by calling RentCast API.
        Skips properties that already have est_price values.
        """
        # Initialize tracking variables
        total = len(properties_df)
        updated = 0
        skipped = 0
        errors = 0
        comps_saved = 0

        # Collect data for summary table
        summary_data = []

        self.console.print(f"\n[bold cyan]Starting property valuation for {total} properties...[/bold cyan]\n")

        # Iterate through each property
        for i, (_, row) in enumerate(properties_df.iterrows(), 1):
            address1 = row.get('address1', 'Unknown')

            # Print progress every property
            self.console.print(f"[cyan]{i}/{total}[/cyan] Processing: {address1}")

            # Skip if property already has est_price
            if pd.notna(row.get('est_price')) and row.get('est_price', 0) > 0:
                self.console.print(f"  [yellow]→ Skipped (already has valuation)[/yellow]")
                skipped += 1
                continue

            # Validate required fields
            full_address = row.get('full_address')
            square_ft = row.get('square_ft')
            beds = row.get('beds')
            baths = row.get('baths')
            units = row.get('units', 0)

            if not full_address or pd.isna(square_ft) or pd.isna(beds) or pd.isna(baths):
                self.console.print(f"  [red]✗ Error: Missing required fields[/red]")
                errors += 1
                continue

            # Determine property type
            property_type = "Single Family" if units == 0 else "Multi-Family"

            # Make RentCast API call
            try:
                response = requests.get(
                    "https://api.rentcast.io/v1/avm/value",
                    headers=RENTCAST_HEADERS,
                    params={
                        "address": full_address,
                        "propertyType": property_type,
                        "squareFootage": int(square_ft),
                        "bedrooms": int(beds),
                        "bathrooms": int(baths),
                        "maxRadius": 5,
                        "daysOld": 270,
                        "compCount": 20
                    },
                )

                # Check if request was successful
                if response.status_code != 200:
                    self.console.print(f"  [red]✗ HTTP {response.status_code}[/red]")
                    errors += 1
                    continue

                data = response.json()

                # Check for API error responses
                if 'error' in data:
                    self.console.print(f"  [red]✗ API Error: {data.get('error')}[/red]")
                    errors += 1
                    continue

                # Extract valuation data - FIXED FIELD NAMES
                est_price = data.get('price')  # Changed from 'value'
                est_price_low = data.get('priceRangeLow')  # Changed from 'valueLow'
                est_price_high = data.get('priceRangeHigh')  # Changed from 'valueHigh'
                comparables = data.get('comparables', [])

                if not est_price:
                    self.console.print(f"  [red]✗ No price in response. Keys: {list(data.keys())}[/red]")
                    errors += 1
                    continue

                # Update properties table
                update_data = {
                    "est_price": est_price,
                    "est_price_low": est_price_low,
                    "est_price_high": est_price_high,
                }

                query = self.supabase.table("properties").update(update_data).eq("address1", address1)
                result = query.execute()

                if hasattr(result, "data") and result.data:
                    updated += 1
                    self.console.print(f"  [green]✓ Saved: ${est_price:,}[/green]")

                    # Save comparables to database
                    if comparables:
                        saved_count = self.save_sale_comps_to_db(comparables, address1)
                        comps_saved += saved_count
                        self.console.print(f"    [dim]→ Saved {saved_count} comparables[/dim]")

                    # Collect data for summary table
                    summary_data.append({
                        'address1': address1,
                        'purchase_price': row.get('purchase_price', 0),
                        'est_price': est_price,
                        'est_price_low': est_price_low,
                        'est_price_high': est_price_high,
                    })
                else:
                    self.console.print(f"  [red]✗ Database update failed[/red]")
                    errors += 1

            except Exception as e:
                self.console.print(f"  [red]✗ Exception: {type(e).__name__}: {str(e)}[/red]")
                errors += 1
                continue

        # Display summary panel
        self.console.print("\n")
        success_rate = (updated / total * 100) if total > 0 else 0
        self.console.print(Panel(
            f"""[bold cyan]Property Valuation Script Complete![/bold cyan]

Total Properties: {total}
Successfully Updated: [green]{updated}[/green]
Skipped (already has values): [yellow]{skipped}[/yellow]
Errors: [red]{errors}[/red]
Success Rate: {success_rate:.1f}%
Comparables Saved: [green]{comps_saved}[/green]
""",
            title="Summary",
            border_style="cyan"
        ))

        # Display value comparison table
        if summary_data:
            display_property_value_comparison(self.console, summary_data)
        else:
            self.console.print("[dim]No properties were updated, so no comparison table to display[/dim]")

    def run_market_research_automation_script(self, properties_df):
        """
        Automate market research generation for Phase 0 properties lacking research.

        For each property:
        - Generates per-unit/per-room rent research
        - Generates property-wide research (SFH only)
        - Updates database with estimates
        - Marks property as researched

        Args:
            properties_df: DataFrame of Phase 0 properties to process
        """
        # Filter to properties lacking market research
        lacking_research_df = properties_df[properties_df['has_market_research'] == False].copy()

        # Initialize tracking variables
        total = len(lacking_research_df)
        successfully_researched = 0
        skipped = 0
        errors = 0

        self.console.print(f"\n[bold cyan]Starting market research automation for {total} properties...[/bold cyan]\n")

        # Process each property
        for i, (_, row) in enumerate(lacking_research_df.iterrows(), 1):
            address1 = row.get('address1', 'Unknown')

            # Print progress
            self.console.print(f"[cyan]{i}/{total}[/cyan] Processing: {address1}")

            # Skip check - verify still needs research (defensive programming)
            if pd.notna(row.get('has_market_research')) and row.get('has_market_research') == True:
                self.console.print(f"  [yellow]→ Skipped (already has research)[/yellow]")
                skipped += 1
                continue

            try:
                # Generate rent research (per-unit/per-room + property-wide for SFH)
                # This handles everything: research generation, estimate extraction, DB updates
                handle_rent_research_after_add(
                    property_id=address1,
                    supabase=self.supabase,
                    console=self.console,
                    ask_user=False  # Non-interactive mode
                )

                # Mark property as researched
                mark_result = mark_property_as_researched(
                    supabase=self.supabase,
                    address1=address1
                )

                # Check if marking succeeded
                if mark_result == False:
                    self.console.print(f"  [yellow]⚠ Research completed but failed to mark property as researched[/yellow]")
                    # Still count as success since research was generated

                successfully_researched += 1
                self.console.print(f"  [green]✓ Research completed and saved[/green]")

            except Exception as e:
                self.console.print(f"  [red]✗ Error: {type(e).__name__}: {str(e)}[/red]")
                errors += 1
                continue

        # Display summary panel
        self.console.print("\n")
        success_rate = (successfully_researched / total * 100) if total > 0 else 0
        self.console.print(Panel(
            f"""[bold cyan]Market Research Automation Complete![/bold cyan]

Total Properties: {total}
Successfully Researched: [green]{successfully_researched}[/green]
Skipped (already researched): [yellow]{skipped}[/yellow]
Errors: [red]{errors}[/red]
Success Rate: {success_rate:.1f}%
""",
            title="Summary",
            border_style="cyan"
        ))

    def run_add_missing_neighborhoods(self, properties_df):
        lacking_neighborhoods_df = properties_df[properties_df["neighborhood"].isna()].copy()

        total = len(lacking_neighborhoods_df)
        successfully_found = 0
        skipped = 0
        errors = 0

        self.console.print(
            f"\n[bold cyan]Starting finding neighborhood automation for {total} properties...[/bold cyan]\n"
        )

        for i, (_, row) in enumerate(lacking_neighborhoods_df.iterrows(), 1):
            self.console.print(f"[cyan]{i}/{total}[/cyan] Processing: {row.get("address1")}")

            if pd.notna(row.get("neighborhood")):
                self.console.print(f"  [yellow]→ Skipped (already has research)[/yellow]")
                skipped += 1
                continue
            
            try:
                neighborhood = self.neighborhood_scraper.get_neighborhood_by_address(row.get("full_address"))
            except Exception as e:
                self.console.print(f"  [red]✗ Error: {type(e).__name__}: {str(e)}[/red]")
                errors += 1
                continue

            try:
                neighborhood_id, was_created = self.neighborhood_client.get_or_create_neighborhood(neighborhood_name=neighborhood, supabase=self.supabase)
                self.neighborhood_client.assign_neighborhood_to_property(property_id=row.get("address1"), neighborhood_id=neighborhood_id)

                if was_created:
                    self.console.print(f"[green]✅ Neighborhood '{neighborhood}' was newly added to database[/green]")

                self.console.print(f"[green]✅ Neighborhood updated to '{neighborhood}' in database[/green]")
            except Exception as e:
                self.console.print(f"  [red]✗ Error: {type(e).__name__}: {str(e)}[/red]")
                errors += 1
                continue
            
            successfully_found += 1
        
        self.console.print("\n")
        success_rate = (successfully_found / total * 100) if total > 0 else 0
        self.console.print(
            Panel(
                f"""[bold cyan]Neighborhood Automation Complete![/bold cyan]

Total Properties: {total}
Successfully Researched: [green]{successfully_found}[/green]
Skipped (already researched): [yellow]{skipped}[/yellow]
Errors: [red]{errors}[/red]
Success Rate: {success_rate:.1f}%
""",
                title="Summary",
                border_style="cyan",
            )
        )

