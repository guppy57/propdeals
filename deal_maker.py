def build_scenario(properties_df):
    # INPUTS
    # 1. Property Address
    # 2. Loan Type
    # 3. Assumption set
    # 3.1. Do you want to override anything in assumptions? (Y/N) 
    # 3.1.1. If so, we go through a list of all assumptions and ovveride any
    # 4. Price we want to pay
    # 5. Who pays buyers' closing costs (buyer or seller)
    # 6. If seller, what percent (1-3%)
    # 6.1. Do we expect seller credits for repairs (Reduces cash needed, but I suppose it helps with reducing rennovation budget?)
    # 7. Tack on seller's increased closing costs to price (Y/N)
    # 8. Using homestyle renovation loan
    # 8.1. Do we have a specific rennovation budget (ovverides auto-calculated budget for homestyle rennovation)
    # 8.2. Rennovation scope (cosmetic only, HVAC, plumbing, electrical, roof, foundation, major repairs, kitchen/bath updates, full gut rennovation) (this way we can scenario-out different rennovation projects for a property, so store this in JSON in scenarios table)
    # 9. Using Iowa 2nd Home Loan
    # 10. Do we have actual rent data (if so, we it will ask us to input the rent for each unit, then the unit we're living in and all of this data will be stored as a JSON in the scenarios table (e.g. { unit_1: 300, total_rent: 400 })))
    # 11. Does this property generate additional income? (parking fees, coin laundry, storage units, pet fees) (if we say, all of these default to 0)
    # 12. Who pays for utilities (certain multi-family calculations may have owner paying. SFH assumes splitting rent)
    # 13. How will this property be managed (default is self-managed, but if 'property manager' then a 8-10% of rent cost will be applied to OpEx, or 'hybrid' 5% if you find tenants and manager maintains)
    # Any other closing costs?
    # Closing date (can we asked as "Days to Close", homestyle would need 60-75, conventional would need typical 30)
    # Offer date (date we put the offer in on)
    # Rent-Up Period (time between closing date and whne the property gets rented and would affect True Y1 Costs, factor in the first mortgage payment based on closing date)
    # Initial repairs budget (outside of any rennovation work)
    # Plan to appeal property tax assessment?
    # Insurance deductible (auto-generate premium amounts per deductible based on the property in question)

    # AUTO-GENERATED 
    # Scenario Name based on key inputs
    # First mortgage payment (calculated based on Closing Date input)

    pass