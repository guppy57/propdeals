import os
import unicodedata
from dotenv import load_dotenv
from supabase import create_client, Client
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

load_dotenv()
console = Console()

# Validate environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    console.print("[red]ERROR: SUPABASE_URL and SUPABASE_KEY must be set in environment[/red]")
    exit(1)

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def normalize_neighborhood_name(name):
    """
    Normalize neighborhood name by:
    - Trimming whitespace
    - Normalizing unicode characters (é -> e)
    - Converting to lowercase

    This ensures consistent storage and prevents duplicates like "Café" vs "Cafe".
    """
    if not name:
        return None
    cleaned = name.strip()
    if not cleaned:
        return None

    # Normalize unicode (NFKD decomposes accented characters)
    # Example: "Café" becomes "Cafe", "Montréal" becomes "Montreal"
    normalized = unicodedata.normalize('NFKD', cleaned)
    # Remove diacritical marks
    normalized = ''.join(c for c in normalized if not unicodedata.combining(c))

    return normalized.lower()

def get_or_create_neighborhood(neighborhood_name, neighborhood_cache):
    """
    Get existing neighborhood ID or create a new neighborhood atomically.
    Uses normalized name for both lookup and storage to ensure consistency.

    Args:
        neighborhood_name: Original neighborhood name from property
        neighborhood_cache: Dictionary mapping normalized names to (ID, was_created) tuples

    Returns:
        Tuple of (neighborhood_id, was_created) where was_created is True if newly created
        Returns (None, False) if error
    """
    # Normalize for lookup and storage
    normalized_name = normalize_neighborhood_name(neighborhood_name)
    if not normalized_name:
        return (None, False)

    # Check cache first
    if normalized_name in neighborhood_cache:
        cached_id, _ = neighborhood_cache[normalized_name]
        return (cached_id, False)  # Already exists, not newly created

    try:
        # Check if neighborhood exists in database (exact match on normalized name)
        response = supabase.table('neighborhoods')\
            .select('id, name')\
            .eq('name', normalized_name)\
            .limit(1)\
            .execute()

        if response.data and len(response.data) > 0:
            # Neighborhood exists, cache and return
            neighborhood_id = response.data[0]['id']
            neighborhood_cache[normalized_name] = (neighborhood_id, False)
            return (neighborhood_id, False)

        # Neighborhood doesn't exist, create it
        insert_response = supabase.table('neighborhoods').insert(
            {'name': normalized_name}
        ).execute()

        if insert_response.data and len(insert_response.data) > 0:
            neighborhood_id = insert_response.data[0]['id']
            neighborhood_cache[normalized_name] = (neighborhood_id, True)
            return (neighborhood_id, True)

        return (None, False)

    except Exception as e:
        console.print(f"[red]Error creating/fetching neighborhood '{normalized_name}': {e}[/red]")
        return (None, False)

def main():
    console.print(Panel.fit(
        "[bold cyan]Neighborhoods Backfill Script[/bold cyan]\n"
        "Creating neighborhoods and property relationships",
        border_style="cyan"
    ))

    # Fetch all properties with neighborhood data
    console.print("\n[yellow]Fetching properties from database...[/yellow]")
    try:
        properties_response = supabase.table('properties').select('address1, neighborhood').order('address1').execute()
        properties = properties_response.data if properties_response.data else []
    except Exception as e:
        console.print(f"[red]Error fetching properties: {e}[/red]")
        return

    console.print(f"[green]Found {len(properties)} properties to process[/green]\n")

    # Track statistics
    skipped = 0
    neighborhoods_created = 0
    relationships_created = 0
    errors = 0
    neighborhood_cache = {}

    # Process each property
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("[cyan]Processing properties...", total=len(properties))

        for i, property_data in enumerate(properties, 1):
            address1 = property_data.get('address1')
            neighborhood_name = property_data.get('neighborhood')

            progress.update(task, advance=1, description=f"[cyan]Processing {i}/{len(properties)}: {address1}")

            # Skip if no neighborhood
            if not neighborhood_name or not neighborhood_name.strip():
                skipped += 1
                continue

            try:
                # Get or create neighborhood (returns tuple: (id, was_created))
                neighborhood_id, was_created = get_or_create_neighborhood(neighborhood_name, neighborhood_cache)

                if not neighborhood_id:
                    errors += 1
                    console.print(f"[red]✗ Failed to get/create neighborhood for {address1}[/red]")
                    continue

                # Track if we created a new neighborhood
                if was_created:
                    neighborhoods_created += 1
                    normalized_name = normalize_neighborhood_name(neighborhood_name)
                    console.print(f"[green]+ Created neighborhood: {normalized_name}[/green]")

                # Create property-neighborhood relationship
                # Check if relationship already exists first
                try:
                    # Check if relationship exists
                    existing_relationship = supabase.table('property_neighborhood')\
                        .select('*')\
                        .eq('neighborhood_id', neighborhood_id)\
                        .eq('address1', address1)\
                        .limit(1)\
                        .execute()

                    if existing_relationship.data and len(existing_relationship.data) > 0:
                        # Relationship already exists, skip
                        relationships_created += 1
                    else:
                        # Create new relationship
                        relationship_response = supabase.table('property_neighborhood').insert({
                            'neighborhood_id': neighborhood_id,
                            'address1': address1
                        }).execute()

                        if relationship_response.data:
                            relationships_created += 1
                        else:
                            errors += 1
                            console.print(f"[red]✗ Failed to create relationship for {address1} - no data returned[/red]")

                except Exception as relationship_error:
                    errors += 1
                    console.print(f"[red]✗ Failed to create relationship for {address1}: {relationship_error}[/red]")

            except Exception as e:
                errors += 1
                console.print(f"[red]✗ Error processing {address1}: {e}[/red]")

    # Display summary
    console.print("\n" + "="*60)
    console.print(Panel.fit(
        f"[bold green]Backfill Complete![/bold green]\n\n"
        f"Total Properties: [cyan]{len(properties)}[/cyan]\n"
        f"Skipped (no neighborhood): [yellow]{skipped}[/yellow]\n"
        f"Unique Neighborhoods Created: [green]{neighborhoods_created}[/green]\n"
        f"Relationships Created: [green]{relationships_created}[/green]\n"
        f"Errors: [red]{errors}[/red]",
        border_style="green" if errors == 0 else "yellow"
    ))

if __name__ == "__main__":
    main()
