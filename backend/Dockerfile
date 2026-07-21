FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install a2a-sdk (locked to 0.3.25 for compatibility)
RUN pip install --no-cache-dir "a2a-sdk==0.3.25"

# Install LangGraph dependencies (optional)
RUN pip install --no-cache-dir langgraph langchain-openai langchain-core 2>/dev/null || true

# Install google-adk (optional)
RUN pip install --no-cache-dir google-adk 2>/dev/null || true

# Copy application code
COPY . .

# Create data directory for persistent storage
RUN mkdir -p /app/data

EXPOSE 8050

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8050", "--log-level", "info"]
