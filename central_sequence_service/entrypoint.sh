#!/bin/sh
# entrypoint.sh for Central Sequence Service

if [ "$1" = "pytest" ]; then
    shift
    exec python -m pytest "$@"
else
    exec uvicorn main:app --host 0.0.0.0 --port 8000
fi
