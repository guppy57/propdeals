from typing import Optional, Dict
from supabase import Client
from models.inspections import InspectionCreate, UnitInspectionCreate
class InspectionsClient():
    def __init__(self, supabase_client: Client):
        self.supabase = supabase_client

    def compile_results(self):
        # deal_breaker_count INTEGER DEFAULT 0,
        # red_flag_count INTEGER DEFAULT 0,
        # total_repair_cost_est BIGINT,
        # overall_condition TEXT, -- 'excellent', 'good', 'fair', 'poor'
        # recommendation TEXT, -- 'strong_yes', 'conditional_yes', 'maybe', 'no'
        # Under 100 amp per unit total = red flag.
        pass

    def get_inspection(self, address1: str) -> Optional[Dict]:
        response = self.supabase.table('inspections').select('*').eq('address1', address1).limit(1).single().execute()
        return response.data

    def upsert_inspection(self, inspection_data: Dict) -> Dict:
        response = self.supabase.table('inspections').upsert(inspection_data).execute()

        if not response.data:
            raise Exception("Failed to upsert inspection record - no data returned")

        return response.data[0]
    
    def get_unit_inspection(self, rent_estimate_id: int) -> Optional[Dict]:
        response = self.supabase.table('unit_inspections').select('*').eq('rent_estimate_id', rent_estimate_id).limit(1).single().execute()
        return response.data

    def upsert_unit_inspection(self, unit_inspection_data: dict) -> Dict:
        response = self.supabase.table('unit_inspections').upsert(unit_inspection_data).execute()

        if not response.data:
            raise Exception("Failed to upsert unit inspection record - no data returned")

        return response.data[0]
    
    def get_property_condition(self, row) -> str:
        condition = "" # excellent, good, fair, poor

        # ideally, we want our property inspection data to give us this score, instead of our gut feeling about it

        return condition
    
    def has_dealbreakers(self, row) -> bool:
        has_dealbreakers = False

        return has_dealbreakers
    
    def get_total_diy_repair_costs(self, row) -> int:
        total_cost = 0

        sqr_ft = row["square_ft"]
        units = row["units"]
        beds = row["beds"]
        baths = row["baths"]

        # get all the unit configurations

        ## HIGH DIY
        # painting
        # kitch cabinet painting
        # Landscaping setup (native plantings, basic yard work)
        # Storage systems
        # Fire safety upgrades (smoke detectors, extinguishers, emergency lighting)
        # Kitchen backsplash

        # Revamping doors

        ## MODERATE DIT
        # Updated lighting fixtures
        # luxury vinly flooring
        # Appliance installation (+ cost of appliances)
        # Ceiling fans (DIY if electrical box already present)
        # Bathroom exhaust fans
        # Entry door REPLACEMENT 
        # Hardwood floor refinishing (only if the property has hardwoods)
        # Pet fencing
        # Parking lot striping

        return total_cost
    
    def get_total_pro_repair_costs(self, row) -> int:
        # Bathroom fixtures / vanity
        # Bathroom rile work
        # Deck/patio construction
        # Security cameras
        # Exterior painting
        # In-unit W/D installation
        # Countertops
        # Central A/C
        # Windows
        # Garage/carport
        # Furnace
        # Electrical panel
        # Plumbing systems
        # Roof
        # Sewer/drainage
        # Foundation

        return 0
    
    def get_est_diy_repair_costs(self, row) -> int:
        return 0
    
    def get_est_pro_repair_costs(self, row) -> int:
        return 0

    def is_property_inspection_done(self, address1: str) -> bool:
        """
        Check if a property has a complete inspection with ALL required fields filled

        A complete inspection requires ALL fields except notes fields to be filled in.
        Notes fields are optional: roof_notes, basement_notes, electrical_notes,
        plumbing_notes, legal_notes, walkability_notes, neighborhood_notes

        Conditional fields are required based on other values:
        - sump_pump_condition: required if has_sump_pump is True
        - rental_license_expiry: required if has_rental_license is True
        - laundry_condition: required if has_shared_laundry is True
        - laundry_coin_revenue_monthly: required if has_shared_laundry is True

        Args:
            address1: Property address to check

        Returns:
            True if inspection is complete with all required fields, False otherwise
        """
        inspection = self.get_inspection(address1)

        if not inspection:
            return False

        if not inspection.get('inspection_date'):
            return False

        model_fields = InspectionCreate.model_fields.keys()

        excluded_fields = {
            'address1',
            'roof_notes',
            'basement_notes',
            'electrical_notes',
            'plumbing_notes',
            'legal_notes',
            'walkability_notes',
            'neighborhood_notes',
            'sump_pump_condition',
            'rental_license_expiry',
            'laundry_condition',
            'laundry_coin_revenue_monthly',
        }

        for field_name in model_fields:
            if field_name not in excluded_fields:
                value = inspection.get(field_name)
                if value is None:
                    return False

        if inspection.get('has_sump_pump') and not inspection.get('sump_pump_condition'):
            return False

        if inspection.get('has_rental_license') and not inspection.get('rental_license_expiry'):
            return False

        if inspection.get('has_shared_laundry'):
            if not inspection.get('laundry_condition') or inspection.get('laundry_coin_revenue_monthly') is None:
                return False

        return True