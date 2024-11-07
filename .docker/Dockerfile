# Dockerfile
FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY .docker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Run the application
CMD ["python", "main.py"]