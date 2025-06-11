#!/bin/sh

if [ "$ENV_VARS_FILE" ] && [ -f "$ENV_VARS_FILE" ] && [ -s "$ENV_VARS_FILE" ]; then
    # If set, ENV_VARS_FILE should be the path to a file that contains environment variables
    # in the `key=value` format.
    echo "Adding environment variables from $ENV_VARS_FILE ..."
    export $(cat $ENV_VARS_FILE | xargs)
fi

set -x

if [ "$USE_GUNICORN" ]; then
    newrelic-admin run-program gunicorn config.wsgi --bind 0.0.0.0 --config python:config.gunicorn
else
    newrelic-admin run-program daphne config.asgi:application --bind 0.0.0.0 --port 8000
fi
