from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

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

class UnitInspectionCreate(BaseModel):
    rent_estimate_id: int
    inspection_date: Optional[date] = None

    # UNIT OCCUPANCY & LEASE INFO
    unit_occupied: Optional[bool] = False
    current_rent: Optional[int] = None
    lease_end_date: Optional[date] = None
    move_in_ready: Optional[bool] = True

    # HVAC SYSTEMS
    has_own_furnace: Optional[bool] = True
    furnace_age_years: Optional[int] = None
    furnace_type: Optional[str] = None
    furnace_condition: Optional[str] = None
    water_heater_age_years: Optional[int] = None
    water_heater_condition: Optional[str] = None
    ac_type: Optional[str] = None
    ac_age_years: Optional[int] = None
    ac_condition: Optional[str] = None
    hvac_replacement_cost_est: Optional[int] = None
    has_separate_thermostat: Optional[bool] = True

    # KITCHEN
    kitchen_condition: Optional[str] = None
    kitchen_has_stove: Optional[bool] = True
    kitchen_stove_condition: Optional[str] = None
    kitchen_has_fridge: Optional[bool] = True
    kitchen_fridge_condition: Optional[str] = None
    kitchen_has_dishwasher: Optional[bool] = False
    kitchen_dishwasher_condition: Optional[str] = None
    kitchen_appliances_age_years: Optional[int] = None
    kitchen_cabinets_condition: Optional[str] = None
    kitchen_countertop_material: Optional[str] = None
    kitchen_countertop_condition: Optional[str] = None
    kitchen_sink_condition: Optional[str] = None
    kitchen_update_cost_est: Optional[int] = None
    kitchen_notes: Optional[str] = None

    # BATHROOM
    bathroom_condition: Optional[str] = None
    bathroom_shower_tub_condition: Optional[str] = None
    bathroom_has_mold: Optional[bool] = False
    bathroom_toilet_condition: Optional[str] = None
    bathroom_sink_vanity_condition: Optional[str] = None
    bathroom_water_pressure: Optional[str] = None
    bathroom_has_exhaust_fan: Optional[bool] = True
    bathroom_update_cost_est: Optional[int] = None
    bathroom_notes: Optional[str] = None

    # FLOORING
    flooring_type: Optional[str] = None
    flooring_condition: Optional[str] = None
    flooring_has_stains: Optional[bool] = False
    flooring_has_damage: Optional[bool] = False
    flooring_has_odor: Optional[bool] = False
    flooring_replacement_cost_est: Optional[int] = None
    flooring_notes: Optional[str] = None

    # WALLS & PAINT
    walls_paint_condition: Optional[str] = None
    walls_paint_color: Optional[str] = None
    walls_has_damage: Optional[bool] = False
    walls_has_water_stains: Optional[bool] = False
    paint_cost_est: Optional[int] = None
    walls_notes: Optional[str] = None

    # WINDOWS
    windows_condition: Optional[str] = None
    windows_type: Optional[str] = None
    windows_open_close_properly: Optional[bool] = True
    windows_have_broken_panes: Optional[bool] = False
    windows_drafty: Optional[bool] = False
    windows_replacement_cost_est: Optional[int] = None

    # OVERALL UNIT ASSESSMENT
    unit_sqft_actual: Optional[int] = None
    unit_total_rehab_cost_est: Optional[int] = None
    unit_condition_rating: Optional[str] = None
    unit_notes: Optional[str] = None
