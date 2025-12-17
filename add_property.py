import os
import time
from datetime import date, timedelta
import math

import questionary
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
        return None, None

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
        return None, None

    total_beds = property_details["beds"]

    if total_beds <= 0:
        console.print("Invalid bedroom count (must be > 0)", style="bold red")
        return None, None

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

def get_political_districts(address):
    pass

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
                print(f"    Retrying in {wait_time*1000:.0f}ms... (attempt {attempt + 1}/{max_retries})")
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
                print(f"    Request exception: {str(e)}. Retrying in {wait_time*1000:.0f}ms...")
                time.sleep(wait_time)
            else:
                console.print(f"  Request failed after {max_retries} attempts: {str(e)}", style="bold red")
                return {'status': 'ERROR', 'error_message': str(e)}

    return {'status': 'ERROR', 'error_message': 'Max retries exceeded'}

def get_geocode_data(address):
    print(f"Getting geocode for: {address}")
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

def get_solar_potential_data(address):
    geocode = get_geocode_data(address)
    print(f"Getting solar potential data for: {address}")
    response = requests.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        params={
            "location.latitude": geocode["lon"],
            "location.longitude": geocode["lat"],
            "requiredQuality": "HIGH",
            "key": os.getenv("GOOGLE_KEY"),
        },
    )
    data = response.json()

    # Get first viable financial analysis (panelConfigIndex != -1)
    financial = next(
        (
            fa
            for fa in data.get("solarPotential", {}).get("financialAnalyses", [])
            if fa.get("panelConfigIndex", -1) != -1
        ),
        None,
    )

    solar_potential = data.get("solarPotential", {})
    building_stats = solar_potential.get("buildingStats", {})
    whole_roof = solar_potential.get("wholeRoofStats", {})

    result = {
        # Capacity metrics
        "max_array_panels_count": solar_potential.get("maxArrayPanelsCount"),
        "max_array_area_m2": solar_potential.get("maxArrayAreaMeters2"),
        "max_sunshine_hours_per_year": solar_potential.get("maxSunshineHoursPerYear"),
        "building_area_m2": building_stats.get("areaMeters2"),
        "whole_roof_area_m2": whole_roof.get("areaMeters2"),
        "panel_capacity_watts": solar_potential.get("panelCapacityWatts"),
        # Financial metrics (if viable config exists)
        "cost_electricity_without_solar": None,
        "payback_years": None,
        "lifetime_savings": None,
        "present_value_savings_year20": None,
        "upfront_cost": None,
        "solar_percentage": None,
        "initial_ac_kwh_per_year": None,
        "net_metering_allowed": None,
    }

    if financial and "financialDetails" in financial:
        details = financial["financialDetails"]
        cash = financial.get("cashPurchaseSavings", {})

        result.update(
            {
                "cost_electricity_without_solar": int(
                    details.get("costOfElectricityWithoutSolar", {}).get("units", 0)
                ),
                "payback_years": cash.get("paybackYears"),
                "lifetime_savings": int(
                    cash.get("savings", {}).get("savingsLifetime", {}).get("units", 0)
                ),
                "present_value_savings_year20": int(
                    cash.get("savings", {})
                    .get("presentValueOfSavingsYear20", {})
                    .get("units", 0)
                ),
                "upfront_cost": int(cash.get("upfrontCost", {}).get("units", 0)),
                "solar_percentage": details.get("solarPercentage"),
                "initial_ac_kwh_per_year": details.get("initialAcKwhPerYear"),
                "net_metering_allowed": details.get("netMeteringAllowed"),
            }
        )
    return result


def get_walkscore_data(lng, lat, address):
    print(f"Getting walkscore data for: {address}")
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
    print(f"Getting POI proximity data for coordinates: ({lat}, {lon})")

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
                print(f"  No {poi_name} found within {radius_miles} miles")
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
                print(f"  Found nearest {poi_name}: {closest_distance:.2f} miles")
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
    print(f"Counting POIs within {radius_miles} miles for coordinates: ({lat}, {lon})")

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
                        print(f"  Found {count} {poi_name}(s) (filtered from {total_results} with ≥{min_reviews} reviews)")
                    else:
                        print(f"  Found {count} {poi_name}(s)")
                else:
                    print(f"  Found {count} {poi_name}(s)")
            elif status == 'ZERO_RESULTS':
                print(f"  Found 0 {poi_name}s within {radius_miles} miles")
            # Error messages already handled by retry helper

            results[f'{poi_type}_count_{int(radius_miles)}mi'] = count

        except Exception as e:
            console.print(f"Error counting {poi_name}s: {str(e)}", style="bold red")
            results[f'{poi_type}_count_{int(radius_miles)}mi'] = 0

    return results


def get_value_estimate(property_details):
    response = requests.get(
        "https://api.rentcast.io/v1/avm/value",
        headers=RENTCAST_HEADERS,
        params={
            "address": property_details["full_address"],
            "propertyType": "Multi-Family",
            "squareFootage": property_details["square_ft"],
            "bedrooms": property_details["beds"],
            "bathrooms": property_details["baths"],
            "compCount": 15,
        },
    )

    data = response.json()
    return data


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

def display_property_details(property_details):
    text = ""

    for key in property_details:
        text += f"{key}: {property_details[key]}\n"

    console.print(
        Panel(text, title="Property Details", title_align="center", padding=1)
    )


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
        solar_data = get_solar_potential_data(property_details["full_address"])
        console.print("Found solar potential data", style="green bold")
        electricity_costs = solar_data["cost_electricity_without_solar"]
        console.print(
            f"Found electricity costs: {electricity_costs}", style="green bold"
        )
    except Exception as e:
        print(e)

    property_details["walk_score"] = walk if walk != "NA" else 0
    property_details["bike_score"] = bike if bike != "NA" else 0
    property_details["transit_score"] = transit if transit != "NA" else 0
    property_details["lat"] = geocode["lat"]
    property_details["lon"] = geocode["lon"]
    property_details["annual_electricity_cost_est"] = electricity_costs
    property_details["county"] = geocode["county"]
    property_details.update(poi_data)

    try:
        query = supabase.table("properties").insert(property_details)
        response = query.execute()

        if hasattr(response, "data"):
            print(f"Response data: {response.data}")
            return response.data[0]["address1"] == property_details["address1"]
        else:
            print("Response has no 'data' attribute")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        print(f"Exception type: {type(e)}")
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
                "beds": beds,
                "baths": baths,
                "rent_estimate": 0,
                "rent_estimate_low": 0,
                "rent_estimate_high": 0,
                "estimated_sqrft": 0,
            }
            unit_configurations.append(rent_comp)
        units_compared += int(num_units)

    return unit_configurations


def display_unit_configs(rent_comps):
    table = Table(title="Rent Comparables")
    table.add_column("Unit #")
    table.add_column("Configuration", no_wrap=True)
    for comp in rent_comps:
        configuration = f"{comp["beds"]}-beds {comp["baths"]}-baths"
        table.add_row(str(comp["unit_num"]), configuration)
    console.print(table)


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
                print(
                    f"Comparable {comp_row['id']} already exists, creating new relationship..."
                )
            else:
                query = supabase.table("comparable_rents").insert(comp_row)
                response = query.execute()

                if hasattr(response, "data"):
                    print(f"Response data: {response.data} (save_comps_to_db)")
                else:
                    print("Response has no 'data' attribute (save_comps_to_db)")

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
                    print(
                        f"Updating distance/correlation for existing relationship: {comp_row['id']} <-> {subject_rent_id}"
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
                        print(f"Updated relationship data: {update_response.data}")
                    else:
                        print("Update response has no 'data' attribute")
                else:
                    print(
                        f"{comp_row['id']} and rent estimate {subject_rent_id} are already joined with complete data, skipping.."
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
                print(f"Response2 data: {response2.data} (save_comps_to_db)")
            else:
                print("Response2 has no 'data' attribute (save_comps_to_db)")
        except Exception as e:
            print(f"Exception: {e} (save_comps_to_db)")
            print(f"Exception type: {type(e)} (save_comps_to_db)")

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
                print(
                    f"Comparable {comp_row['id']} already exists, creating new relationship..."
                )
            else:
                query = supabase.table("comparable_rents").insert(comp_row)
                response = query.execute()

                if hasattr(response, "data"):
                    print(f"Response data: {response.data} (save_property_comps_to_db)")
                else:
                    print("Response has no 'data' attribute (save_property_comps_to_db)")

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
                    print(
                        f"Updating distance/correlation for existing relationship: {comp_row['id']} <-> {address1}"
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
                        print(f"Updated relationship data: {update_response.data}")
                    else:
                        print("Update response has no 'data' attribute")
                else:
                    print(
                        f"{comp_row['id']} and property {address1} are already joined with complete data, skipping.."
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
                print(f"Response2 data: {response2.data} (save_property_comps_to_db)")
            else:
                print("Response2 has no 'data' attribute (save_property_comps_to_db)")
        except Exception as e:
            print(f"Exception: {e} (save_property_comps_to_db)")
            print(f"Exception type: {type(e)} (save_property_comps_to_db)")

def add_rent_to_supabase(rent_comps, comparables, supabase) -> bool:
    new_ids = []

    for rent_comp in rent_comps:
        try:
            query = supabase.table("rent_estimates").insert(rent_comp)
            response = query.execute()
            if hasattr(response, "data"):
                print(f"Response data: {response.data}")
                new_ids.append(response.data[0]["id"])
            else:
                print("Response has no 'data' attribute")
                return False
        except Exception as e:
            print(f"Exception: {e}")
            print(f"Exception type: {type(e)}")
            return False

    for i, unit_comparables in enumerate(comparables):
        if unit_comparables:  # Only save if there are comparables
            rent_estimate_id = new_ids[i]
            save_comps_to_db(unit_comparables, rent_estimate_id, supabase)

    return True

def add_rent_to_supabase_singlefamily(address1, unit_configs_w_rent, property_comparables, property_rent, supabase) -> bool:
    try:
        query = supabase.table("properties").update(property_rent).eq("address1", address1)
        response = query.execute()
        if hasattr(response, "data"):
            print(f"Response data: {response.data}")
        else:
            print("Response has no 'data' attribute (update call)")
            return False
    except Exception as e:
        print(f"Exception: {e}")
        print(f"Exception type: {type(e)}")
        return False

    for unit_config in unit_configs_w_rent:
        try:
            query = supabase.table("rent_estimates").insert(unit_config)
            response = query.execute()
            if hasattr(response, "data"):
                print(f"Response data: {response.data}")
            else:
                print("Response has no 'data' attribute (insert call)")
                return False
        except Exception as e:
            print(f"Exception: {e}")
            print(f"Exception type: {type(e)}")
            return False
    
    save_property_comps_to_db(property_comparables, address1, supabase)
    return True


def run_add_property(supabase_client) -> dict:
    console.print("Let's add a new property to analyze", style="bold red")
    proceed = False

    while not proceed:
        property_details = collect_property_details()
        display_property_details(property_details=property_details)
        proceed = questionary.confirm("Does everything look correct?").ask()
        if not proceed:
            console.print("Add the property details again", style="bold blue")

    succeeded = add_property_to_supabase(property_details, supabase_client)

    if not succeeded:
        console.print(
            "Something went wrong when adding the property, exiting early",
            style="bold red",
        )
        return

    console.print("Property details added to Supabase", style="bold green")
    proceed2 = False

    while not proceed2 and property_details["units"] != 0:
        unit_count = property_details["units"]
        console.print(
            f"Let's now add our rent comparables for this property.\nWe will add details for the {unit_count} units.",
            style="bold blue",
        )
        unit_configs = collect_unit_configurations(
            unit_count, property_details["address1"]
        )
        display_unit_configs(unit_configs)
        proceed2 = questionary.confirm("Does everything look correct?").ask()
        if not proceed2:
            console.print("Add the rent comparables again", style="bold blue")

    if property_details["units"] != 0:
        rent_comps, comparables = get_rental_estimations_multifamily(property_details, unit_configs)
        succeeded2 = add_rent_to_supabase(rent_comps, comparables, supabase_client)
    else:
        unit_configs_w_rent, comparables, property_rent = get_rental_estimations_singlefamily(property_details)
        succeeded2 = add_rent_to_supabase_singlefamily(property_details["address1"], unit_configs_w_rent, comparables, property_rent, supabase_client)

    if not succeeded2:
        console.print("Something went wrong when adding rent comps", style="bold red")
        return

    console.print("Property and rent comps added to Supabase", style="bold green")

    return property_details
