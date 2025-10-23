"""ASGI entry point for the FXPro Trading Bot application.

This module is the main entry point for uvicorn/gunicorn ASGI servers.
"""

from backend.app.orchestrator.main import create_app

# Create the FastAPI application
app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
