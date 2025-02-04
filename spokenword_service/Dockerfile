# Dockerfile for Spoken Word Service

FROM python:3.9-slim

WORKDIR /app
ENV PYTHONPATH=/app

# Copy and install dependencies.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all project files.
COPY . /app

# Make sure the entrypoint script is executable.
RUN chmod +x /app/entrypoint.sh

# Expose the internal port.
EXPOSE 8000

# Set the entrypoint.
ENTRYPOINT ["/app/entrypoint.sh"]

