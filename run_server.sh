#!/bin/sh

if [ "$USE_GUNICORN" ]; then
    alias run_server="newrelic-admin run-program gunicorn config.wsgi --bind 0.0.0.0 --config python:config.gunicorn"
else
    alias run_server="newrelic-admin run-program daphne config.asgi:application --bind 0.0.0.0 --port 8000"
fi

if [ "$INFISICAL_SECRETS_FILE" ]; then
    echo "Adding Infisical secrets to the environment..."
    export $(cat $INFISICAL_SECRETS_FILE | xargs)
fi

set -x

if [ "$USE_INFISICAL_RUN" ]; then
    # Run the application with `infisical run`, which will inject secrets into
    # the application process as environment variables.
    # See:
    # - https://infisical.com/docs/cli/usage#staging-production-and-all-other-use-cases
    # - https://infisical.com/docs/integrations/platforms/docker
    # - https://infisical.com/docs/cli/commands/run
    infisical run --projectId $INFISICAL_SECRETS_PROJECT_ID --env $INFISICAL_SECRETS_ENV --silent -- run_server
else
    run_server
fi
