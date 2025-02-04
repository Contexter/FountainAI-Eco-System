#!/bin/bash
# check_health.sh - Script to verify health endpoints for the FountainAI ecosystem services
# This version uses parallel arrays for compatibility with Bash 3.2 (default on macOS).

# List of service names (as defined in your docker-compose file)
services=( "2fa_service" "action_service" "api_gateway" "central_gateway" "central_sequence_service" "character_service" "core_script_management_service" "fountainai-rbac" "kms-app" "notification-service" "paraphrase_service" "performer_service" "session_context_service" "spokenword_service" "story_factory_service" "typesense_client_service" )

# Corresponding published ports for each service
ports=( "9000" "9001" "9002" "9003" "9004" "9005" "9007" "9008" "9009" "9010" "9011" "9012" "9013" "9014" "9015" "9016" )

echo "Starting health checks for FountainAI ecosystem services..."
echo "--------------------------------------------------------------"

# Loop over indices in the arrays
for (( i=0; i<${#services[@]}; i++ )); do
    service="${services[$i]}"
    port="${ports[$i]}"
    url="http://localhost:${port}/health"
    echo -n "Checking ${service} at ${url}... "
    # Curl the URL, capture only the HTTP status code.
    http_code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    if [ "$http_code" == "200" ]; then
        echo "Healthy (HTTP 200)"
    else
        echo "Unhealthy (HTTP $http_code)"
    fi
done

echo "--------------------------------------------------------------"
echo "Health check completed."
