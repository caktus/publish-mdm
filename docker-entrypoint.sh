#!/bin/sh
set -e

until psql $DATABASE_URL -c '\l'; do
    >&2 echo "Postgres is unavailable - sleeping"
    sleep 1
done

>&2 echo "Postgres is up - continuing"

if [ "x$DJANGO_MANAGEPY_MIGRATE" = 'xon' ]; then
    python manage.py rename_app odk_publish publish_mdm
    >&2 echo "Running Migrations"
    python manage.py migrate --noinput
fi

exec "$@"
