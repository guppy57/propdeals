import os
from dotenv import load_dotenv
from supabase import create_client, Client
from rich.console import Console
from rich.panel import Panel
from add_property import get_poi_proximity_data, get_poi_count_data

# Load environment variables
load_dotenv()

# Initialize Supabase client
console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

console.print("[bold cyan]Starting POI Proximity & Count Backfill[/bold cyan]\n")
console.print("[dim]This will fetch distance to nearest POIs and count POIs within 5 miles:[/dim]")
console.print("[dim]- Gas stations, Schools, Universities, Grocery stores, Hospitals, Parks, Transit stations[/dim]\n")

# Get all properties from Supabase
console.print("[yellow]Fetching all properties from database...[/yellow]")
properties_response = supabase.table('properties').select('address1, lat, lon').order('address1').execute()
properties = properties_response.data if properties_response.data else []

total = len(properties)
console.print(f"[green]Found {total} properties to process[/green]\n")

# Track statistics
updated = 0
errors = 0

# Process each property
for i, property in enumerate(properties, 1):
    address1 = property['address1']
    lat = property.get('lat')
    lon = property.get('lon')

    if not lat or not lon:
        console.print(f"[yellow]{i}/{total} - Skipping {address1}: Missing lat/lon coordinates[/yellow]")
        errors += 1
        continue

    console.print(f"[cyan]{i}/{total} - Processing: {address1}[/cyan]")

    try:
        # Get POI proximity data for the property (distance to nearest)
        poi_distance_data = get_poi_proximity_data(lat, lon, radius_miles=5)

        # Get POI count data for the property (count within 5 miles)
        poi_count_data = get_poi_count_data(lat, lon, radius_miles=5)

        # Merge both datasets
        poi_data = {**poi_distance_data, **poi_count_data}

        # Update POI distance and count fields
        result = (
            supabase.table("properties")
            .update(poi_data)
            .eq("address1", address1)
            .execute()
        )

        if result.data:
            updated += 1
            # Display summary
            found_distances = sum(1 for v in poi_distance_data.values() if v is not None)
            total_count = sum(poi_count_data.values())
            console.print(f"[green]  ✅ Updated {found_distances} distances, {total_count} total POIs counted[/green]")
        else:
            errors += 1
            console.print("[red]  ❌ Update failed: No data returned from database[/red]")

    except Exception as e:
        errors += 1
        console.print(f"[red]  ❌ Error: {str(e)}[/red]")

# Display summary
console.print("\n")
console.print(Panel(f"""
[bold cyan]Backfill Complete![/bold cyan]

Total Properties: {total}
Successfully Updated: [green]{updated}[/green]
Errors: [red]{errors}[/red]
Success Rate: {(updated/total*100) if total > 0 else 0:.1f}%

[bold]Data collected per property:[/bold]
- Distance to nearest POI (7 types)
- Count of POIs within 5 miles (7 types)

[dim]Note: ~14 API calls per property were made to Google Places API
Estimated cost: ${(updated * 14 * 0.032 / 1000):.4f}[/dim]
""", title="POI Proximity & Count Backfill Summary", border_style="cyan"))
