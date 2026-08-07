"""WSGI entry point for Waitress (Windows) and Gunicorn (Linux)."""
from app import create_app

app = create_app()
