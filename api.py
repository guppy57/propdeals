import os
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import List, Dict, Any, Optional

# Import shared functions from run.py
from run import reload_dataframe, get_reduced_pp_df, get_all_phase1_qualifying_properties

load_dotenv()

# Initialize Supabase client early
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

# Global dataframe - will be loaded on startup
df = None
rents = None

# Load assumptions with fallbacks
def load_assumptions():
    """Load assumptions from YAML file with fallback defaults"""
    default_assumptions = {
        'appreciation_rate': 0.02,
        'rent_appreciation_rate': 0.01,
        'property_tax_rate': 0.01565,
        'home_insurance_rate': 0.02,
        'vacancy_rate': 0.0833,
        'repair_savings_rate': 0.05,
        'closing_costs_rate': 0.04,
        'unit_living_in': 'cheapest'
    }
    
    try:
        import yaml
        with open('assumptions.yaml', 'r') as file:
            assumptions = yaml.safe_load(file)
        print("✅ Loaded assumptions from assumptions.yaml")
        return assumptions
    except Exception as e:
        print(f"⚠️ Failed to load assumptions.yaml: {str(e)}")
        print("🔧 Using default assumptions")
        return default_assumptions

# Load assumptions on module import
assumptions = load_assumptions()
appreciation_rate = assumptions["appreciation_rate"]
rent_appreciation_rate = assumptions["rent_appreciation_rate"]
property_tax_rate = assumptions["property_tax_rate"]
home_insurance_rate = assumptions["home_insurance_rate"]
vacancy_rate = assumptions["vacancy_rate"]
repair_savings_rate = assumptions["repair_savings_rate"]
closing_costs_rate = assumptions["closing_costs_rate"]
live_in_unit_setting = assumptions["unit_living_in"]

# Load loan details with fallbacks
def load_loan_details():
    """Load FHA loan details from Supabase with fallback defaults"""
    default_loan = {
        'interest_rate': 0.065,  # 6.5%
        'down_payment_rate': 0.035,  # 3.5%
        'years': 30,
        'mip_upfront_rate': 0.0175,
        'mip_annual_rate': 0.0055
    }
    
    try:
        fha_loan_get_response = supabase.table('loans').select("*").eq("id", 1).limit(1).single().execute()
        loan_data = fha_loan_get_response.data
        print("✅ Loaded loan details from database")
        return {
            'interest_rate': float(loan_data['interest_rate']),
            'down_payment_rate': float(loan_data['down_payment_rate']),
            'years': float(loan_data['years']),
            'mip_upfront_rate': float(loan_data['mip_upfront_rate']),
            'mip_annual_rate': float(loan_data['mip_annual_rate'])
        }
    except Exception as e:
        print(f"⚠️ Failed to load loan details from database: {str(e)}")
        print("🔧 Using default loan settings")
        return default_loan

# Load loan details on module import
loan_details = load_loan_details()
interest_rate = loan_details['interest_rate']
down_payment_rate = loan_details['down_payment_rate']
loan_length_years = loan_details['years']
mip_upfront_rate = loan_details['mip_upfront_rate']
mip_annual_rate = loan_details['mip_annual_rate']

def reload_dataframe_logic():
    """Reload and recalculate property data (adapted from run.py)"""
    global df, rents
    
    try:
        # Try to use the existing reload_dataframe function from run.py
        reload_dataframe()
        
        # Import the updated dataframes from run.py
        from run import df as run_df, rents as run_rents
        
        # Update our global variables
        df = run_df.copy()
        rents = run_rents.copy() if run_rents is not None else None
        
    except Exception as e:
        print(f"⚠️ Failed to use run.py reload logic: {str(e)}")
        print("🔧 Using basic property data loading")
        
        # Fallback: just load properties without full calculations
        properties_get_response = supabase.table('properties').select('*').execute()
        df = pd.DataFrame(properties_get_response.data)
        rents = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize data on startup and cleanup on shutdown"""
    global df, rents
    
    # Startup
    print("🔄 Starting PropDeals API...")
    
    try:
        print("📊 Loading property data...")
        
        # Load data using the same logic as run.py
        properties_get_response = supabase.table('properties').select('*').execute()
        df = pd.DataFrame(properties_get_response.data)
        
        # Apply all calculations (simplified version of reload_dataframe)
        reload_dataframe_logic()
        
        print(f"✅ Loaded {len(df) if df is not None else 0} properties")
        
    except Exception as e:
        print(f"⚠️ Failed to load property data during startup: {str(e)}")
        print("🚀 API will start without data - data will be loaded on first request")
        df = None
        rents = None
    
    yield
    
    # Shutdown
    print("🛑 Shutting down PropDeals API")

app = FastAPI(
    title="PropDeals API",
    description="Real estate investment analysis API for property deals",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """API health check"""
    global df, rents
    
    # Check data status
    data_status = {
        "properties_loaded": df is not None and not df.empty,
        "property_count": len(df) if df is not None else 0,
        "rents_loaded": rents is not None and not rents.empty if rents is not None else False
    }
    
    return {
        "message": "PropDeals API is running", 
        "version": "1.0.0",
        "status": "healthy",
        "data": data_status
    }

@app.get("/properties", response_model=List[Dict[str, Any]])
async def get_all_properties(
    status: Optional[str] = Query(None, description="Filter by property status (active, sold, passed)")
):
    """Get all properties with optional status filter"""
    global df
    
    if df is None or df.empty:
        # Try to load data if not available
        try:
            print("🔄 Loading data on demand...")
            properties_get_response = supabase.table('properties').select('*').execute()
            df = pd.DataFrame(properties_get_response.data)
            
            if df.empty:
                raise HTTPException(status_code=404, detail="No properties found in database")
                
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Unable to load property data: {str(e)}")
    
    filtered_df = df.copy()
    
    if status:
        filtered_df = filtered_df[filtered_df['status'] == status]
    
    # Convert to records and handle NaN values
    properties = filtered_df.fillna(0).to_dict('records')
    
    return properties

@app.get("/properties/phase1")
async def get_phase1_qualifiers():
    global df
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    criteria = "status == 'active' & MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & cash_needed <= 25000 & monthly_cash_flow_y1 >= -400 & monthly_cash_flow_y2 >= 400"

    assumptions_response = supabase.table('assumptions').select("*").eq("id", 1).limit(1).single().execute()

    deal_score_total = 24
    
    try:
        current, contingent, creative = get_all_phase1_qualifying_properties()
        current = current.fillna(0).to_dict('records')
        contingent = contingent.fillna(0).to_dict('records')
        # creative = creative.fillna(0).to_dict('records')

        return {
            "criteria": criteria,
            "assumptions": assumptions_response.data,
            "deal_score_total": deal_score_total,
            "properties": {
                "current_prices": current,
                "contingent_10prcnt_price_reduction": contingent,
                "creative_pricing": creative,
            }
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error filtering properties: {str(e)}")

@app.get("/properties/{property_id}")
async def get_property(property_id: str):
    """Get detailed information for a specific property"""
    global df, rents
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    property_data = df[df['address1'] == property_id]
    
    if property_data.empty:
        raise HTTPException(status_code=404, detail=f"Property {property_id} not found")
    
    row = property_data.iloc[0].fillna(0).to_dict()
    
    # Add rent breakdown if available
    if rents is not None:
        property_rents = rents[rents['address1'] == property_id]
        if not property_rents.empty:
            row['rent_breakdown'] = property_rents.fillna(0).to_dict('records')
    
    return row

@app.get("/properties/{property_id}/analysis")
async def get_property_analysis(property_id: str):
    """Get detailed investment analysis for a specific property"""
    global df
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    property_data = df[df['address1'] == property_id]
    
    if property_data.empty:
        raise HTTPException(status_code=404, detail=f"Property {property_id} not found")
    
    row = property_data.iloc[0]
    
    # Calculate detailed scoring breakdown
    cf_y2_score = (3 if row["monthly_cash_flow_y2"] > 500 else 2 if row["monthly_cash_flow_y2"] > 400 else 1 if row["monthly_cash_flow_y2"] > 200 else 0)
    cf_y1_bonus = (3 if row["monthly_cash_flow_y1"] > 0 else 2 if row["monthly_cash_flow_y1"] > -350 else 0)
    coc_score = (3 if row["CoC_y2"] > 0.15 else 2 if row["CoC_y2"] > 0.12 else 1 if row["CoC_y2"] > 0.08 else 0)
    cap_score = (1 if row["cap_rate_y2"] > 0.06 else 0)
    mgr_score = (2 if row["MGR_PP"] >= 0.01 else 1 if row["MGR_PP"] >= 0.008 else 0)
    opex_score = (2 if 0.4 <= row["OpEx_Rent"] <= 0.6 else 1 if 0.3 <= row["OpEx_Rent"] <= 0.7 else 0)
    dscr_score = (2 if row["DSCR"] >= 1.25 else 1 if row["DSCR"] >= 1.1 else 0)
    cash_score = (2 if row["cash_needed"] < 20000 else 1 if row["cash_needed"] < 30000 else 0)
    grm_score = (1 if row["GRM_y2"] < 12 else 0)
    sqft_score = (2 if row["cost_per_sqrft"] < 100 else 1 if row["cost_per_sqrft"] < 150 else 0)
    age_score = (2 if row["home_age"] < 20 else 0)
    
    return {
        "property_id": property_id,
        "basic_info": {
            "address": row['address1'],
            "purchase_price": float(row['purchase_price']),
            "beds": int(row['beds']),
            "baths": float(row['baths']),
            "square_ft": float(row['square_ft']),
            "built_in": int(row['built_in']),
            "home_age": int(row['home_age']),
            "units": int(row['units'])
        },
        "financial_metrics": {
            "monthly_cash_flow_y1": float(row['monthly_cash_flow_y1']),
            "monthly_cash_flow_y2": float(row['monthly_cash_flow_y2']),
            "annual_cash_flow_y1": float(row['annual_cash_flow_y1']),
            "annual_cash_flow_y2": float(row['annual_cash_flow_y2']),
            "cap_rate_y1": float(row['cap_rate_y1']),
            "cap_rate_y2": float(row['cap_rate_y2']),
            "coc_y1": float(row['CoC_y1']),
            "coc_y2": float(row['CoC_y2']),
            "cash_needed": float(row['cash_needed']),
            "grm_y2": float(row['GRM_y2']),
            "mgr_pp": float(row['MGR_PP']),
            "opex_rent": float(row['OpEx_Rent']),
            "dscr": float(row['DSCR'])
        },
        "investment_scoring": {
            "deal_score": int(row['deal_score']),
            "deal_score_max": 24,
            "mobility_score": float(row['mobility_score']),
            "score_breakdown": {
                "cash_flow_y2": {"score": cf_y2_score, "max": 3},
                "cash_flow_y1_bonus": {"score": cf_y1_bonus, "max": 3},
                "cash_on_cash": {"score": coc_score, "max": 3},
                "cap_rate": {"score": cap_score, "max": 1},
                "one_percent_rule": {"score": mgr_score, "max": 2},
                "fifty_percent_rule": {"score": opex_score, "max": 2},
                "dscr": {"score": dscr_score, "max": 2},
                "cash_needed": {"score": cash_score, "max": 2},
                "grm": {"score": grm_score, "max": 1},
                "cost_per_sqft": {"score": sqft_score, "max": 2},
                "property_age": {"score": age_score, "max": 2}
            }
        },
        "forecasts": {
            "5_year_gains": float(row['5y_forecast']),
            "10_year_gains": float(row['10y_forecast'])
        },
        "mobility": {
            "walk_score": float(row['walk_score']),
            "transit_score": float(row['transit_score']),
            "bike_score": float(row['bike_score']),
            "mobility_score": float(row['mobility_score'])
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)