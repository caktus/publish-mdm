#!/bin/sh
set -x

if [ "$USE_GUNICORN" ]; then
    newrelic-admin run-program gunicorn config.wsgi --bind 0.0.0.0 --config python:config.gunicorn
else
    newrelic-admin run-program daphne config.asgi:application --bind 0.0.0.0 --port 8000
fi
