import os
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client
from typing import Optional
from run import reload_dataframe, get_all_phase1_qualifying_properties, get_phase2_data_checklist, get_all_phase2_properties, get_combined_phase1_qualifiers
from inspections import InspectionsClient
from helpers import convert_numpy_types

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections_client = InspectionsClient(supabase)
df = None
rents = None

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
            'apr_rate': float(loan_data['apr_rate']),
            'down_payment_rate': float(loan_data['down_payment_rate']),
            'years': int(loan_data['years']),
            'mip_upfront_rate': float(loan_data['mip_upfront_rate']),
            'mip_annual_rate': float(loan_data['mip_annual_rate'])
        }
    except Exception as e:
        print(f"⚠️ Failed to load loan details from database: {str(e)}")
        print("🔧 Using default loan settings")
        return default_loan
loan_details = load_loan_details()
interest_rate = loan_details['interest_rate']
apr_rate = loan_details['apr_rate']
down_payment_rate = loan_details['down_payment_rate']
loan_length_years = loan_details['years']
mip_upfront_rate = loan_details['mip_upfront_rate']
mip_annual_rate = loan_details['mip_annual_rate']

def reload_dataframe_logic():
    global df, rents
    
    try:
        reload_dataframe()
        from run import df as run_df, rents as run_rents
        df = run_df.copy()
        rents = run_rents.copy() if run_rents is not None else None
        
    except Exception as e:
        print(f"⚠️ Failed to use run.py reload logic: {str(e)}")
        print("🔧 Using basic property data loading")

        # Fallback: just load properties without full calculations
        properties_get_response = supabase.table('properties').select('*').limit(10000).execute()
        df = pd.DataFrame(properties_get_response.data)
        rents = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global df, rents
    print("🔄 Starting PropDeals API...")
    
    try:
        print("📊 Loading property data...")
        properties_get_response = supabase.table('properties').select('*').limit(10000).execute()
        df = pd.DataFrame(properties_get_response.data)
        reload_dataframe_logic()
        print(f"✅ Loaded {len(df) if df is not None else 0} properties")
    except Exception as e:
        print(f"⚠️ Failed to load property data during startup: {str(e)}")
        print("🚀 API will start without data - data will be loaded on first request")
        df = None
        rents = None
    
    yield
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
    global df, rents
    
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

@app.get("/properties")
async def get_all_properties_route(
    status: Optional[str] = Query(None, description="Filter by property status (active, sold, passed)")
):
    global df
    
    if df is None or df.empty:
        try:
            print("🔄 Loading data on demand...")
            properties_get_response = supabase.table('properties').select('*').limit(10000).execute()
            df = pd.DataFrame(properties_get_response.data)
            
            if df.empty:
                raise HTTPException(status_code=404, detail="No properties found in database")
                
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Unable to load property data: {str(e)}")
    
    filtered_df = df.copy()
    
    if status:
        filtered_df = filtered_df[filtered_df['status'] == status]
    
    properties = filtered_df.fillna(0).to_dict('records')
    
    return {
        "count": len(filtered_df),
        "properties": properties,
    }

@app.get("/properties/phase1")
async def get_phase1_qualifiers_route():
    global df

    reload_dataframe_logic()
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    assumptions_response = supabase.table('assumptions').select("*").eq("id", 1).limit(1).single().execute()
    
    try:
        current, contingent, creative = get_all_phase1_qualifying_properties()
        current = convert_numpy_types(current.fillna(0).to_dict('records'))
        contingent = convert_numpy_types(contingent.fillna(0).to_dict('records'))
        creative = convert_numpy_types(creative.fillna(0).to_dict('records'))

        ia_current, ia_contingent, ia_creative = get_all_phase1_qualifying_properties(False)
        ia_current = convert_numpy_types(ia_current.fillna(0).to_dict('records'))
        ia_contingent = convert_numpy_types(ia_contingent.fillna(0).to_dict('records'))
        ia_creative = convert_numpy_types(ia_creative.fillna(0).to_dict('records'))

        return {
            "assumptions": assumptions_response.data,
            "properties": {
                "current_prices": current,
                "contingent_10prcnt_price_reduction": contingent,
                "creative_pricing": creative,
            },
            "inactive_properties": {
                "current_prices": ia_current,
                "contingent_10prcnt_price_reduction": ia_contingent,
                "creative_pricing": ia_creative,
            }
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error filtering properties: {str(e)}")

@app.get("/properties/phase2")
async def get_phase2_data_checklist_route():
    """
    Gets all phase1 properties and their subsequent 'data checklist' to easily display the remaining work
    we have to do to get all data needed for Phase 2
    """
    global df

    reload_dataframe_logic()

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")

    try:
        result = get_all_phase2_properties()
        return {
            "qualifiers": convert_numpy_types(
                result["qualifiers"].fillna(0).to_dict("records")
            )
            if hasattr(result["qualifiers"], "to_dict")
            else result["qualifiers"],
            "disqualifiers": convert_numpy_types(
                result["disqualifiers"].fillna(0).to_dict("records")
            )
            if hasattr(result["disqualifiers"], "to_dict")
            else result["disqualifiers"],
            "needs_research_1": convert_numpy_types(
                result["needs_research_1"].fillna(0).to_dict("records")
            )
            if hasattr(result["needs_research_1"], "to_dict")
            else result["needs_research_1"],
            "needs_research_2": convert_numpy_types(
                result["needs_research_2"].fillna(0).to_dict("records")
            )
            if hasattr(result["needs_research_2"], "to_dict")
            else result["needs_research_2"],
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error getting phase2 properties: {str(e)}")

@app.get("/properties/phase2/{address1}/data-checklist")
async def get_phase2_data_checklist_for_property_route(address1: str):
    global df

    reload_dataframe_logic()

    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    try:
        checklist = get_phase2_data_checklist()
        properties = get_combined_phase1_qualifiers()
        property = properties.query('address1 == @address1')

        return {
            "checklist": checklist[address1],
            "property": convert_numpy_types(property.fillna(0).to_dict('records')[0])
        }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error getting phase2 data checklist for property: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)