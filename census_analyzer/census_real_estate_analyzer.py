"""
Census Real Estate Analyzer
A tool for analyzing demographic and economic data for real estate investment decisions.

Requires:
    pip install census us censusgeocode --break-system-packages

Get your Census API key from: https://api.census.gov/data/key_signup.html
"""

from census import Census
from us import states
import censusgeocode as cg
from typing import Dict, List, Tuple
import pandas as pd


class CensusRealEstateAnalyzer:
    """Analyze census data for real estate investment decisions."""
    
    def __init__(self, api_key: str):
        """
        Initialize the analyzer with Census API key.
        
        Args:
            api_key: Your Census API key from api.census.gov
        """
        self.census = Census(api_key)
        
    def _get_census_tract(self, address: str, city: str, state: str, zip_code: str) -> Tuple[str, str, str]:
        """
        Convert address to census tract, county, and state FIPS codes.
        
        Args:
            address: Street address (e.g., "123 Main St")
            city: City name
            state: State abbreviation (e.g., "CA")
            zip_code: ZIP code
            
        Returns:
            Tuple of (state_fips, county_fips, tract_code)
        """
        # Construct full address
        full_address = f"{address}, {city}, {state} {zip_code}"
        
        # Geocode the address
        result = cg.onelineaddress(full_address)
        
        if not result or len(result) == 0:
            raise ValueError(f"Could not geocode address: {full_address}")
        
        # Extract census geography
        census_tract_info = result[0]['Census Tracts'][0]
        state_fips = census_tract_info['STATE']
        county_fips = census_tract_info['COUNTY']
        tract_code = census_tract_info['TRACT']
        
        return state_fips, county_fips, tract_code
    
    def get_census_data(self, address: str, city: str, state: str, zip_code: str, 
                       year: int = 2023) -> Dict:
        """
        Get comprehensive census data for a property address.
        Returns data for the census tract (smallest reliable geography).
        
        Args:
            address: Street address (e.g., "123 Main St")
            city: City name
            state: State abbreviation (e.g., "CA")
            zip_code: ZIP code
            year: Year for ACS data (default: 2023, most recent)
            
        Returns:
            Dictionary containing all requested census metrics
        """
        # Get census tract
        state_fips, county_fips, tract_code = self._get_census_tract(
            address, city, state, zip_code
        )
        
        # Define variables to retrieve
        # Using ACS 5-year estimates for most reliable data at tract level
        variables = (
            'NAME',                  # Geographic name
            'B19013_001E',          # Median household income
            'B25003_001E',          # Total housing units (for calculation)
            'B25003_002E',          # Owner-occupied housing units
            'B25003_003E',          # Renter-occupied housing units
            'B01001_001E',          # Total population
            'B01001_003E',          # Male under 5 years
            'B01001_004E',          # Male 5 to 9 years
            'B01001_005E',          # Male 10 to 14 years
            'B01001_006E',          # Male 15 to 17 years
            'B01001_007E',          # Male 18 and 19 years
            'B01001_008E',          # Male 20 years
            'B01001_009E',          # Male 21 years
            'B01001_010E',          # Male 22 to 24 years
            'B01001_011E',          # Male 25 to 29 years
            'B01001_012E',          # Male 30 to 34 years
            'B01001_013E',          # Male 35 to 39 years
            'B01001_014E',          # Male 40 to 44 years
            'B01001_015E',          # Male 45 to 49 years
            'B01001_016E',          # Male 50 to 54 years
            'B01001_017E',          # Male 55 to 59 years
            'B01001_018E',          # Male 60 and 61 years
            'B01001_019E',          # Male 62 to 64 years
            'B01001_020E',          # Male 65 and 66 years
            'B01001_021E',          # Male 67 to 69 years
            'B01001_022E',          # Male 70 to 74 years
            'B01001_023E',          # Male 75 to 79 years
            'B01001_024E',          # Male 80 to 84 years
            'B01001_025E',          # Male 85 years and over
            'B01001_027E',          # Female under 5 years
            'B01001_028E',          # Female 5 to 9 years
            'B01001_029E',          # Female 10 to 14 years
            'B01001_030E',          # Female 15 to 17 years
            'B01001_031E',          # Female 18 and 19 years
            'B01001_032E',          # Female 20 years
            'B01001_033E',          # Female 21 years
            'B01001_034E',          # Female 22 to 24 years
            'B01001_035E',          # Female 25 to 29 years
            'B01001_036E',          # Female 30 to 34 years
            'B01001_037E',          # Female 35 to 39 years
            'B01001_038E',          # Female 40 to 44 years
            'B01001_039E',          # Female 45 to 49 years
            'B01001_040E',          # Female 50 to 54 years
            'B01001_041E',          # Female 55 to 59 years
            'B01001_042E',          # Female 60 and 61 years
            'B01001_043E',          # Female 62 to 64 years
            'B01001_044E',          # Female 65 and 66 years
            'B01001_045E',          # Female 67 to 69 years
            'B01001_046E',          # Female 70 to 74 years
            'B01001_047E',          # Female 75 to 79 years
            'B01001_048E',          # Female 80 to 84 years
            'B01001_049E',          # Female 85 years and over
            'B25064_001E',          # Median gross rent
            'B25077_001E',          # Median home value
            'C17002_001E',          # Total for poverty calculation
            'C17002_002E',          # Income < 0.50 of poverty level
            'C17002_003E',          # Income 0.50 to 0.99 of poverty level
        )
        
        # Fetch data
        raw_data = self.census.acs5.state_county_tract(
            variables,
            state_fips,
            county_fips,
            tract_code,
            year=year
        )
        
        if not raw_data or len(raw_data) == 0:
            raise ValueError("No data returned from Census API")
        
        data = raw_data[0]
        
        # Calculate derived metrics
        total_housing = int(data['B25003_001E'] or 0)
        owner_occupied = int(data['B25003_002E'] or 0)
        renter_occupied = int(data['B25003_003E'] or 0)
        
        # Calculate percentages
        homeownership_rate = (owner_occupied / total_housing * 100) if total_housing > 0 else 0
        rental_rate = (renter_occupied / total_housing * 100) if total_housing > 0 else 0
        
        # Calculate poverty rate
        total_for_poverty = int(data['C17002_001E'] or 0)
        below_poverty = int(data['C17002_002E'] or 0) + int(data['C17002_003E'] or 0)
        poverty_rate = (below_poverty / total_for_poverty * 100) if total_for_poverty > 0 else 0
        
        # Age distribution calculation
        total_pop = int(data['B01001_001E'] or 0)
        
        # Age groups of interest for house hacking / rentals
        age_18_24_male = sum([
            int(data['B01001_007E'] or 0),
            int(data['B01001_008E'] or 0),
            int(data['B01001_009E'] or 0),
            int(data['B01001_010E'] or 0),
        ])
        age_18_24_female = sum([
            int(data['B01001_031E'] or 0),
            int(data['B01001_032E'] or 0),
            int(data['B01001_033E'] or 0),
            int(data['B01001_034E'] or 0),
        ])
        age_25_34_male = sum([
            int(data['B01001_011E'] or 0),
            int(data['B01001_012E'] or 0),
        ])
        age_25_34_female = sum([
            int(data['B01001_035E'] or 0),
            int(data['B01001_036E'] or 0),
        ])
        age_35_44_male = sum([
            int(data['B01001_013E'] or 0),
            int(data['B01001_014E'] or 0),
        ])
        age_35_44_female = sum([
            int(data['B01001_037E'] or 0),
            int(data['B01001_038E'] or 0),
        ])
        age_45_64_male = sum([
            int(data['B01001_015E'] or 0),
            int(data['B01001_016E'] or 0),
            int(data['B01001_017E'] or 0),
            int(data['B01001_018E'] or 0),
            int(data['B01001_019E'] or 0),
        ])
        age_45_64_female = sum([
            int(data['B01001_039E'] or 0),
            int(data['B01001_040E'] or 0),
            int(data['B01001_041E'] or 0),
            int(data['B01001_042E'] or 0),
            int(data['B01001_043E'] or 0),
        ])
        age_65_plus_male = sum([
            int(data['B01001_020E'] or 0),
            int(data['B01001_021E'] or 0),
            int(data['B01001_022E'] or 0),
            int(data['B01001_023E'] or 0),
            int(data['B01001_024E'] or 0),
            int(data['B01001_025E'] or 0),
        ])
        age_65_plus_female = sum([
            int(data['B01001_044E'] or 0),
            int(data['B01001_045E'] or 0),
            int(data['B01001_046E'] or 0),
            int(data['B01001_047E'] or 0),
            int(data['B01001_048E'] or 0),
            int(data['B01001_049E'] or 0),
        ])
        
        age_distribution = {
            '18-24': age_18_24_male + age_18_24_female,
            '25-34': age_25_34_male + age_25_34_female,
            '35-44': age_35_44_male + age_35_44_female,
            '45-64': age_45_64_male + age_45_64_female,
            '65+': age_65_plus_male + age_65_plus_female,
        }
        
        # Convert to percentages
        age_distribution_pct = {
            age: (count / total_pop * 100) if total_pop > 0 else 0 
            for age, count in age_distribution.items()
        }
        
        # Compile results
        results = {
            'location': {
                'name': data['NAME'],
                'address': f"{address}, {city}, {state} {zip_code}",
                'census_tract': tract_code,
                'state_fips': state_fips,
                'county_fips': county_fips,
                'year': year,
            },
            'income': {
                'median_household_income': int(data['B19013_001E'] or 0),
            },
            'housing': {
                'rental_rate_pct': round(rental_rate, 2),
                'homeownership_rate_pct': round(homeownership_rate, 2),
                'total_housing_units': total_housing,
                'renter_occupied_units': renter_occupied,
                'owner_occupied_units': owner_occupied,
                'median_rent': int(data['B25064_001E'] or 0),
                'median_home_value': int(data['B25077_001E'] or 0),
            },
            'demographics': {
                'total_population': total_pop,
                'poverty_rate_pct': round(poverty_rate, 2),
                'age_distribution': age_distribution,
                'age_distribution_pct': age_distribution_pct,
            }
        }
        
        return results
    
    def get_historical_trends(self, address: str, city: str, state: str, 
                             zip_code: str, years: List[int] = None) -> pd.DataFrame:
        """
        Get historical trends for key metrics over multiple years.
        
        Args:
            address: Street address
            city: City name
            state: State abbreviation
            zip_code: ZIP code
            years: List of years to analyze (default: last 20 years of ACS5 data)
            
        Returns:
            DataFrame with historical trends
        """
        if years is None:
            # ACS5 available from 2009-2023
            years = list(range(2009, 2024))
        
        trends_data = []
        
        for year in years:
            try:
                data = self.get_census_data(address, city, state, zip_code, year)
                
                trends_data.append({
                    'year': year,
                    'median_household_income': data['income']['median_household_income'],
                    'rental_rate_pct': data['housing']['rental_rate_pct'],
                    'median_home_value': data['housing']['median_home_value'],
                    'median_rent': data['housing']['median_rent'],
                    'total_population': data['demographics']['total_population'],
                    'poverty_rate_pct': data['demographics']['poverty_rate_pct'],
                })
            except Exception as e:
                print(f"Warning: Could not retrieve data for {year}: {e}")
                continue
        
        df = pd.DataFrame(trends_data)
        
        # Calculate growth rates
        if len(df) > 1:
            df['income_growth_pct'] = df['median_household_income'].pct_change() * 100
            df['home_value_growth_pct'] = df['median_home_value'].pct_change() * 100
            df['rent_growth_pct'] = df['median_rent'].pct_change() * 100
            df['population_growth_pct'] = df['total_population'].pct_change() * 100
            df['rental_rate_change_pct_points'] = df['rental_rate_pct'].diff()
        
        return df
    
    def print_summary(self, data: Dict):
        """Print a formatted summary of census data."""
        print(f"\n{'='*70}")
        print(f"CENSUS DATA SUMMARY")
        print(f"{'='*70}")
        print(f"\nLocation: {data['location']['address']}")
        print(f"Census Tract: {data['location']['census_tract']}")
        print(f"Data Year: {data['location']['year']}")
        
        print(f"\n{'-'*70}")
        print("INCOME METRICS")
        print(f"{'-'*70}")
        print(f"Median Household Income: ${data['income']['median_household_income']:,}")
        
        print(f"\n{'-'*70}")
        print("HOUSING METRICS")
        print(f"{'-'*70}")
        print(f"Rental Rate: {data['housing']['rental_rate_pct']:.2f}%")
        print(f"Homeownership Rate: {data['housing']['homeownership_rate_pct']:.2f}%")
        print(f"Median Rent: ${data['housing']['median_rent']:,}/month")
        print(f"Median Home Value: ${data['housing']['median_home_value']:,}")
        print(f"Total Housing Units: {data['housing']['total_housing_units']:,}")
        
        print(f"\n{'-'*70}")
        print("DEMOGRAPHIC METRICS")
        print(f"{'-'*70}")
        print(f"Total Population: {data['demographics']['total_population']:,}")
        print(f"Poverty Rate: {data['demographics']['poverty_rate_pct']:.2f}%")
        print(f"\nAge Distribution:")
        for age_group, pct in data['demographics']['age_distribution_pct'].items():
            count = data['demographics']['age_distribution'][age_group]
            print(f"  {age_group}: {pct:.1f}% ({count:,} people)")
        
        # Calculate rent-to-value ratio (useful for investors)
        if data['housing']['median_home_value'] > 0:
            annual_rent = data['housing']['median_rent'] * 12
            rent_to_value = (annual_rent / data['housing']['median_home_value']) * 100
            print(f"\n{'-'*70}")
            print("INVESTMENT METRICS")
            print(f"{'-'*70}")
            print(f"Gross Rent Yield: {rent_to_value:.2f}%")
            print(f"Price-to-Rent Ratio: {data['housing']['median_home_value'] / annual_rent:.1f}x")
        
        print(f"\n{'='*70}\n")


def example_usage():
    """Example usage of the CensusRealEstateAnalyzer."""
    
    # Initialize with your API key
    API_KEY = "YOUR_CENSUS_API_KEY_HERE"  # Get from https://api.census.gov/data/key_signup.html
    analyzer = CensusRealEstateAnalyzer(API_KEY)
    
    # Example property address
    address = "1600 Pennsylvania Avenue NW"
    city = "Washington"
    state = "DC"
    zip_code = "20500"
    
    print("\n" + "="*70)
    print("EXAMPLE 1: Get Current Census Data for a Property")
    print("="*70)
    
    # Get current census data
    current_data = analyzer.get_census_data(address, city, state, zip_code)
    analyzer.print_summary(current_data)
    
    print("\n" + "="*70)
    print("EXAMPLE 2: Analyze 20-Year Historical Trends")
    print("="*70 + "\n")
    
    # Get historical trends
    trends = analyzer.get_historical_trends(address, city, state, zip_code)
    
    print("\nHistorical Trends (2009-2023):")
    print("-" * 70)
    
    # Display key trends
    pd.set_option('display.max_columns', None)
    pd.set_option('display.width', None)
    pd.set_option('display.max_colwidth', None)
    
    print("\nYear-by-Year Data:")
    print(trends[['year', 'median_household_income', 'median_home_value', 
                  'median_rent', 'rental_rate_pct', 'total_population']].to_string(index=False))
    
    print("\n\nGrowth Rates (Year-over-Year):")
    print(trends[['year', 'income_growth_pct', 'home_value_growth_pct', 
                  'rent_growth_pct', 'population_growth_pct']].to_string(index=False))
    
    # Calculate total growth over the period
    if len(trends) > 1:
        first_year = trends.iloc[0]
        last_year = trends.iloc[-1]
        years_elapsed = last_year['year'] - first_year['year']
        
        print(f"\n\n{'-'*70}")
        print(f"TOTAL GROWTH ({first_year['year']} to {last_year['year']})")
        print(f"{'-'*70}")
        
        income_total_growth = ((last_year['median_household_income'] / first_year['median_household_income']) - 1) * 100
        value_total_growth = ((last_year['median_home_value'] / first_year['median_home_value']) - 1) * 100
        rent_total_growth = ((last_year['median_rent'] / first_year['median_rent']) - 1) * 100
        pop_total_growth = ((last_year['total_population'] / first_year['total_population']) - 1) * 100
        
        print(f"Median Income Growth: {income_total_growth:.1f}% (CAGR: {(income_total_growth/years_elapsed):.1f}%/year)")
        print(f"Median Home Value Growth: {value_total_growth:.1f}% (CAGR: {(value_total_growth/years_elapsed):.1f}%/year)")
        print(f"Median Rent Growth: {rent_total_growth:.1f}% (CAGR: {(rent_total_growth/years_elapsed):.1f}%/year)")
        print(f"Population Growth: {pop_total_growth:.1f}% (CAGR: {(pop_total_growth/years_elapsed):.1f}%/year)")
        print(f"Rental Rate Change: {last_year['rental_rate_pct'] - first_year['rental_rate_pct']:.1f} percentage points")
        
        # Investment insight
        print(f"\n{'-'*70}")
        print("INVESTMENT INSIGHTS")
        print(f"{'-'*70}")
        
        if rent_total_growth > value_total_growth:
            print("✓ Rents grew faster than home values - favorable for cash flow!")
        else:
            print("⚠ Home values grew faster than rents - appreciation play, not cash flow")
        
        if pop_total_growth > 0:
            print(f"✓ Population grew by {pop_total_growth:.1f}% - increasing demand")
        else:
            print(f"⚠ Population declined by {abs(pop_total_growth):.1f}% - decreasing demand")
        
        if last_year['rental_rate_pct'] > first_year['rental_rate_pct']:
            print(f"✓ Rental rate increased - more renters in the market")
        else:
            print(f"⚠ Rental rate decreased - more people buying homes")
    
    print(f"\n{'='*70}\n")
    
    # Export to CSV
    trends.to_csv('/mnt/user-data/outputs/census_trends.csv', index=False)
    print(f"Trend data exported to: census_trends.csv")


if __name__ == "__main__":
    example_usage()
