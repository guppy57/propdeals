import os
from dotenv import load_dotenv
from supabase import create_client, Client
from rich.console import Console
from rich.panel import Panel
from add_property import get_geocode_data

# Load environment variables
load_dotenv()

# Initialize Supabase client
console = Console()
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

console.print("[bold cyan]Starting County & Neighborhood Backfill[/bold cyan]\n")

# Get all properties from Supabase
console.print("[yellow]Fetching all properties from database...[/yellow]")
properties_response = supabase.table('properties').select('*').order('address1').execute()
properties = properties_response.data if properties_response.data else []

total = len(properties)
console.print(f"[green]Found {total} properties to process[/green]\n")

# Track statistics
updated = 0
errors = 0

# Process each property
for i, property in enumerate(properties, 1):
    address1 = property['address1']
    full_address = property.get('full_address')

    if not full_address:
        console.print(f"[yellow]{i}/{total} - Skipping {address1}: No full_address[/yellow]")
        errors += 1
        continue

    console.print(f"[cyan]{i}/{total} - Processing: {address1}[/cyan]")

    try:
        # Get geocode data for the property
        geocode_data = get_geocode_data(full_address)

        # Update only county and neighborhood fields
        result = (
            supabase.table("properties")
            .update({
                "county": geocode_data["county"],
                "neighborhood": geocode_data["neighborhood"]
            })
            .eq("address1", address1)
            .execute()
        )

        if result.data:
            updated += 1
            console.print(f"[green]  ✅ Updated: County={geocode_data['county']}, Neighborhood={geocode_data['neighborhood']}[/green]")
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
""", title="Summary", border_style="cyan"))
