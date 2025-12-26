import os
import pandas as pd
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from supabase import create_client, Client
from run import reload_dataframe, get_phase1_research_list 
from inspections import InspectionsClient
from helpers import convert_numpy_types

load_dotenv()

supabase: Client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
inspections_client = InspectionsClient(supabase)
df = None
rents = None
loan = 2

def load_loan_details():
    try:
        fha_loan_get_response = supabase.table('loans').select("*").eq("id", 2).limit(1).single().execute()
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

@app.get("/properties/phase1/tour-list")
async def get_phase1_qualifiers_route():
    global df

    reload_dataframe_logic()
    
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No properties found")
    
    try:
        tour_list, _ = get_phase1_research_list() 
        converted = convert_numpy_types(tour_list.fillna(0).to_dict('records'))
        return { "properties": converted }
    except Exception as e:
        print(e)
        raise HTTPException(status_code=500, detail=f"Error filtering properties: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)