#!/bin/bash
# docker_log_review.sh - Automate the review of Docker logs for FountainAI services (excluding api_gateway).

# List of container names as defined in your docker-compose file (api_gateway removed).
containers=(
  "2fa_service"
  "action_service"
  "central_gateway"
  "central_sequence_service"
  "character_service"
  "core_script_management_service"
  "fountainai-rbac"
  "kms-app"
  "notification-service"
  "paraphrase_service"
  "performer_service"
  "session_context_service"
  "spokenword_service"
  "story_factory_service"
  "typesense_client_service"
)

echo "Starting Docker Log Review for FountainAI services..."
echo "--------------------------------------------------------"

for container in "${containers[@]}"; do
    echo "Reviewing logs for container: $container"
    echo "--------------------------------------------------------"
    
    # Check if the container is currently running.
    if docker ps --format '{{.Names}}' | grep -q "^${container}\$"; then
        echo "Container $container is running. Fetching logs..."
        # Fetch the last 50 lines and filter for errors, warnings, or failures.
        docker logs --tail 50 "$container" | grep -iE "error|fail|warn" || echo "No errors or warnings found in the last 50 lines."
    else
        echo "Container $container is not running."
    fi
    
    echo "--------------------------------------------------------"
done

echo "Docker Log Review completed."

