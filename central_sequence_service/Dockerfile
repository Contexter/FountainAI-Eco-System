# Dockerfile for Central Sequence Service

FROM python:3.9-slim

WORKDIR /app

# Copy the requirements file and install dependencies.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the entire project directory (including main.py and tests/)
COPY . /app

# Ensure the entrypoint script is executable.
RUN chmod +x /app/entrypoint.sh

# Expose the port the application listens on.
EXPOSE 8000

# Set the entrypoint.
ENTRYPOINT ["/app/entrypoint.sh"]
