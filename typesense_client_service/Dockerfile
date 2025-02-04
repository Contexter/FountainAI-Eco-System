# Dockerfile for Typesense Client Microservice

FROM python:3.10-slim

# Prevent .pyc files and enable unbuffered output.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Copy the dependency file and install dependencies.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire application code.
COPY . /app

# Copy the entrypoint script and set permissions.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose the internal port (the app listens on 8001).
EXPOSE 8001

# Set the entrypoint.
ENTRYPOINT ["/app/entrypoint.sh"]

