# Census Real Estate Analyzer

A Python tool for analyzing demographic and economic data for real estate investment decisions using US Census Bureau data.

## Features

- **Property-Level Analysis**: Get census data for the smallest reliable geography (census tract) based on any address
- **Comprehensive Metrics**: Median income, rental rates, home values, age distribution, poverty rates, and more
- **20-Year Trend Analysis**: Track how neighborhoods have changed over time
- **Investment Insights**: Automatic calculation of rent yields, growth rates, and investment indicators

## Installation

### 1. Install Python packages:
```bash
pip install -r requirements.txt --break-system-packages
```

### 2. Get a Census API Key:
1. Visit: https://api.census.gov/data/key_signup.html
2. Fill out the form (takes 2 minutes)
3. You'll receive a 40-character API key via email instantly
4. It's free and has no usage limits!

## Quick Start

### Example 1: Analyze a Single Property

```python
from census_real_estate_analyzer import CensusRealEstateAnalyzer

# Initialize with your API key
analyzer = CensusRealEstateAnalyzer("YOUR_API_KEY_HERE")

# Analyze a property
data = analyzer.get_census_data(
    address="1234 Main St",
    city="Denver",
    state="CO",
    zip_code="80202"
)

# Print formatted summary
analyzer.print_summary(data)
```

**Output includes:**
- Median household income
- Rental rate %
- Homeownership rate %
- Median rent
- Median home value
- Population by age group
- Poverty rate
- Gross rent yield (investment metric)

### Example 2: Analyze 20-Year Trends

```python
# Get historical trends (2009-2023)
trends = analyzer.get_historical_trends(
    address="1234 Main St",
    city="Denver",
    state="CO",
    zip_code="80202"
)

# The DataFrame includes:
# - Income growth over time
# - Home value appreciation
# - Rent growth
# - Population changes
# - Rental rate changes
# - Year-over-year growth percentages

# Export to CSV
trends.to_csv('property_trends.csv', index=False)
```

## What Data You Get

### Current Data (`get_census_data`)

**Income:**
- Median household income

**Housing:**
- Rental rate (% of housing units that are rentals)
- Homeownership rate (% of housing units that are owner-occupied)
- Median gross rent ($/month)
- Median home value ($)
- Total housing units
- Renter vs owner-occupied counts

**Demographics:**
- Total population
- Age distribution (18-24, 25-34, 35-44, 45-64, 65+)
- Poverty rate

**Calculated Investment Metrics:**
- Gross rent yield (annual rent / home value)
- Price-to-rent ratio

### Historical Trends (`get_historical_trends`)

Returns a pandas DataFrame with year-by-year data:
- All metrics from current data
- Year-over-year growth rates for:
  - Income
  - Home values
  - Rents
  - Population
- Rental rate changes (percentage point changes)

## Real-World Use Cases

### House Hacking Decision
```python
# Compare multiple properties
properties = [
    ("123 Main St", "Denver", "CO", "80202"),
    ("456 Oak Ave", "Denver", "CO", "80203"),
    ("789 Pine Rd", "Denver", "CO", "80204"),
]

for address, city, state, zip_code in properties:
    data = analyzer.get_census_data(address, city, state, zip_code)
    print(f"\n{address}: Rental Rate = {data['housing']['rental_rate_pct']:.1f}%, "
          f"Median Income = ${data['income']['median_household_income']:,}, "
          f"Age 25-34 = {data['demographics']['age_distribution_pct']['25-34']:.1f}%")
```

### Market Research
```python
# Analyze if a neighborhood is improving or declining
trends = analyzer.get_historical_trends("1234 Main St", "Denver", "CO", "80202")

# Look for:
# - Rising incomes (gentrification)
# - Increasing rents (demand)
# - Growing population (hot market)
# - Stable or increasing home values (appreciation)

recent_5y = trends.tail(5)
print(f"5-Year Income Growth: {recent_5y['income_growth_pct'].sum():.1f}%")
print(f"5-Year Rent Growth: {recent_5y['rent_growth_pct'].sum():.1f}%")
```

### Investment Comparison
```python
# Compare rent growth to home value growth
trends = analyzer.get_historical_trends("1234 Main St", "Denver", "CO", "80202")

avg_rent_growth = trends['rent_growth_pct'].mean()
avg_value_growth = trends['home_value_growth_pct'].mean()

if avg_rent_growth > avg_value_growth:
    print("✓ Cash flow play - rents growing faster than values")
else:
    print("✓ Appreciation play - values growing faster than rents")
```

## Understanding the Data

### Geographic Level
The tool uses **census tracts**, which typically contain 1,200-8,000 people. This is:
- Smaller than ZIP codes (more precise)
- Larger than block groups (more reliable data)
- The best balance of precision and data quality for ACS 5-year estimates

### Data Source
- **ACS 5-Year Estimates**: Most reliable data for small geographies
- **Years Available**: 2009-2023
- **Update Frequency**: Annual (new data released each fall)

### Limitations
- Census tracts don't always align perfectly with "neighborhoods"
- Data is estimates with margins of error (especially for small areas)
- Some areas may have suppressed data due to small sample sizes
- Address geocoding may fail for very new developments

## Tips for Real Estate Investors

### Red Flags:
- Declining population
- Increasing poverty rate
- Stagnant or declining income
- Rental rates decreasing (more people buying, less rental demand)

### Green Flags:
- Rising median income (gentrification/improvement)
- Growing population
- High percentage of 25-34 year olds (prime renters for house hacking)
- Rental rate increasing (more rental demand)
- Rent growth > inflation (strong rental market)
- Gross rent yield > 8% (good cash flow potential)

### For House Hacking:
Look for census tracts with:
- 40%+ rental rate (established rental market)
- High percentage of age 25-34 (potential roommates)
- Median income $60k-$100k (can afford rent, not buying yet)
- Proximity to employment centers (commuters need housing)

## Files

- `census_real_estate_analyzer.py` - Main analyzer class
- `example_usage.py` - Simple example script
- `requirements.txt` - Python dependencies
- `README.md` - This file

## Support

For issues with the Census API:
- API Documentation: https://www.census.gov/data/developers/guidance.html
- Variable Search: https://api.census.gov/data.html
- Email: [email protected]

## License

MIT License - free to use for personal or commercial projects

## Disclaimer

This tool provides demographic and economic data for informational purposes only. It does not constitute financial, investment, or real estate advice. Always conduct your own due diligence and consult with qualified professionals before making investment decisions.

Census data has margins of error and may not reflect current conditions. Always verify data with local sources and recent market research.
