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
        condition = "fair" # excellent, good, fair, poor

        # ideally, we want our property inspection data to give us this score, instead of our gut feeling about it

        return condition
    
    def has_dealbreakers(self, row) -> bool:
        has_dealbreakers = False

        return has_dealbreakers
    
    def get_total_diy_repair_costs(self, row) -> int:
        """
        Calculate total DIY renovation costs for full cosmetic refresh.
        Assumes advanced DIY skills (can handle flooring, tile, basic electrical).
        All costs are Iowa/Midwest adjusted (0.90x national average).

        Sources: HomeAdvisor 2025, RSMeans, Remodeling Magazine Cost vs Value
        """
        total_cost = 0

        sqr_ft = row["square_ft"]
        units = row["units"]
        beds = row["beds"]
        baths = row["baths"]

        # Regional adjustment for Iowa/Midwest pricing
        REGIONAL_MULTIPLIER = 0.90

        ## HIGH DIY CATEGORIES (70-90% labor savings)

        # Interior painting - walls and ceilings
        # $2/sq ft DIY (materials: paint, primer, supplies)
        # Assumes 2 coats paint + primer for all interior surfaces
        painting_cost = sqr_ft * 2.0
        total_cost += painting_cost

        # Kitchen cabinet painting - refresh existing cabinets
        # $400 per kitchen DIY (deglosser, primer, paint, hardware)
        # Assumes 1 kitchen per unit
        cabinet_painting_cost = units * 400
        total_cost += cabinet_painting_cost

        # Kitchen backsplash - tile installation
        # $10/sq ft × 15 sq ft per kitchen (materials: tile, thinset, grout)
        # Assumes standard 15 sq ft backsplash per kitchen
        backsplash_cost = units * 15 * 10
        total_cost += backsplash_cost

        # Landscaping - native plantings and basic yard work
        # $1.50/sq ft for 500 sq ft (mulch, plants, edging, basic materials)
        # Fixed 500 sq ft landscaping area per property
        landscaping_cost = 500 * 1.5
        total_cost += landscaping_cost

        # Storage systems - closet organizers and shelving
        # $150 per unit (wire shelving, brackets, installation supplies)
        storage_cost = units * 150
        total_cost += storage_cost

        # Fire safety upgrades - smoke detectors, extinguishers, emergency lighting
        # $75 per unit (detectors, CO monitors, fire extinguisher, exit signs)
        fire_safety_cost = units * 75
        total_cost += fire_safety_cost

        ## MODERATE DIY CATEGORIES (30-50% labor savings)

        # Updated lighting fixtures - modern fixtures throughout
        # $200 per unit DIY (basic fixtures: kitchen, bathroom, bedroom lights)
        # Assumes electrical boxes already present
        lighting_cost = units * 200
        total_cost += lighting_cost

        # Luxury vinyl flooring (LVP/LVT) - full property
        # $6/sq ft DIY (materials + underlayment, assuming click-lock installation)
        # Full cosmetic refresh = replace all flooring
        vinyl_flooring_cost = sqr_ft * 6.0
        total_cost += vinyl_flooring_cost

        # Appliance installation + purchase - full kitchen package
        # $2,500 per unit (range, refrigerator, dishwasher, microwave + installation)
        # Mid-range appliances, DIY installation
        appliances_cost = units * 2500
        total_cost += appliances_cost

        # Ceiling fans - bedrooms and common areas
        # $250 per bedroom DIY (fan + light kit, assumes electrical box exists)
        ceiling_fans_cost = beds * 250
        total_cost += ceiling_fans_cost

        # Bathroom exhaust fans - improve ventilation
        # $100 per bathroom DIY (fan unit, ducting if needed)
        bathroom_fans_cost = baths * 100
        total_cost += bathroom_fans_cost

        # Entry door replacement - exterior security doors
        # $600 per unit DIY (steel door + hardware, materials only)
        entry_doors_cost = units * 600
        total_cost += entry_doors_cost

        # Hardwood floor refinishing - sand and refinish existing hardwoods
        # $1.50/sq ft DIY (rental sander, stain, polyurethane)
        # Assumes 30% of properties have hardwood under carpet/vinyl
        hardwood_refinishing_cost = sqr_ft * 0.30 * 1.5
        total_cost += hardwood_refinishing_cost

        # Pet fencing - designated pet area for tenant convenience
        # $200 flat (basic fencing materials for small area)
        pet_fencing_cost = 200
        total_cost += pet_fencing_cost

        # Parking lot striping - refresh parking space lines
        # $0.30/sq ft for 3,000 sq ft (paint + equipment rental)
        # Assumes 20 spaces × 150 sq ft per space = 3,000 sq ft
        parking_striping_cost = 3000 * 0.30
        total_cost += parking_striping_cost

        # Apply regional adjustment for Iowa/Midwest pricing
        total_cost = int(total_cost * REGIONAL_MULTIPLIER)

        return total_cost
    
    def get_total_pro_repair_costs(self, row) -> int:
        """
        Calculate total professional renovation costs for full cosmetic refresh.
        These items require licensed contractors (plumbers, electricians, HVAC techs, etc.).
        All costs are Iowa/Midwest adjusted (0.90x national average).

        Sources: HomeAdvisor 2025, RSMeans, Remodeling Magazine Cost vs Value
        """
        total_cost = 0

        sqr_ft = row["square_ft"]
        units = row["units"]
        beds = row["beds"]
        baths = row["baths"]

        # Regional adjustment for Iowa/Midwest pricing
        REGIONAL_MULTIPLIER = 0.90

        ## BATHROOM RENOVATIONS (requires licensed plumber)

        # Bathroom fixtures and vanity replacement
        # $1,200 per bathroom (vanity, toilet, sink, faucets installed)
        # Mid-range fixtures with professional installation
        bathroom_fixtures_cost = baths * 1200
        total_cost += bathroom_fixtures_cost

        # Bathroom tile work - floor and shower/tub surround
        # $20/sq ft × 50 sq ft per bathroom (materials + labor)
        # Assumes 30 sq ft floor + 20 sq ft shower surround per bath
        bathroom_tile_cost = baths * 50 * 20
        total_cost += bathroom_tile_cost

        ## KITCHEN RENOVATIONS

        # Countertops - quartz or granite
        # $80/sq ft × 30 sq ft per kitchen (materials + fabrication + installation)
        # Mid-range quartz, includes cutouts and edges
        countertops_cost = units * 30 * 80
        total_cost += countertops_cost

        ## EXTERIOR IMPROVEMENTS

        # Exterior painting - full house
        # $3.50/sq ft for exterior wall area (prep + 2 coats)
        # Assumes exterior wall area = sqr_ft / units × 1.2 (accounts for height)
        exterior_wall_area = (sqr_ft / units) * 1.2 * units
        exterior_painting_cost = exterior_wall_area * 3.5
        total_cost += exterior_painting_cost

        # Deck or patio construction
        # $35/sq ft × 200 sq ft (composite deck or stamped concrete patio)
        # Fixed 200 sq ft outdoor living space per property
        deck_patio_cost = 200 * 35
        total_cost += deck_patio_cost

        ## MECHANICAL SYSTEMS (requires licensed HVAC tech)

        # Central HVAC system - furnace + A/C replacement
        # $7,500 per unit (complete system: furnace, condenser, air handler, ductwork inspection)
        # Assumes separate system per unit or proportional cost for shared systems
        hvac_cost = units * 7500
        total_cost += hvac_cost

        ## ELECTRICAL SYSTEMS (requires licensed electrician)

        # Electrical panel upgrade
        # $1,500 per property (200A service upgrade with new panel)
        # Fixed cost per property, not per unit
        electrical_panel_cost = 1500
        total_cost += electrical_panel_cost

        ## PLUMBING SYSTEMS (requires licensed plumber)

        # Plumbing system updates
        # $1,000 per unit (fixture updates, valve replacements, minor repairs)
        # Does not include full replumb, just essential updates
        plumbing_cost = units * 1000
        total_cost += plumbing_cost

        # Sewer and drainage improvements
        # $800 per unit (sewer line inspection, minor repairs, drain cleaning)
        # Does not include full sewer line replacement
        sewer_drainage_cost = units * 800
        total_cost += sewer_drainage_cost

        ## STRUCTURAL SYSTEMS

        # Roof replacement
        # $8/sq ft × roof area (architectural shingles + installation)
        # Roof area = sqr_ft / units × 1.2 (accounts for pitch and overhang) × units
        roof_area = (sqr_ft / units) * 1.2 * units
        roof_cost = roof_area * 8
        total_cost += roof_cost

        # Foundation repairs
        # $3,000 flat (minor crack sealing, waterproofing, settling repairs)
        # Does not include major structural work
        foundation_cost = 3000
        total_cost += foundation_cost

        ## ADDITIONAL IMPROVEMENTS

        # Window replacement - full property
        # $600 per window × estimated window count
        # Assumes 2.5 windows per bedroom + 3 common area windows
        # Double-pane, energy-efficient windows with professional installation
        window_count = int(beds * 2.5 + 3)
        windows_cost = window_count * 600
        total_cost += windows_cost

        # In-unit washer/dryer hookup installation
        # $250 per unit (plumbing + electrical + venting)
        # Assumes hookups don't currently exist
        wd_hookup_cost = units * 250
        total_cost += wd_hookup_cost

        # Security camera system
        # $150 per camera × 4 cameras (equipment + professional installation)
        # Standard system: 2 exterior, 1 entry, 1 parking area
        security_cameras_cost = 4 * 150
        total_cost += security_cameras_cost

        # Apply regional adjustment for Iowa/Midwest pricing
        total_cost = int(total_cost * REGIONAL_MULTIPLIER)

        return total_cost
    
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
        # inspection = self.get_inspection(address1)

        # if not inspection:
        #     return False

        # if not inspection.get('inspection_date'):
        #     return False

        # model_fields = InspectionCreate.model_fields.keys()

        # excluded_fields = {
        #     'address1',
        #     'roof_notes',
        #     'basement_notes',
        #     'electrical_notes',
        #     'plumbing_notes',
        #     'legal_notes',
        #     'walkability_notes',
        #     'neighborhood_notes',
        #     'sump_pump_condition',
        #     'rental_license_expiry',
        #     'laundry_condition',
        #     'laundry_coin_revenue_monthly',
        # }

        # for field_name in model_fields:
        #     if field_name not in excluded_fields:
        #         value = inspection.get(field_name)
        #         if value is None:
        #             return False

        # if inspection.get('has_sump_pump') and not inspection.get('sump_pump_condition'):
        #     return False

        # if inspection.get('has_rental_license') and not inspection.get('rental_license_expiry'):
        #     return False

        # if inspection.get('has_shared_laundry'):
        #     if not inspection.get('laundry_condition') or inspection.get('laundry_coin_revenue_monthly') is None:
        #         return False

        # return True

        return False