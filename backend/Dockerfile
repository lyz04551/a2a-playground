FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install google-adk first (it pins langgraph to old version)
RUN pip install --no-cache-dir "google-adk[extensions]>=2.4.0" 2>/dev/null || true

# Then install core deps (langgraph>=1.2.9 will override google-adk's old langgraph)
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create data directory for persistent storage
RUN mkdir -p /app/data

EXPOSE 8050

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050", "--log-level", "info"]
