# Dockerfile

# Use an official Python runtime as a parent image.
FROM python:3.10-slim

# Set environment variables.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Set the working directory.
WORKDIR /app

# Copy requirements.txt to leverage Docker cache.
COPY requirements.txt /app/requirements.txt

# Upgrade pip and install dependencies.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the code.
COPY . /app

# Copy the entrypoint script.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expose the application port.
EXPOSE 8003

# Set the entrypoint.
ENTRYPOINT ["/app/entrypoint.sh"]


