import os
import time
from datetime import date, timedelta
import math

import questionary
import requests
from dotenv import load_dotenv
from rich.console import Console
from display import display_property_details, display_unit_configs

load_dotenv()

RENTCAST_HEADERS = {
    "accept": "application/json",
    "X-Api-Key": os.getenv("RENTCAST_KEY"),
}

console = Console()

def get_rental_estimations_multifamily(property_details, unit_configs):
    total_beds = property_details["beds"]
    total_baths = property_details["baths"] * 0.5
    total = total_beds + total_baths
    comparables = []

    for unit in unit_configs:
        beds_val = float(float(unit["beds"]) / total)
        baths_val = float((float(unit["baths"]) * 0.5) / total)
        sqrft = property_details["square_ft"] * (beds_val + baths_val)

        try:
            request = requests.get(
                "https://api.rentcast.io/v1/avm/rent/long-term",
                headers=RENTCAST_HEADERS,
                params={
                    "address": property_details["full_address"],
                    "propertyType": "Multi-Family",
                    "bedrooms": unit["beds"],
                    "bathrooms": unit["baths"],
                    "squareFootage": sqrft,
                    "maxRadius": 1,
                    "compCount": 25,
                },
            )

            data = request.json()
        except Exception as e:
            console.print(e, style="bold red")
            console.print(
                "Something went wrong when trying to pull rental estimate for multifamily",
                style="bold red",
            )
            return None, None

        unit["rent_estimate"] = int(float(data["rent"]))
        unit["rent_estimate_low"] = int(float(data["rentRangeLow"]))
        unit["rent_estimate_high"] = int(float(data["rentRangeHigh"]))
        unit["estimated_sqrft"] = int(float(sqrft))
        comparables.append(data["comparables"])

    return unit_configs, comparables

def get_rental_estimations_singlefamily(property_details):
    try:
        request = requests.get(
            "https://api.rentcast.io/v1/avm/rent/long-term",
            headers=RENTCAST_HEADERS,
            params={
                "address": property_details["full_address"],
                "propertyType": "Single Family",
                "bedrooms": property_details["beds"],
                "bathrooms": property_details["baths"],
                "squareFootage": property_details["square_ft"],
                "maxRadius": 7,
                "compCount": 25,
            },
        )

        data = request.json()
    except Exception as e:
        console.print(e, style="bold red")
        console.print(
            "Something went wrong when trying to pull rental estimate for single family",
            style="bold red",
        )
        return None, None, None

    property_rent = {}

    try:
        mid = int(float(data["rent"]))
        low = int(float(data["rentRangeLow"]))
        high = int(float(data["rentRangeHigh"]))

        property_rent = {
            "rent_estimate": mid,
            "rent_estimate_low": low,
            "rent_estimate_high": high,
        }

        comparables = data["comparables"]
    except KeyError as e:
        console.print(f"Missing expected field in API response: {e}", style="bold red")
        return None, None, None

    total_beds = property_details["beds"]

    if total_beds <= 0:
        console.print("Invalid bedroom count (must be > 0)", style="bold red")
        return None, None, None

    rent_comps = []

    for i in range(total_beds):
        rent_comps.append({
            "address1": property_details["address1"],
            "unit_num": i + 1,
            "beds": 1,
            "baths": 0,
            "rent_estimate": math.ceil((mid * 1.3) / total_beds),
            "rent_estimate_low": math.ceil((low * 1.3) / total_beds),
            "rent_estimate_high": math.ceil((high * 1.3) / total_beds),
            "estimated_sqrft": 0
        })

    return rent_comps, comparables, property_rent

def haversine_distance(lat1, lon1, lat2, lon2):
    """
    Calculate the great circle distance between two points
    on the earth (specified in decimal degrees)
    Returns distance in miles
    """
    from math import asin, cos, radians, sin, sqrt

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))

    # Radius of earth in miles
    r = 3956

    return c * r

def make_places_request_with_retry(url, params, max_retries=3):
    """
    Make Places API request with exponential backoff retry logic

    Args:
        url: API endpoint URL
        params: Request parameters
        max_retries: Maximum number of retry attempts

    Returns:
        API response data (JSON)
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params)
            data = response.json()
            status = data.get('status')

            # Success cases - return immediately
            if status in ['OK', 'ZERO_RESULTS']:
                return data

            # REQUEST_DENIED - don't retry, it's a configuration issue
            if status == 'REQUEST_DENIED':
                error_message = data.get('error_message', 'No error message provided')
                console.print(f"  REQUEST_DENIED: {error_message}", style="bold red")
                console.print("  [yellow]Troubleshooting tips:[/yellow]")
                console.print("    • Check API key restrictions (Android/iOS keys not supported)", style="dim")
                console.print("    • Verify 'Places API Web Service' is enabled in Google Cloud Console", style="dim")
                console.print("    • Ensure API key has no IP restrictions or correct IP is whitelisted", style="dim")
                return data  # Return without retry

            # Transient errors - retry with exponential backoff
            if status in ['UNKNOWN_ERROR', 'INVALID_REQUEST'] and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 0.1  # 100ms, 200ms, 400ms
                console.print(f"    Retrying in {wait_time*1000:.0f}ms... (attempt {attempt + 1}/{max_retries})", style="green")
                time.sleep(wait_time)
                continue

            # Other errors or final attempt - return data
            if status and status != 'OK':
                error_message = data.get('error_message', 'No error message provided')
                console.print(f"  API Error ({status}): {error_message}", style="yellow")

            return data

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 0.1
                console.print(f"    Request exception: {str(e)}. Retrying in {wait_time*1000:.0f}ms...", style="green")
                time.sleep(wait_time)
            else:
                console.print(f"  Request failed after {max_retries} attempts: {str(e)}", style="bold red")
                return {'status': 'ERROR', 'error_message': str(e)}

    return {'status': 'ERROR', 'error_message': 'Max retries exceeded'}

def get_geocode_data(address):
    console.print(f"Getting geocode for: {address}", style="green")
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={
            "key": os.getenv("GOOGLE_KEY"),
            "address": address,
        },
    )

    data = response.json()
    address_components = data["results"][0]["address_components"]
    county = ""
    neighborhood = ""

    for component in address_components:
        if "administrative_area_level_2" in component["types"]:
            county = component["long_name"]
        elif "neighborhood" in component["types"]:
            neighborhood = component["long_name"]

    location = data["results"][0]["geometry"]["location"]

    return {
        "lon": location["lng"],
        "lat": location["lat"],
        "county": county,
        "neighborhood": neighborhood,
    }

def get_walkscore_data(lng, lat, address):
    console.print(f"Getting walkscore data for: {address}", style="green")
    response = requests.get(
        "https://api.walkscore.com/score",
        params={
            "format": "json",
            "transit": 1,
            "bike": 1,
            "wsapikey": os.getenv("WALKSCORE_KEY"),
            "address": address,
            "lat": lat,
            "lon": lng,
        },
    )
    data = response.json()

    try:
        transit = data["transit"]["score"]
    except KeyError:
        transit = "NA"

    try:
        bike = data["bike"]["score"]
    except KeyError:
        bike = "NA"

    return data["walkscore"], transit, bike

def get_poi_proximity_data(lat, lon, radius_miles=5):
    """
    Get proximity to important points of interest using Google Places API
    Returns distances in miles to the nearest POI of each type within the radius

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        radius_miles: Search radius in miles (default 5 miles for Des Moines area)
    """
    console.print(f"Getting POI proximity data for coordinates: ({lat}, {lon})", style="green")

    # Convert miles to meters for Google API
    radius_meters = int(radius_miles * 1609.34)

    poi_types = [
        ('gas_station', 'gas station'),
        ('school', 'school'),
        ('university', 'university'),
        ('grocery_or_supermarket', 'grocery store'),
        ('hospital', 'hospital'),
        ('park', 'park'),
        ('transit_station', 'transit station')
    ]

    results = {}

    for poi_type, poi_name in poi_types:
        try:
            # Use retry helper for robust API calls
            data = make_places_request_with_retry(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                    "location": f"{lat},{lon}",
                    "radius": radius_meters,
                    "type": poi_type,
                    "key": os.getenv("GOOGLE_KEY"),
                }
            )

            status = data.get('status')

            # Handle ZERO_RESULTS separately (not an error)
            if status == 'ZERO_RESULTS':
                console.print(f"  No {poi_name} found within {radius_miles} miles", style="green")
                results[f'{poi_type}_distance_miles'] = None
                continue

            if status == 'OK' and data.get('results'):
                # Find closest result by calculating distances
                closest_distance = float('inf')
                closest_poi = None

                for result in data['results']:
                    poi_lat = result['geometry']['location']['lat']
                    poi_lon = result['geometry']['location']['lng']
                    distance = haversine_distance(lat, lon, poi_lat, poi_lon)
                    if distance < closest_distance:
                        closest_distance = distance
                        closest_poi = result

                results[f'{poi_type}_distance_miles'] = round(closest_distance, 2)
                console.print(f"  Found nearest {poi_name}: {closest_distance:.2f} miles", style="green")
            else:
                results[f'{poi_type}_distance_miles'] = None

        except Exception as e:
            console.print(f"Error fetching {poi_name} data: {str(e)}", style="bold red")
            results[f'{poi_type}_distance_miles'] = None

    return results

def get_poi_count_data(lat, lon, radius_miles=5):
    """
    Count number of POIs within a radius using Google Places API
    Returns counts of each POI type within the specified radius
    Filters by review count to focus on established/major locations

    Args:
        lat: Latitude coordinate
        lon: Longitude coordinate
        radius_miles: Search radius in miles (default 5 miles for Des Moines area)
    """
    console.print(f"Counting POIs within {radius_miles} miles for coordinates: ({lat}, {lon})", style="green")

    # Convert miles to meters for Google API
    radius_meters = int(radius_miles * 1609.34)

    poi_types = [
        ('gas_station', 'gas station'),
        ('school', 'school'),
        ('university', 'university'),
        ('grocery_or_supermarket', 'grocery store'),
        ('hospital', 'hospital'),
        ('park', 'park'),
        ('transit_station', 'transit station')
    ]

    # Review thresholds to filter out minor/obscure locations
    review_thresholds = {
        'gas_station': 20,
        'school': 25,
        'university': 75,
        'grocery_or_supermarket': 65,
        'hospital': 100,
        'park': 5,
        'transit_station': 1
    }

    results = {}

    for poi_type, poi_name in poi_types:
        try:
            # Use retry helper for robust API calls
            data = make_places_request_with_retry(
                "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                params={
                    "location": f"{lat},{lon}",
                    "radius": radius_meters,
                    "type": poi_type,
                    "key": os.getenv("GOOGLE_KEY"),
                }
            )

            status = data.get('status')
            count = 0

            if status == 'OK' and data.get('results'):
                total_results = len(data['results'])
                min_reviews = review_thresholds.get(poi_type, 0)

                # Filter by review count
                filtered_results = [
                    place for place in data['results']
                    if place.get('user_ratings_total', 0) >= min_reviews
                ]
                count = len(filtered_results)

                # Log filtering stats
                if total_results > 0:
                    if count < total_results:
                        console.print(f"  Found {count} {poi_name}(s) (filtered from {total_results} with ≥{min_reviews} reviews)", style="green")
                    else:
                        console.print(f"  Found {count} {poi_name}(s)", style="green")
                else:
                    console.print(f"  Found {count} {poi_name}(s)", style="green")
            elif status == 'ZERO_RESULTS':
                console.print(f"  Found 0 {poi_name}s within {radius_miles} miles", style="green")
            # Error messages already handled by retry helper

            results[f'{poi_type}_count_{int(radius_miles)}mi'] = count

        except Exception as e:
            console.print(f"Error counting {poi_name}s: {str(e)}", style="bold red")
            results[f'{poi_type}_count_{int(radius_miles)}mi'] = 0

    return results

def collect_property_details():
    full_address = questionary.text("Full address").ask()
    zillow_link = questionary.text("Zillow link").ask()
    purchase_price = questionary.text("Purchase price").ask()
    property_type = questionary.select(
        "Property type",
        choices=["Single Family", "Duplex", "Triplex", "Fourplex"],
    ).ask()
    beds = questionary.text("Bedrooms").ask()
    baths = questionary.text("Bathrooms").ask()
    square_ft = questionary.text("Square footage").ask()
    built_in = questionary.text("Year built").ask()
    days_listed = questionary.text("Current days on market").ask()
    has_reduced_price = questionary.confirm("Has had price reductions?").ask()
    has_tenants = questionary.confirm("Are there current tenants?").ask()
    address1 = full_address.split(",")[0]
    unit_conversion = {"Single Family": 0, "Duplex": 2, "Triplex": 3, "Fourplex": 4}
    units = unit_conversion[property_type]
    listed_date = (date.today() - timedelta(days=int(days_listed))).isoformat() 

    return {
        "full_address": full_address.strip(),
        "zillow_link": zillow_link.strip(),
        "purchase_price": int(purchase_price),
        "address1": address1.strip(),
        "beds": int(beds),
        "baths": float(baths),
        "square_ft": int(square_ft),
        "built_in": int(built_in),
        "units": units,
        "listed_date": listed_date,
        "has_reduced_price": has_reduced_price,
        "has_tenants": has_tenants,
    }

def add_property_to_supabase(property_details, supabase) -> bool:
    try:
        geocode = get_geocode_data(property_details["full_address"])
        lon = geocode["lon"]
        lat = geocode["lat"]
        console.print(f"Found long: {lon} and lat: {lat}", style="green bold")
        walk, transit, bike = get_walkscore_data(
            lon, lat, property_details["full_address"]
        )
        console.print(
            f"Found walk score: {walk}, transit: {transit}, bike: {bike}",
            style="green bold",
        )
        poi_distance_data = get_poi_proximity_data(lat, lon, radius_miles=5)
        poi_count_data = get_poi_count_data(lat, lon, radius_miles=5)
        poi_data = {**poi_distance_data, **poi_count_data}
        console.print("Found POI proximity and count data", style="green bold")
    except Exception as e:
        console.print(e, style="bold red")

    property_details["walk_score"] = walk if walk != "NA" else 0
    property_details["bike_score"] = bike if bike != "NA" else 0
    property_details["transit_score"] = transit if transit != "NA" else 0
    property_details["lat"] = geocode["lat"]
    property_details["lon"] = geocode["lon"]
    property_details["county"] = geocode["county"]
    property_details.update(poi_data)

    try:
        query = supabase.table("properties").insert(property_details)
        response = query.execute()

        if hasattr(response, "data"):
            console.print(f"Response data: {response.data}", style="green")
            return response.data[0]["address1"] == property_details["address1"]
        else:
            console.print("Response has no 'data' attribute", style="green")
            return False
    except Exception as e:
        console.print(f"Exception: {e}", style="bold red")
        console.print(f"Exception type: {type(e)}", style="bold red")
        return False

def collect_unit_configurations(unit_count, address1):
    unit_configurations = []
    units_compared = 0

    while units_compared < unit_count:
        beds = questionary.text("Bedrooms (0 for Studio)").ask()
        baths = questionary.text("Bathrooms").ask()
        num_units = questionary.text("Number of units like this", default="1").ask()

        for i in range(int(num_units)):
            rent_comp = {
                "address1": address1,
                "unit_num": units_compared + i + 1,
                "beds": int(beds),
                "baths": float(baths),
                "rent_estimate": 0,
                "rent_estimate_low": 0,
                "rent_estimate_high": 0,
                "estimated_sqrft": 0,
            }
            unit_configurations.append(rent_comp)
        units_compared += int(num_units)

    return unit_configurations

def create_placeholder_unit_configs_singlefamily(address1, beds):
    """
    Creates placeholder rent estimate configs for single family properties.
    Generates one 1-bed unit per bedroom with zero values.

    Args:
        address1: Property address (street address only)
        beds: Number of bedrooms in the property

    Returns:
        List of placeholder unit configs with rent estimates set to 0
    """
    unit_configs = []
    for i in range(beds):
        unit_configs.append({
            "address1": address1,
            "unit_num": i + 1,
            "beds": 1,
            "baths": 0,
            "rent_estimate": 0,
            "rent_estimate_low": 0,
            "rent_estimate_high": 0,
            "estimated_sqrft": 0
        })
    return unit_configs

def save_comps_to_db(comps, subject_rent_id, supabase):
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
            # Check if this comparable already exists
            existing = (
                supabase.table("comparable_rents")
                .select("id")
                .eq("id", comp_row["id"])
                .execute()
            )

            if existing.data:
                console.print(
                    f"Comparable {comp_row['id']} already exists, creating new relationship...", style="green"
                )
            else:
                query = supabase.table("comparable_rents").insert(comp_row)
                response = query.execute()

                if hasattr(response, "data"):
                    console.print(f"Response data: {response.data} (save_comps_to_db)", style="green")
                else:
                    console.print("Response has no 'data' attribute (save_comps_to_db)", style="green")

            existing_join = (
                supabase.table("rent_comp_to_rent_estimate")
                .select("id, distance, correlation")
                .eq("estimate_id", subject_rent_id)
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
                    console.print(
                        f"Updating distance/correlation for existing relationship: {comp_row['id']} <-> {subject_rent_id}", style="green"
                    )
                    update_data = {
                        "distance": comp.get("distance"),
                        "correlation": comp.get("correlation")
                    }

                    update_query = (
                        supabase.table("rent_comp_to_rent_estimate")
                        .update(update_data)
                        .eq("id", existing_record["id"])
                    )
                    update_response = update_query.execute()

                    if hasattr(update_response, "data"):
                        console.print(f"Updated relationship data: {update_response.data}", style="green")
                    else:
                        console.print("Update response has no 'data' attribute", style="green")
                else:
                    console.print(
                        f"{comp_row['id']} and rent estimate {subject_rent_id} are already joined with complete data, skipping..", style="green"
                    )
                continue

            join_row = {
                "comp_id": comp.get("id"), 
                "estimate_id": subject_rent_id,
                "distance": comp.get("distance"),
                "correlation": comp.get("correlation")
            }

            query2 = supabase.table("rent_comp_to_rent_estimate").insert(join_row)
            response2 = query2.execute()

            if hasattr(response2, "data"):
                console.print(f"Response2 data: {response2.data} (save_comps_to_db)", style="green")
            else:
                console.print("Response2 has no 'data' attribute (save_comps_to_db)", style="green")
        except Exception as e:
            console.print(f"Exception: {e} (save_comps_to_db)", style="bold red")
            console.print(f"Exception type: {type(e)} (save_comps_to_db)", style="bold red")

def save_property_comps_to_db(comps, address1, supabase):
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
            # Check if this comparable already exists
            existing = (
                supabase.table("comparable_rents")
                .select("id")
                .eq("id", comp_row["id"])
                .execute()
            )

            if existing.data:
                console.print(
                    f"Comparable {comp_row['id']} already exists, creating new relationship...", style="green"
                )
            else:
                query = supabase.table("comparable_rents").insert(comp_row)
                response = query.execute()

                if hasattr(response, "data"):
                    console.print(f"Response data: {response.data} (save_property_comps_to_db)", style="green")
                else:
                    console.print("Response has no 'data' attribute (save_property_comps_to_db)", style="green")

            existing_join = (
                supabase.table("rent_comp_to_property")
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
                    console.print(
                        f"Updating distance/correlation for existing relationship: {comp_row['id']} <-> {address1}", style="green"
                    )
                    update_data = {
                        "distance": comp.get("distance"),
                        "correlation": comp.get("correlation")
                    }

                    update_query = (
                        supabase.table("rent_comp_to_property")
                        .update(update_data)
                        .eq("id", existing_record["id"])
                    )
                    update_response = update_query.execute()

                    if hasattr(update_response, "data"):
                        console.print(f"Updated relationship data: {update_response.data}", style="green")
                    else:
                        console.print("Update response has no 'data' attribute", style="green")
                else:
                    console.print(
                        f"{comp_row['id']} and property {address1} are already joined with complete data, skipping..", style="green"
                    )
                continue

            join_row = {
                "comp_id": comp.get("id"),
                "address1": address1,
                "distance": comp.get("distance"),
                "correlation": comp.get("correlation")
            }

            query2 = supabase.table("rent_comp_to_property").insert(join_row)
            response2 = query2.execute()

            if hasattr(response2, "data"):
                console.print(f"Response2 data: {response2.data} (save_property_comps_to_db)", style="green")
            else:
                console.print("Response2 has no 'data' attribute (save_property_comps_to_db)", style="green")
        except Exception as e:
            console.print(f"Exception: {e} (save_property_comps_to_db)", style="bold red")
            console.print(f"Exception type: {type(e)} (save_property_comps_to_db)", style="bold red")

def add_rent_to_supabase(rent_comps, comparables, supabase) -> bool:
    new_ids = []

    for i, rent_comp in enumerate(rent_comps):
        try:
            console.print(f"  Upserting rent estimate for unit {i+1}/{len(rent_comps)}...", style="dim")
            query = supabase.table("rent_estimates").upsert(rent_comp, on_conflict="address1,unit_num")
            response = query.execute()
            if hasattr(response, "data"):
                console.print(f"Response data: {response.data}", style="green")
                console.print(f"  ✓ Unit {i+1} rent estimate saved", style="green")
                new_ids.append(response.data[0]["id"])
            else:
                console.print("Response has no 'data' attribute", style="green")
                return False
        except Exception as e:
            console.print(f"Exception: {e}", style="bold red")
            console.print(f"Exception type: {type(e)}", style="bold red")
            return False

    for i, unit_comparables in enumerate(comparables):
        if unit_comparables and i < len(new_ids):  # Only save if there are comparables
            console.print(f"  Saving {len(unit_comparables)} comparable rents for unit {i+1}...", style="dim")
            rent_estimate_id = new_ids[i]
            save_comps_to_db(unit_comparables, rent_estimate_id, supabase)
        elif unit_comparables and i >= len(new_ids):
            console.print(f"Warning: No rent estimate ID for comparables at index {i}, skipping", style="bold red")

    return True

def add_rent_to_supabase_singlefamily(address1, unit_configs_w_rent, property_comparables, property_rent, supabase) -> bool:
    try:
        console.print("  Updating property rent data...", style="dim")
        query = supabase.table("properties").update(property_rent).eq("address1", address1)
        response = query.execute()
        if hasattr(response, "data"):
            console.print(f"Response data: {response.data}", style="green")
            console.print("  ✓ Property rent data updated", style="green")
        else:
            console.print("Response has no 'data' attribute (update call)", style="red")
            return False
    except Exception as e:
        console.print(f"Exception: {e}", style="bold red")
        console.print(f"Exception type: {type(e)}", style="bold red")
        return False

    for i, unit_config in enumerate(unit_configs_w_rent):
        try:
            console.print(f"  Upserting rent estimate for unit {i+1}/{len(unit_configs_w_rent)}...", style="dim")
            query = supabase.table("rent_estimates").upsert(unit_config, on_conflict="address1,unit_num")
            response = query.execute()
            if hasattr(response, "data"):
                console.print(f"Response data: {response.data}", style="green")
                console.print(f"  ✓ Unit {i+1} rent estimate saved", style="green")
            else:
                console.print("Response has no 'data' attribute (insert call)", style="red")
                return False
        except Exception as e:
            console.print(f"Exception: {e}", style="bold red")
            console.print(f"Exception type: {type(e)}", style="bold red")
            return False

    if property_comparables:
        console.print(f"  Saving {len(property_comparables)} comparable rents...", style="dim")
        save_property_comps_to_db(property_comparables, address1, supabase)
    return True

def mark_property_as_researched(supabase, address1):
    try:
        query = supabase.table("properties").update({ "has_market_research": True }).eq("address1", address1)
        response = query.execute()
        if hasattr(response, "data"):
            console.print(f"Response data: {response.data}", style="green")
            console.print("  ✓ Property marked as researched", style="green")
        else:
            console.print("Response has no 'data' attribute (mark_property_as_researched)", style="red")
            return False
    except Exception as e:
        console.print(f"Exception: {e}", style="bold red")
        console.print(f"Exception type: {type(e)}", style="bold red")
        return False

def run_add_property(
    supabase_client,
    reload_df_callback,
    get_all_phase0_qualifying_properties,
    get_reduced_pp_df,
    phase0_criteria
):
    console.print("Let's add a new property to analyze", style="bold red")
    proceed = False
    property_details = {}

    while not proceed:
        property_details = collect_property_details()
        display_property_details(console, property_details=property_details)
        proceed = questionary.confirm("Does everything look correct?").ask()
        if not proceed:
            console.print("Add the property details again", style="bold blue")

    console.print("Adding property details to Supabase...", style="bold cyan")
    succeeded = add_property_to_supabase(property_details, supabase_client)

    if not succeeded:
        console.print(
            "Something went wrong when adding the property, exiting early",
            style="bold red",
        )
        return

    console.print("Property details added to Supabase", style="bold green")
    proceed2 = False
    unit_configs = []

    while not proceed2 and property_details["units"] != 0:
        unit_count = property_details["units"]
        console.print(
            f"Let's now add our rent comparables for this property.\nWe will add details for the {unit_count} units.",
            style="bold blue",
        )
        unit_configs = collect_unit_configurations(unit_count, property_details["address1"])
        display_unit_configs(console, unit_configs)
        proceed2 = questionary.confirm("Does everything look correct?").ask()
        if not proceed2:
            console.print("Add the rent comparables again", style="bold blue")

    console.print("Adding unit configurations for Phase 0 qualification check...", style="bold cyan")
    if property_details["units"] != 0:
        # Multifamily: unit_configs already collected from user via collect_unit_configurations()
        succeeded_1 = add_rent_to_supabase(unit_configs, [], supabase_client)
    else:
        # Single family: Generate placeholder unit configs (one 1-bed unit per bedroom)
        placeholder_unit_configs = create_placeholder_unit_configs_singlefamily(
            address1=property_details["address1"],
            beds=property_details["beds"]
        )
        succeeded_1 = add_rent_to_supabase_singlefamily(
            address1=property_details['address1'],
            unit_configs_w_rent=placeholder_unit_configs,
            property_comparables=None,
            property_rent={},
            supabase=supabase_client
        )

    if not succeeded_1:
        console.print("Adding basic unit configurations and rent comparison for Phase 0 check failed", style="bold red")
        return None

    console.print("✓ Unit configurations added", style="green")
    console.print("Evaluating Phase 0 qualification criteria...", style="bold cyan")
    reload_df_callback()
    phase0_df = get_all_phase0_qualifying_properties()
    is_valid_current = (phase0_df['address1'] == property_details["address1"]).any()
    reduced_df = get_reduced_pp_df(0.10)
    filtered_df = reduced_df.query(phase0_criteria).copy()
    is_valid_contingent = (filtered_df['address1'] == property_details["address1"]).any()
    passes_phase0 = False

    if is_valid_contingent or is_valid_current:
        passes_phase0 = True
        qual_type = "CONTINGENT" if (is_valid_contingent and not is_valid_current) else "CURRENT"
        console.print(f"{property_details['address1']} qualifies for Phase 0: {qual_type}", style="bold green")
        if property_details["units"] != 0:
            console.print("Fetching rental estimations from RentCast API...", style="bold cyan")
            rent_comps, comparables = get_rental_estimations_multifamily(property_details, unit_configs)
            if rent_comps is None or comparables is None:
                console.print("Failed to get rental estimations for multifamily property", style="bold red")
                return
            console.print("✓ Rental estimations retrieved successfully", style="green")
            console.print("Updating database with rental estimations and comparables...", style="bold cyan")
            succeeded2 = add_rent_to_supabase(rent_comps, comparables, supabase_client)
        else:
            console.print("Fetching rental estimations from RentCast API...", style="bold cyan")
            unit_configs_w_rent, comparables, property_rent = get_rental_estimations_singlefamily(property_details)
            if unit_configs_w_rent is None or comparables is None or property_rent is None:
                console.print("Failed to get rental estimations for single family property", style="bold red")
                return
            console.print("✓ Rental estimations retrieved successfully", style="green")
            console.print("Updating database with rental estimations and comparables...", style="bold cyan")
            succeeded2 = add_rent_to_supabase_singlefamily(property_details["address1"], unit_configs_w_rent, comparables, property_rent, supabase_client)

        if not succeeded2:
            console.print("Something went wrong when adding rent comps", style="bold red")
            return
        
        mark_property_as_researched(supabase_client, property_details['address1'])
        console.print("Property and rent comps added to Supabase", style="bold green")
    else:
        console.print(f"{property_details['address1']} DOES NOT QUALIFY FOR PHASE 0", style="bold red")

    return property_details, passes_phase0
