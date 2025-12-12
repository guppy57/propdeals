from supabase import Client
from rich.console import Console

class ScriptsProvider:
    def __init__(self, supabase_client: Client, console: Console):
        self.supabase = supabase_client
        self.console = console
    
    def run_add_property_values_script(self, properties_df):
        # go through each property in the dataframe
        # make a call to rentcast api to get the property valuation
        # using this: https://developers.rentcast.io/reference/property-valuation
        # then update the properties table with "est_price, est_price_low, est_price_high"
        #
        # if a property already has these values SKIP the property and dont make a new API call
        # like some of our backfill scripts, we should display live progress and a summary at the end
        # we should also print out at the end: address1, purchase price, est price and then the difference as a dollar amount, difference as a percent sorted by largest percent
        # this ^ would be part of the 'summary' (this should be a display method in @display.py)
        pass