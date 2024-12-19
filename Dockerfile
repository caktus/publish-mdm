FROM node:18-bookworm-slim as static_files

WORKDIR /code
ENV PATH /code/node_modules/.bin:$PATH
COPY package.json package-lock.json tailwind.config.js postcss.config.js /code/
RUN npm install --silent
COPY config/assets config/assets
COPY config/static config/static
# Every template dir using Tailwind must be added below
COPY apps/eportal/templates apps/eportal/templates
COPY apps/inventory/templates apps/inventory/templates
COPY apps/inventory_materials/templates apps/inventory_materials/templates
COPY apps/portal_patterns/templates apps/portal_patterns/templates
RUN npm run build

FROM python:3.11-slim-bookworm as base

# Install packages needed to run your application (not build deps):
#   mime-support -- for mime types when serving static files
#   postgresql-client -- matches RDS version, for running database commands
# We need to recreate the /usr/share/man/man{1..8} directories first because
# they were clobbered by a parent image.
ENV POSTGRESQL_CLIENT_VERSION="15"
RUN set -ex \
    && RUN_DEPS=" \
    mime-support \
    postgresql-client-${POSTGRESQL_CLIENT_VERSION}  \
    vim \
    curl \
    " \
    && seq 1 8 | xargs -I{} mkdir -p /usr/share/man/man{} \
    && apt-get update \
    && apt-get -y install wget gnupg2 lsb-release \
    # PostgreSQL
    && sh -c 'echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list' \
    && wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add - \
    && apt-get update \
    && apt-get install -y --no-install-recommends $RUN_DEPS \
    && rm -rf /var/lib/apt/lists/*

ADD requirements /requirements

# Install build deps, then run `pip install`, then remove unneeded build deps all in a single step.
# Correct the path to your production requirements file, if needed.
RUN set -ex \
    && BUILD_DEPS=" \
    build-essential \
    git-core \
    libpq-dev \
    " \
    && apt-get update && apt-get install -y --no-install-recommends $BUILD_DEPS \
    && pip install -U -q pip-tools \
    && pip-sync --pip-args="--no-cache-dir" requirements/base/base.txt \
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false $BUILD_DEPS \
    && rm -rf /var/lib/apt/lists/*

# Copy your application code to the container (make sure you create a .dockerignore file if any large files or directories should be excluded)
RUN mkdir /code/
WORKDIR /code/
ADD . /code/

COPY --from=static_files /code/config/static /code/config/static

FROM base AS deploy

# Create a group and user to run our app
ARG APP_USER=appuser
RUN groupadd -r ${APP_USER} && useradd --no-log-init -r -g ${APP_USER} ${APP_USER}

# uWSGI will listen on this port
EXPOSE 8000

# Add any static environment variables needed by Django or your settings file here:
ENV DJANGO_SETTINGS_MODULE=config.settings.deploy

# Call collectstatic (customize the following line with the minimal environment variables needed for manage.py to run):
RUN DATABASE_URL='' ENVIRONMENT='' DJANGO_SECRET_KEY='dummy' DOMAIN='' python manage.py collectstatic --noinput -c

ENV GUNICORN_CMD_ARGS="--workers=4"

# Change to a non-root user
USER ${APP_USER}:${APP_USER}

# Uncomment after creating your docker-entrypoint.sh
ENTRYPOINT ["/code/docker-entrypoint.sh"]

# Start uWSGI
CMD ["newrelic-admin", "run-program", "gunicorn", "config.wsgi", "--bind", "0.0.0.0", "--config", "python:config.gunicorn"]
