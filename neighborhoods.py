import pandas as pd


class NeighborhoodsClient():
  def __init__(self):
    pass

  # use elementary, middle school, high school ratings to create an average for the property

  def is_neighborhood_assessment_complete(self, address1: str) -> bool:
    return False

  def get_neighborhoods_dataframe(self, supabase):
    """
    Fetch neighborhoods for all properties from the property_neighborhood many-to-many table.

    Args:
        supabase: Supabase client instance

    Returns:
        pandas DataFrame with columns: address1, neighborhood
        Properties without neighborhoods will not be in the dataframe (handled by left merge)
    """
    try:
      # Query property_neighborhood with a join to neighborhoods table
      # Supabase syntax: table.select('col1, col2, foreign_table(foreign_col)')
      response = supabase.table('property_neighborhood')\
        .select('address1, neighborhoods(name)')\
        .execute()

      if not response.data:
        # No neighborhoods found, return empty dataframe with correct columns
        return pd.DataFrame(columns=['address1', 'neighborhood'])

      # Convert to dataframe
      neighborhoods_df = pd.DataFrame(response.data)

      # Handle the nested structure from Supabase join
      # The 'neighborhoods' column contains a dict like {'name': 'downtown'}
      if 'neighborhoods' in neighborhoods_df.columns:
        neighborhoods_df['neighborhood'] = neighborhoods_df['neighborhoods'].apply(
          lambda x: x['name'] if x and isinstance(x, dict) and 'name' in x else None
        )
        # Keep only the columns we need
        neighborhoods_df = neighborhoods_df[['address1', 'neighborhood']]
      else:
        # Fallback if structure is different
        return pd.DataFrame(columns=['address1', 'neighborhood'])

      # Remove any rows where neighborhood is None
      neighborhoods_df = neighborhoods_df.dropna(subset=['neighborhood'])

      return neighborhoods_df

    except Exception as e:
      print(f"Error fetching neighborhoods: {e}")
      # Return empty dataframe on error
      return pd.DataFrame(columns=['address1', 'neighborhood']) 