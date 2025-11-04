#!/usr/bin/env python3
"""
Development server startup script for PropDeals API
"""

import uvicorn
import os

if __name__ == "__main__":
    # Set development environment
    os.environ["ENVIRONMENT"] = "development"
    
    print("🚀 Starting PropDeals API...")
    print("📊 Dashboard will be available at: http://localhost:8000")
    print("📖 API documentation at: http://localhost:8000/docs")
    print("🔍 Interactive API explorer: http://localhost:8000/redoc")
    print("\n⚡ Hot reload enabled - code changes will automatically restart the server")
    print("🛑 Press Ctrl+C to stop the server\n")
    
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable hot reload for development
        log_level="info"
    )