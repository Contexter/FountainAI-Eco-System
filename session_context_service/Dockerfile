# Dockerfile for Session and Context Management API

FROM python:3.9-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Copy and install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . /app

# Ensure the entrypoint script is executable
RUN chmod +x /app/entrypoint.sh

# Expose the service port (container’s internal port)
EXPOSE 8000

# Set the entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]
