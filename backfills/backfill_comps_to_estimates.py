import os

from dotenv import load_dotenv
from rich.console import Console
from rich.progress import track
from supabase import Client, create_client

from add_property import get_rental_estimations_multifamily, save_comps_to_db

load_dotenv()

console = Console()

def setup_supabase_client() -> Client:
    """Setup and return Supabase client"""
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in environment variables")
    
    return create_client(supabase_url, supabase_key)

def get_all_properties(supabase: Client):
    """Fetch all properties from the database"""
    try:
        response = supabase.table("properties").select("*").execute()
        if response.data:
            console.print(f"Found {len(response.data)} properties to process", style="green")
            return response.data
        else:
            console.print("No properties found in database", style="yellow")
            return []
    except Exception as e:
        console.print(f"Error fetching properties: {e}", style="red")
        raise

def get_rent_estimates_for_property(supabase: Client, address1: str):
    """Fetch all rent estimates for a specific property"""
    try:
        response = supabase.table("rent_estimates").select("*").eq("address1", address1).execute()
        if response.data:
            console.print(f"Found {len(response.data)} rent estimates for {address1}", style="green")
            return response.data
        else:
            console.print(f"No rent estimates found for {address1}", style="yellow")
            return []
    except Exception as e:
        console.print(f"Error fetching rent estimates for {address1}: {e}", style="red")
        raise

def create_property_data_from_db(property_record):
    """Convert database property record to the format expected by get_rental_estimations"""
    return {
        "full_address": property_record["full_address"],
        "zillow_link": property_record.get("zillow_link", ""),
        "purchase_price": property_record.get("purchase_price", 0),
        "address1": property_record["address1"],
        "beds": property_record["beds"],
        "baths": property_record["baths"],
        "square_ft": property_record["square_ft"],
        "built_in": property_record.get("built_in", 0),
        "units": property_record["units"],
    }

def create_unit_configs_from_rent_estimates(rent_estimates, address1):
    """Convert rent estimates to unit configurations format expected by get_rental_estimations"""
    unit_configs = []
    
    for rent_estimate in rent_estimates:
        unit_config = {
            "address1": address1,
            "unit_num": rent_estimate["unit_num"],
            "beds": str(rent_estimate["beds"]),  # get_rental_estimations expects string
            "baths": str(rent_estimate["baths"]),  # get_rental_estimations expects string
            "rent_estimate": rent_estimate.get("rent_estimate", 0),
            "rent_estimate_low": rent_estimate.get("rent_estimate_low", 0),
            "rent_estimate_high": rent_estimate.get("rent_estimate_high", 0),
            "estimated_sqrft": rent_estimate.get("estimated_sqrft", 0),
        }
        unit_configs.append(unit_config)
    
    return unit_configs

def backfill_comparables_for_property(supabase: Client, property_record):
    """Backfill comparables for a single property"""
    address1 = property_record["address1"]
    console.print(f"\nProcessing property: {address1}", style="bold blue")
    
    try:
        # Get rent estimates for this property
        rent_estimates = get_rent_estimates_for_property(supabase, address1)
        
        if not rent_estimates:
            console.print(f"Skipping {address1} - no rent estimates found", style="yellow")
            return
        
        # Create property data and unit configs
        property_data = create_property_data_from_db(property_record)
        unit_configs = create_unit_configs_from_rent_estimates(rent_estimates, address1)
        
        console.print(f"Fetching new rental comparables for {len(unit_configs)} units...", style="cyan")
        
        # Get fresh rental estimations and comparables
        updated_unit_configs, comparables = get_rental_estimations_multifamily(property_data, unit_configs)
        
        # Save comparables for each unit
        for i, unit_comparables in enumerate(comparables):
            if unit_comparables:  # Only save if there are comparables
                rent_estimate = rent_estimates[i]
                rent_estimate_id = rent_estimate["id"]
                
                console.print(f"Saving {len(unit_comparables)} comparables for unit {rent_estimate['unit_num']}", style="green")
                save_comps_to_db(unit_comparables, rent_estimate_id, supabase)
            else:
                console.print(f"No comparables found for unit {rent_estimates[i]['unit_num']}", style="yellow")
                
        console.print(f"✓ Completed backfill for {address1}", style="bold green")
        
    except Exception as e:
        console.print(f"✗ Error processing {address1}: {e}", style="bold red")
        raise

def main():
    """Main backfill function"""
    console.print("Starting comparables backfill process...", style="bold magenta")
    
    try:
        # Setup Supabase client
        supabase = setup_supabase_client()
        console.print("✓ Connected to Supabase", style="green")
        
        # Get all properties
        properties = get_all_properties(supabase)
        
        if not properties:
            console.print("No properties to process. Exiting.", style="yellow")
            return
        
        # Process each property
        console.print(f"\nProcessing {len(properties)} properties...", style="bold")
        
        for property_record in track(properties, description="Backfilling comparables..."):
            backfill_comparables_for_property(supabase, property_record)
        
        console.print("\n✓ Backfill process completed successfully!", style="bold green")
        
    except Exception as e:
        console.print(f"\n✗ Backfill process failed: {e}", style="bold red")
        raise

if __name__ == "__main__":
    main()
