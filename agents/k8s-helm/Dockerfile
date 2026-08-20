FROM python:3.11-slim
WORKDIR /app
COPY agents/shared-runtime /app/shared-runtime
COPY agents/k8s-helm /app/agent
RUN pip install --no-cache-dir /app/shared-runtime python-dotenv uvicorn
WORKDIR /app/agent
CMD ["python", "main.py"]
