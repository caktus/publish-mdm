#!/bin/sh

if [ "$ENV_VARS_FILE" ] && [ -f "$ENV_VARS_FILE" ] && [ -s "$ENV_VARS_FILE" ]; then
    # If set, ENV_VARS_FILE should be the path to a file that contains environment variables
    # in the `key=value` format.
    echo "Adding environment variables from $ENV_VARS_FILE ..."
    export $(cat $ENV_VARS_FILE | xargs)
fi

if [ -z "$INFISICAL_TOKEN" ] && [ "$INFISICAL_CLIENT_ID" ] && [ "$INFISICAL_CLIENT_SECRET" ]; then
    echo "Generating an Infisical access token ..."
    export INFISICAL_TOKEN=$(infisical login --method=universal-auth --client-id=$INFISICAL_CLIENT_ID --client-secret=$INFISICAL_CLIENT_SECRET --silent --plain)
fi

set -x

if [ "$USE_GUNICORN" ]; then
    newrelic-admin run-program gunicorn config.wsgi --bind 0.0.0.0 --config python:config.gunicorn
else
    newrelic-admin run-program daphne config.asgi:application --bind 0.0.0.0 --port 8000
fi
