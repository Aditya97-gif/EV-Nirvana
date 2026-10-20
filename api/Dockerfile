FROM python:3.11-slim

WORKDIR /app

# System deps for geopandas / shapely / rasterio / psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgeos-dev \
    libproj-dev \
    libgdal-dev \
    libpq-dev \
    gdal-bin \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip + setuptools first to avoid pkg_resources / build-backend failures
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

COPY requirements.txt .
# --prefer-binary: always use pre-built wheels to avoid source-compile failures
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
