FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the A2A agent port
EXPOSE 8051

# Run the A2A server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8051"]
