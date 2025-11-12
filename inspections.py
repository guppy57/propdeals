from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import date
from supabase import Client

class InspectionCreate(BaseModel):
    address1: str
    inspection_date: Optional[date] = None

    # FOUNDATION & STRUCTURE
    foundation_type: Optional[str] = None
    foundation_condition: Optional[str] = None
    foundation_crack_size_inches: Optional[float] = None
    floor_condition: Optional[str] = None
    structural_issues: Optional[str] = None
    structural_repair_cost_est: Optional[int] = None

    # ROOF & DRAINAGE
    roof_age_years: Optional[int] = None
    roof_type: Optional[str] = None
    roof_condition: Optional[str] = None
    roof_has_visible_damage: Optional[bool] = False
    roof_replacement_cost_est: Optional[int] = None
    gutters_condition: Optional[str] = None
    drainage_adequate: Optional[bool] = True
    roof_notes: Optional[str] = None

    # BASEMENT/CRAWLSPACE
    basement_type: Optional[str] = None
    basement_water_issues: Optional[str] = None
    has_sump_pump: Optional[bool] = False
    sump_pump_condition: Optional[str] = None
    basement_has_mold: Optional[bool] = False
    basement_waterproofed: Optional[bool] = False
    basement_notes: Optional[str] = None

    # ELECTRICAL SYSTEM
    electrical_panel_type: Optional[str] = None
    electrical_amp_service: Optional[int] = None
    electrical_wiring_type: Optional[str] = None
    has_separate_meters: Optional[bool] = False
    electrical_issues: Optional[str] = None
    rewiring_cost_est: Optional[int] = None
    electrical_notes: Optional[str] = None

    # PLUMBING SYSTEM
    plumbing_pipe_material: Optional[str] = None
    plumbing_water_pressure: Optional[str] = None
    plumbing_sewer_line_type: Optional[str] = None
    plumbing_has_issues: Optional[bool] = False
    replumbing_cost_est: Optional[int] = None
    plumbing_notes: Optional[str] = None

    # EXTERIOR & COMMON AREAS
    exterior_siding_condition: Optional[str] = None
    exterior_paint_condition: Optional[str] = None
    exterior_trim_condition: Optional[str] = None
    parking_type: Optional[str] = None
    parking_spaces_count: Optional[int] = None
    has_shared_laundry: Optional[bool] = False
    laundry_condition: Optional[str] = None
    laundry_coin_revenue_monthly: Optional[int] = None
    yard_condition: Optional[str] = None

    # UTILITIES & OPERATIONS
    tenant_pays_electric: Optional[bool] = True
    tenant_pays_gas: Optional[bool] = True
    tenant_pays_water: Optional[bool] = False
    tenant_pays_trash: Optional[bool] = False
    landlord_utility_cost_monthly: Optional[int] = None

    # LEGAL & PERMITS
    has_rental_license: Optional[bool] = False
    rental_license_expiry: Optional[date] = None
    has_code_violations: Optional[bool] = False
    zoning_allows_multifamily: Optional[bool] = True
    legal_notes: Optional[str] = None

    # NEIGHBORHOOD ASSESSMENT
    neighborhood_safety_rating: Optional[int] = Field(None, ge=1, le=10)
    walkability_notes: Optional[str] = None
    would_live_here: Optional[bool] = None
    neighborhood_notes: Optional[str] = None
    gut_feeling_rating: Optional[int] = Field(None, ge=1, le=10)

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
        response = self.supabase.table('inspections').select('*').eq('address1', address1).execute()

        if response.data and len(response.data) > 0:
            return response.data[0]

        return None

    def upsert_inspection(self, inspection_data: Dict) -> Dict:
        response = self.supabase.table('inspections').upsert(inspection_data).execute()

        if not response.data:
            raise Exception("Failed to upsert inspection record - no data returned")

        return response.data[0]

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