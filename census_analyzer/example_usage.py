"""
Simple example showing how to analyze a property using Census data.
"""

from census_real_estate_analyzer import CensusRealEstateAnalyzer
from dotenv import load_dotenv
import os

load_dotenv()

# STEP 1: Get your Census API key from https://api.census.gov/data/key_signup.html
API_KEY = os.getenv("CENSUS_KEY")

# STEP 2: Initialize the analyzer
analyzer = CensusRealEstateAnalyzer(API_KEY)

# STEP 3: Analyze a property
# Example: A property in Denver, CO
property_address = "224 Ash Ave"
property_city = "Ames"
property_state = "IA"
property_zip = "50014"

print("Analyzing property at:")
print(f"{property_address}, {property_city}, {property_state} {property_zip}\n")

# Get current data (for 2023)
current_data = analyzer.get_census_data(
    address=property_address,
    city=property_city,
    state=property_state,
    zip_code=property_zip
)

# Print formatted summary
analyzer.print_summary(current_data)

# STEP 4: Analyze 20-year trends
print("\n" + "="*70)
print("Getting 20-year historical trends...")
print("="*70 + "\n")

trends_df = analyzer.get_historical_trends(
    address=property_address,
    city=property_city,
    state=property_state,
    zip_code=property_zip
)

# Show key metrics over time
print("\nKey Metrics Over Time:")
print(trends_df[['year', 'median_household_income', 'median_home_value', 
                 'median_rent', 'total_population']].to_string(index=False))

# Calculate and show total growth
first_year = trends_df.iloc[0]
last_year = trends_df.iloc[-1]

print(f"\n\nGrowth from {first_year['year']} to {last_year['year']}:")
print("-" * 50)
print(f"Income: ${first_year['median_household_income']:,} → ${last_year['median_household_income']:,} "
      f"({((last_year['median_household_income']/first_year['median_household_income'])-1)*100:.1f}%)")
print(f"Home Value: ${first_year['median_home_value']:,} → ${last_year['median_home_value']:,} "
      f"({((last_year['median_home_value']/first_year['median_home_value'])-1)*100:.1f}%)")
print(f"Rent: ${first_year['median_rent']:,} → ${last_year['median_rent']:,} "
      f"({((last_year['median_rent']/first_year['median_rent'])-1)*100:.1f}%)")

# Export to CSV for further analysis in Excel
trends_df.to_csv('property_trends.csv', index=False)
print(f"\n✓ Trends exported to: property_trends.csv")
