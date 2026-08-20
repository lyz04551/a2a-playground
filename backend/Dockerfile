FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY backend/requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend ./backend

# Create data directory for persistent storage
RUN mkdir -p /app/data

EXPOSE 8050

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8050", "--log-level", "info"]
