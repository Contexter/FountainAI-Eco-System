#!/bin/bash
set -e

echo "Resetting Docker environment..."

# Stop all running containers (if any)
containers=$(docker ps -q)
if [ -n "$containers" ]; then
  echo "Stopping containers..."
  docker stop $containers
fi

# Remove all containers
containers=$(docker ps -aq)
if [ -n "$containers" ]; then
  echo "Removing containers..."
  docker rm -f $containers
fi

# Remove all images
images=$(docker images -q)
if [ -n "$images" ]; then
  echo "Removing images..."
  docker rmi -f $images
fi

# Remove all volumes
volumes=$(docker volume ls -q)
if [ -n "$volumes" ]; then
  echo "Removing volumes..."
  docker volume rm $volumes
fi

# Prune unused networks (won't remove default networks)
echo "Pruning networks..."
docker network prune -f

echo "Docker environment has been reset."

# Optional: Wait a moment to ensure Docker has cleaned up
sleep 3

# Rebuild and start the FountainAI eco-system using docker-compose
# Assumes docker-compose.yml is in the same directory as this script.
echo "Starting the FountainAI eco-system with docker-compose..."
docker-compose up --build

