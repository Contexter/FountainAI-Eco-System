# Dockerfile for FountainAI Compose Manager Utility App

FROM python:3.9-slim

WORKDIR /app

# Copy the requirements file and install dependencies.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the utility application script.
COPY compose_manager.py /app/compose_manager.py

# Set the default command to run the utility.
ENTRYPOINT ["python", "compose_manager.py"]
