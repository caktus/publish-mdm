Quickstart with Docker
======================

This guide will walk you through setting up ODK Publish locally using Docker
Compose.


Prerequisites
-------------

- `Docker <https://docs.docker.com/get-docker/>`_ and `Docker Compose <https://docs.docker.com/compose/install/>`_
- Credentials to access an ODK Central server, such as `ODK Cloud <https://getodk.org/>`_
- A Google Cloud Platform project with the `Google Sheets API <https://console.developers.google.com/apis/library/sheets.googleapis.com>`_ enabled


Google OAuth Client ID
~~~~~~~~~~~~~~~~~~~~~~

ODK Publish accesses spreadsheets on behalf of an end user, so you will need to
create a Google OAuth client ID to authenticate users. To create a new OAuth
client ID, follow the steps below:

1. Follow `For End Users: Using OAuth Client ID
   <https://docs.gspread.org/en/latest/oauth2.html#for-end-users-using-oauth-client-id>`_
   from the gspread documentation to create a new OAuth client ID.
2. Save the client ID and client secret for the next step.


Setup
-----

1. Create a new directory for the project and navigate to it:

.. code-block:: bash

   mkdir odk-publish
   cd odk-publish


2. Create a new file named ``docker-compose.yml`` and paste the following
   content:

.. code-block:: yaml

  services:
    app:
      image: ghcr.io/caktus/odk-publish:main
      command: daphne config.asgi:application -b 0.0.0.0 -p 8000
      env_file:
        - .env
      ports:
        - "8000:8000"
      depends_on:
        - db

    db:
      image: postgres:15-alpine
      environment:
        POSTGRES_DB: odk_publish
        POSTGRES_HOST_AUTH_METHOD: trust
      ports:
        - 5432
      volumes:
        - dev_pgdata:/var/lib/postgresql/data

  volumes:
    dev_pgdata:

3. Create a new file named ``.env`` and paste the following content:

.. code-block:: shell

  DJANGO_SETTINGS_MODULE="config.settings.deploy"
  DATABASE_URL="postgresql://postgres@db/odk_publish"
  DJANGO_SECRET_KEY="django-insecure-CHANGEME"
  SESSION_COOKIE_SECURE="False"
  DJANGO_SECURE_SSL_REDIRECT="False"
  DJANGO_MANAGEPY_MIGRATE="on"

  # google oauth for django-allauth
  GOOGLE_CLIENT_ID="your-client-id-from-above"
  GOOGLE_CLIENT_SECRET="your-client-secret-from-above"

  # odk central
  ODK_CENTRAL_CREDENTIALS="base_url=https://myserver.com;username=user1;password=pass1"

4. Run the following command to start the application and login:

.. code-block:: bash

   docker compose up

Visit http://localhost:8000 in your browser and log in with your Google account.

5. After logging in, make yourself a superuser by running the following command:

.. code-block:: bash

   docker compose exec app python manage.py shell -c "from apps.users.models import User; User.objects.all().update(is_staff=True, is_superuser=True)"


Local development
-----------------


Build development image locally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To build the development image locally, run the following command:

.. code-block:: bash

   docker build -t odk-publish:latest --target deploy -f Dockerfile .

This will build the image with the tag ``odk-publish:latest``, which you can use
in your ``docker-compose.yml`` file.
