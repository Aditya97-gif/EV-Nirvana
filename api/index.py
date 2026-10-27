"""
Vercel serverless entry point — wraps the FastAPI app with Mangum (ASGI adapter).
"""
import sys
import os

# Add the api/ directory to the Python path so routers/db/etc. are importable
sys.path.insert(0, os.path.dirname(__file__))

from mangum import Mangum
from main import app  # noqa: E402

# Vercel calls `handler` for each request
handler = Mangum(app, lifespan="off")
