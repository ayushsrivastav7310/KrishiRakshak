"""ASGI entry point: uvicorn main:app --reload (run from this folder)."""
from app.api import create_app

app = create_app()
