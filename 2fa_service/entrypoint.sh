#!/bin/sh
# entrypoint.sh

if [ "$1" = "pytest" ]; then
    shift
    exec python -m pytest "$@"
else
    exec uvicorn main:app --host 0.0.0.0 --port 8004
fi

