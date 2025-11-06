from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from dotenv import load_dotenv
import os
import questionary
import requests

load_dotenv()

EXCEL_FILE_PATH = "./Real Estate Investing.xlsx"
PROPERTIES_CSV_PATH = "./properties.csv"

RENTCAST_HEADERS = {
    "accept": "application/json",
    "X-Api-Key": os.getenv("RENTCAST_KEY"),
}

console = Console()


def get_rental_estimations(property_details, unit_configs):
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
                "Something went wrong when trying to pulling rental estimate",
                style="bold red",
            )

        unit["rent_estimate"] = int(float(data["rent"]))
        unit["rent_estimate_low"] = int(float(data["rentRangeLow"]))
        unit["rent_estimate_high"] = int(float(data["rentRangeHigh"]))
        unit["estimated_sqrft"] = int(float(sqrft))
        comparables.append(data["comparables"])

    return unit_configs, comparables


def get_geocode(address):
    print(f"Getting geocode for: {address}")
    response = requests.get(
        "https://maps.googleapis.com/maps/api/geocode/json",
        params={
            "key": os.getenv("GOOGLE_KEY"),
            "address": address,
        },
    )

    data = response.json()
    location = data["results"][0]["geometry"]["location"]
    return location["lng"], location["lat"]


def get_solar_potential_data(address):
    lng, lat = get_geocode(address)
    print(f"Getting solar potential data for: {address}")
    response = requests.get(
        "https://solar.googleapis.com/v1/buildingInsights:findClosest",
        params={
            "location.latitude": lat,
            "location.longitude": lng,
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
        choices=["Duplex", "Triplex", "Fourplex"],
    ).ask()
    beds = questionary.text("Bedrooms").ask()
    baths = questionary.text("Bathrooms").ask()
    square_ft = questionary.text("Square footage").ask()
    built_in = questionary.text("Year built").ask()
    address1 = full_address.split(",")[0]

    unit_conversion = {"Duplex": 2, "Triplex": 3, "Fourplex": 4}

    units = unit_conversion[property_type]

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
        lon, lat = get_geocode(property_details["full_address"])
        console.print(f"Found long: {lon} and lat: {lat}", style="green bold")
        walk, transit, bike = get_walkscore_data(
            lon, lat, property_details["full_address"]
        )
        console.print(
            f"Found walk score: {walk}, transit: {transit}, bike: {bike}",
            style="green bold",
        )
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
    property_details["lat"] = lat
    property_details["lon"] = lon
    property_details["annual_electricity_cost_est"] = electricity_costs

    try:
        query = supabase.table("properties").insert(property_details)
        response = query.execute()

        # Check if response has data
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


def add_rent_to_supabase(rent_comps, comparables, supabase) -> int:
    current_rents = supabase.table("rent_estimates").select("id").execute()
    current_count = len(current_rents.data)
    new_ids = []

    # Insert all rent estimates first
    for i, rent_comp in enumerate(rent_comps):
        new_id = current_count + 1 + i
        rent_comp["id"] = new_id
        new_ids.append(new_id)

        try:
            query = supabase.table("rent_estimates").insert(rent_comp)
            response = query.execute()
            if hasattr(response, "data"):
                print(f"Response data: {response.data}")
            else:
                print("Response has no 'data' attribute")
                return False
        except Exception as e:
            print(f"Exception: {e}")
            print(f"Exception type: {type(e)}")
            return False

    # Save comparables for each unit (if we have them structured per unit)
    for i, unit_comparables in enumerate(comparables):
        if unit_comparables:  # Only save if there are comparables
            rent_estimate_id = new_ids[i]
            save_comps_to_db(unit_comparables, rent_estimate_id, supabase)

    return True


# --------------------------------------------------------


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

    while not proceed2:
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

    rent_comps, comparables = get_rental_estimations(property_details, unit_configs)
    succeeded2 = add_rent_to_supabase(rent_comps, comparables, supabase_client)

    if not succeeded2:
        console.print("Something went wrong when adding rent comps", style="bold red")
        return

    console.print("Property and rent comps added to Supabase", style="bold green")

    return property_details
