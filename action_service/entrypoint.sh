#!/bin/sh
# entrypoint.sh for Action Service

if [ "$1" = "pytest" ]; then
    shift
    exec python -m pytest "$@"
else
    exec uvicorn main:app --host 0.0.0.0 --port ${SERVICE_PORT:-8000}
fi

