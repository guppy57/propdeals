from add_property import get_test_data, get_geocode, get_walkscore_data, get_solar_potential_data, get_value_estimate

data = get_test_data()

# print(data["full_address"])

# lng, lat = get_geocode(data["full_address"])

# print(f"LONGITUDE: {lng}")
# print(f"LATITUDE: {lat}")

# walk, transit, bike = get_walkscore_data(data)
# print(f"WALK_SCORE: {walk}")
# print(f"TRANSIT_SCORE: {transit}")
# print(f"BIKE_SCORE: {bike}")

# solar = get_solar_potential_data(data["full_address"])
# print(solar)

value = get_value_estimate(data)