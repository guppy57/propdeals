"""
Bonus Script: Compare Multiple Properties Side-by-Side

This script shows how to quickly compare several properties to find
the best investment opportunity.
"""

from census_real_estate_analyzer import CensusRealEstateAnalyzer
import pandas as pd

# Initialize analyzer
API_KEY = "YOUR_API_KEY_HERE"
analyzer = CensusRealEstateAnalyzer(API_KEY)

# List of properties to compare
properties = [
    {"address": "1234 Main St", "city": "Denver", "state": "CO", "zip": "80202", "name": "Property A"},
    {"address": "5678 Oak Ave", "city": "Denver", "state": "CO", "zip": "80203", "name": "Property B"},
    {"address": "9101 Pine Rd", "city": "Denver", "state": "CO", "zip": "80204", "name": "Property C"},
]

print("="*80)
print("PROPERTY COMPARISON - Multi-Family / House Hacking Analysis")
print("="*80 + "\n")

comparison_data = []

for prop in properties:
    print(f"Analyzing {prop['name']}...")
    
    try:
        data = analyzer.get_census_data(
            address=prop['address'],
            city=prop['city'],
            state=prop['state'],
            zip_code=prop['zip']
        )
        
        # Extract key metrics
        comparison_data.append({
            'Property': prop['name'],
            'Location': f"{prop['city']}, {prop['state']} {prop['zip']}",
            'Median Income': data['income']['median_household_income'],
            'Rental Rate %': data['housing']['rental_rate_pct'],
            'Median Rent': data['housing']['median_rent'],
            'Median Value': data['housing']['median_home_value'],
            'Rent Yield %': (data['housing']['median_rent'] * 12 / data['housing']['median_home_value'] * 100) 
                           if data['housing']['median_home_value'] > 0 else 0,
            'Age 25-34 %': data['demographics']['age_distribution_pct']['25-34'],
            'Poverty Rate %': data['demographics']['poverty_rate_pct'],
            'Population': data['demographics']['total_population'],
        })
        
    except Exception as e:
        print(f"  Error: {e}")
        continue

# Create comparison DataFrame
df = pd.DataFrame(comparison_data)

print("\n" + "="*80)
print("SIDE-BY-SIDE COMPARISON")
print("="*80 + "\n")

# Format currency columns
df['Median Income'] = df['Median Income'].apply(lambda x: f"${x:,.0f}")
df['Median Rent'] = df['Median Rent'].apply(lambda x: f"${x:,.0f}")
df['Median Value'] = df['Median Value'].apply(lambda x: f"${x:,.0f}")

# Format percentage columns
df['Rental Rate %'] = df['Rental Rate %'].apply(lambda x: f"{x:.1f}%")
df['Rent Yield %'] = df['Rent Yield %'].apply(lambda x: f"{x:.2f}%")
df['Age 25-34 %'] = df['Age 25-34 %'].apply(lambda x: f"{x:.1f}%")
df['Poverty Rate %'] = df['Poverty Rate %'].apply(lambda x: f"{x:.1f}%")

# Format population
df['Population'] = df['Population'].apply(lambda x: f"{x:,}")

print(df.to_string(index=False))

print("\n" + "="*80)
print("INVESTMENT SCORING")
print("="*80 + "\n")

# Create a scoring system (you can customize the weights)
scoring_df = pd.DataFrame(comparison_data)

# Higher is better (normalize to 0-10 scale)
scoring_df['Income Score'] = (scoring_df['Median Income'] / scoring_df['Median Income'].max() * 10)
scoring_df['Yield Score'] = (scoring_df['Rent Yield %'] / scoring_df['Rent Yield %'].max() * 10)
scoring_df['Rental Market Score'] = (scoring_df['Rental Rate %'] / 100 * 10)
scoring_df['Demographics Score'] = (scoring_df['Age 25-34 %'] / scoring_df['Age 25-34 %'].max() * 10)

# Lower is better (invert)
scoring_df['Poverty Score'] = ((1 - scoring_df['Poverty Rate %'] / scoring_df['Poverty Rate %'].max()) * 10)

# Calculate total score
scoring_df['Total Score'] = (
    scoring_df['Income Score'] * 0.20 +
    scoring_df['Yield Score'] * 0.30 +
    scoring_df['Rental Market Score'] * 0.20 +
    scoring_df['Demographics Score'] * 0.20 +
    scoring_df['Poverty Score'] * 0.10
)

# Display scores
scores = scoring_df[['Property', 'Income Score', 'Yield Score', 'Rental Market Score', 
                     'Demographics Score', 'Poverty Score', 'Total Score']].copy()
scores = scores.round(2)
scores = scores.sort_values('Total Score', ascending=False)

print("Score breakdown (0-10 scale, higher is better):")
print("-" * 80)
print(scores.to_string(index=False))

print("\n" + "="*80)
print("RECOMMENDATION")
print("="*80)

best_property = scores.iloc[0]
print(f"\n🏆 Best Overall: {best_property['Property']} (Score: {best_property['Total Score']:.2f}/10)")
print("\nWhy:")
print(f"  • Strong cash flow potential (Yield Score: {best_property['Yield Score']:.1f}/10)")
print(f"  • Good rental market (Rental Market Score: {best_property['Rental Market Score']:.1f}/10)")
print(f"  • Ideal tenant demographics (Demographics Score: {best_property['Demographics Score']:.1f}/10)")

# Export results
df.to_csv('/mnt/user-data/outputs/property_comparison.csv', index=False)
scoring_df.to_csv('/mnt/user-data/outputs/property_scores.csv', index=False)
print(f"\n✓ Results exported to property_comparison.csv and property_scores.csv")

print("\n" + "="*80)
print("NOTES")
print("="*80)
print("""
Scoring Weights:
  • Rent Yield: 30% (most important for cash flow)
  • Income: 20% (ability to afford rent)
  • Rental Market: 20% (established rental demand)
  • Demographics: 20% (quality tenant pool)
  • Poverty Rate: 10% (risk factor)

Customize the weights in the script based on your investment strategy:
  - Focus on cash flow? Increase Yield Score weight
  - Focus on stability? Increase Income Score weight
  - House hacking? Increase Demographics Score weight

Always visit properties in person and verify local conditions!
""")
