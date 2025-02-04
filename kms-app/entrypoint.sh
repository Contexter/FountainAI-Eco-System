#!/bin/sh
# If the first argument is "pytest", then run tests using "python -m pytest"
if [ "$1" = "pytest" ]; then
    shift
    exec python -m pytest "$@"
else
    exec uvicorn main:app --host 0.0.0.0 --port 8002
fi
