# Dockerfile for Core Script Management API

FROM python:3.9-slim

WORKDIR /app

# Add /app to PYTHONPATH so our modules are found.
ENV PYTHONPATH=/app

# Copy requirements and install dependencies.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project.
COPY . /app

# Ensure the entrypoint script is executable.
RUN chmod +x /app/entrypoint.sh

# Expose the application port.
EXPOSE 8000

# Set the entrypoint.
ENTRYPOINT ["/app/entrypoint.sh"]
