# filename: enrich_properties_csv.py
import csv
from pathlib import Path
from add_property import get_geocode, get_walkscore_data, get_solar_potential_data

INPUT_PATH = Path("properties.csv")
OUTPUT_PATH = Path("properties.tmp.csv")  # temp file for atomic replace


def enrich_row(row: dict) -> dict:
    """Compute and add enrichment fields to a single property row."""
    # Defensive: ensure required keys exist
    full_address = row.get("full_address", "")
    lon, lat = get_geocode(full_address)
    walk, transit, bike = get_walkscore_data(row)
    solar_data = get_solar_potential_data(full_address)
    electricity_costs = solar_data.get("cost_electricity_without_solar", "")

    # Add/overwrite fields
    row["walk_score"] = walk
    row["transit_score"] = transit
    row["bike_score"] = bike
    row["lat"] = lat
    row["lon"] = lon
    row["annual_electricity_cost_est"] = electricity_costs
    return row


def main():
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f"Input CSV not found: {INPUT_PATH}")

    # Read all rows
    with INPUT_PATH.open("r", newline="", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        original_fieldnames = reader.fieldnames or []

        rows = []
        for row in reader:
            # Use single quotes inside f-string to avoid syntax error
            print(f"Working on {row.get('address1', '')}")
            rows.append(enrich_row(row))
            print("Finished with this one")

    # Compute final fieldnames: original + new enrichment columns
    enrichment_fields = [
        "walk_score",
        "transit_score",
        "bike_score",
        "lat",
        "lon",
        "annual_electricity_cost_est",
    ]
    # Preserve order: originals first, then add missing enrichment fields
    fieldnames = list(original_fieldnames) if original_fieldnames else []
    for f in enrichment_fields:
        if f not in fieldnames:
            fieldnames.append(f)

    # Write to temp file
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    # Atomic replace: move temp over original
    # OUTPUT_PATH.replace(INPUT_PATH)


if __name__ == "__main__":
    main()
