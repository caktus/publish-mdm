<!-- omit in toc -->

# ODK Publish

<div align="center" style="margin-bottom:20px">
  <a target="_blank" href="https://github.com/caktus/odk-publish/blob/main/LICENSE" style="background:none">
    <img src="https://img.shields.io/badge/License-MIT-blue.svg?label=license">
  </a>
  <a target="_blank" href="https://github.com/caktus/odk-publish/actions/workflows/tests.yaml" style="background:none">
    <img src="https://github.com/caktus/odk-publish/actions/workflows/tests.yaml/badge.svg?branch=main">
  </a>
  <a target="_blank" href="https://github.com/caktus/odk-publish/actions/workflows/docker-publish.yml" style="background:none">
    <img src="https://github.com/caktus/odk-publish/actions/workflows/docker-publish.yml/badge.svg?branch=main">
  </a>
  <a target="_blank" href="https://odk-publish.readthedocs.io/" style="background:none">
    <img src="https://img.shields.io/readthedocs/odk-publish?logo=read-the-docs&logoColor=white">
  </a>
</div>

This repository contains the proof-of-concept ODK Publish project.

## Development

1. Configure your environment:

   ```sh
   layout python python3.12
   use node 22

   export DJANGO_SETTINGS_MODULE=config.settings.dev

   # postgres
   export PGHOST=localhost
   export PGPORT=5432
   export PGUSER=$USER
   export PGDATABASE=odk_publish
   export DATABASE_URL=postgresql://$PGUSER@$PGHOST:$PGPORT/$PGDATABASE
   export DATABASE_URL_SQLALCHEMY=postgresql+psycopg://$PGUSER@$PGHOST:$PGPORT/$PGDATABASE

   # google oauth for django-allauth
   export GOOGLE_CLIENT_ID=
   export GOOGLE_CLIENT_SECRET=

   # odk central
   export ODK_CENTRAL_USERNAME=
   export ODK_CENTRAL_PASSWORD=
   ```

2. Install the required dependencies.

   ```sh
   make setup
   npm install
   ```

3. Setup the database.

   ```sh
   python manage.py migrate
   python manage.py populate_sample_odk_data
   ```

4. Run the development server.

   ```sh
   # in one terminal
   npm run dev
   # in another terminal
   python manage.py runserver
   ```
