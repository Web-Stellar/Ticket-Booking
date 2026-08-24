import uvicorn
import os

if __name__ == "__main__":
    print("=" * 60)
    print("🚀 LAUNCHING TICKET BOOKING SYSTEM PLATFORM")
    print("=" * 60)
    print("Server running at: http://localhost:8000")
    print("Press Ctrl+C to stop the server.")
    print("=" * 60)
    
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
