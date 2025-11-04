import os
import pandas as pd
import yaml
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import List, Dict, Any, Optional

# Import shared functions from run.py
from run import (
    reload_dataframe, 
    get_reduced_pp_df,
    deal_score_property,
    mobility_score,
    get_expected_gains,
    format_currency,
    format_percentage,
    format_number
)

load_dotenv()

# Global dataframe - will be loaded on startup
df = None
rents = None

def reload_dataframe_logic():
    """Reload and recalculate property data (adapted from run.py)"""
    global df, rents
    
    # This will use the existing reload_dataframe function
    # We need to import the global variables from run.py
    from run import df as run_df, rents as run_rents
    
    # Force reload of data
    reload_dataframe()
    
    # Update our global variables
    df = run_df.copy()
    rents = run_rents.copy() if run_rents is not None else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize data on startup and cleanup on shutdown"""
    global df, rents
    
    # Startup
    print("🔄 Loading property data...")
    
    # Load data using the same logic as run.py
    properties_get_response = supabase.table('properties').select('*').execute()
    df = pd.DataFrame(properties_get_response.data)
    
    # Apply all calculations (simplified version of reload_dataframe)
    reload_dataframe_logic()
    
    print(f"✅ Loaded {len(df) if df is not None else 0} properties")
    
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

# Initialize Supabase client
supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

@app.get("/")
async def root():
    """API health check"""
    return {"message": "PropDeals API is running", "version": "1.0.0"}

@app.get("/properties", response_model=List[Dict[str, Any]])
async def get_all_properties(
    status: Optional[str] = Query(None, description="Filter by property status (active, sold, passed)")
):
    """Get all properties with optional status filter"""
    global df
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    filtered_df = df.copy()
    
    if status:
        filtered_df = filtered_df[filtered_df['status'] == status]
    
    # Convert to records and handle NaN values
    properties = filtered_df.fillna(0).to_dict('records')
    
    return properties

@app.get("/properties/phase1")
async def get_phase1_qualifiers():
    """Get properties that meet Phase 1 investment criteria"""
    global df
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    criteria = "status == 'active' & MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & cash_needed <= 25000 & monthly_cash_flow_y1 >= -400 & monthly_cash_flow_y2 >= 400"
    
    try:
        filtered_df = df.query(criteria)
        properties = filtered_df.fillna(0).to_dict('records')
        
        return {
            "count": len(properties),
            "criteria": criteria,
            "properties": properties
        }
    except Exception as e:
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

@app.get("/properties/reduced-price/{reduction_percent}")
async def get_properties_with_reduced_price(reduction_percent: float):
    """Get all properties with reduced purchase price and recalculated metrics"""
    if reduction_percent < 0 or reduction_percent > 50:
        raise HTTPException(status_code=400, detail="Reduction percent must be between 0 and 50")
    
    try:
        reduction_factor = reduction_percent / 100.0
        reduced_df = get_reduced_pp_df(reduction_factor)
        properties = reduced_df.fillna(0).to_dict('records')
        
        return {
            "reduction_percent": reduction_percent,
            "reduction_factor": reduction_factor,
            "count": len(properties),
            "properties": properties
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error calculating reduced prices: {str(e)}")

@app.get("/stats/summary")
async def get_summary_stats():
    """Get summary statistics for all properties"""
    global df
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    active_properties = df[df['status'] == 'active']
    
    # Phase 1 qualifiers
    phase1_criteria = "status == 'active' & MGR_PP > 0.01 & OpEx_Rent < 0.5 & DSCR > 1.25 & cash_needed <= 25000 & monthly_cash_flow_y1 >= -400 & monthly_cash_flow_y2 >= 400"
    phase1_count = len(df.query(phase1_criteria))
    
    return {
        "total_properties": len(df),
        "active_properties": len(active_properties),
        "phase1_qualifiers": phase1_count,
        "avg_purchase_price": float(active_properties['purchase_price'].mean()) if not active_properties.empty else 0,
        "avg_cash_needed": float(active_properties['cash_needed'].mean()) if not active_properties.empty else 0,
        "avg_deal_score": float(active_properties['deal_score'].mean()) if not active_properties.empty else 0,
        "avg_mobility_score": float(active_properties['mobility_score'].mean()) if not active_properties.empty else 0,
        "price_range": {
            "min": float(active_properties['purchase_price'].min()) if not active_properties.empty else 0,
            "max": float(active_properties['purchase_price'].max()) if not active_properties.empty else 0
        }
    }



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)