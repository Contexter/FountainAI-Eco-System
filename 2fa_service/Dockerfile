# Dockerfile for FountainAI 2FA Service

FROM python:3.10-slim

# Set environment variables.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set the working directory.
WORKDIR /app

# Copy requirements.txt and install dependencies.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application.
COPY . /app

# Copy and set the entrypoint script.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose port 8004.
EXPOSE 8004

# Set the entrypoint to our script.
ENTRYPOINT ["/app/entrypoint.sh"]
