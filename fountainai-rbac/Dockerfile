# Use an official Python runtime as a parent image.
FROM python:3.10-slim

# Set environment variables to prevent .pyc files and enable unbuffered logging.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Ensure that /app is on the PYTHONPATH so that modules like main.py can be imported.
ENV PYTHONPATH=/app

# Set working directory in the container.
WORKDIR /app

# Copy requirements.txt first to leverage Docker cache.
COPY requirements.txt /app/requirements.txt

# Upgrade pip and install dependencies.
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code.
COPY . /app

# Expose the port on which the app will run.
EXPOSE 8001

# Default command to run the application.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
