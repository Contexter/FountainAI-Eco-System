#!/bin/sh
# entrypoint.sh for FountainAI API Gateway

if [ "$1" = "pytest" ]; then
    shift
    exec python -m pytest "$@"
else
    exec uvicorn main:app --host 0.0.0.0 --port ${GATEWAY_PORT:-8000}
fi

