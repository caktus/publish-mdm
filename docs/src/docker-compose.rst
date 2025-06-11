Quickstart with Docker
======================

This guide will walk you through setting up Publish MDM locally using Docker
Compose.


Prerequisites
-------------

- `Docker <https://docs.docker.com/get-docker/>`_ and `Docker Compose <https://docs.docker.com/compose/install/>`_
- Credentials to access an ODK Central server, such as `ODK Cloud <https://getodk.org/>`_
- A Google Cloud Platform project with the `Google Drive <https://console.developers.google.com/apis/library/drive.googleapis.com>`_
  and `Google Picker <https://console.developers.google.com/apis/library/picker.googleapis.com>`_ APIs enabled.


Google OAuth Client ID
~~~~~~~~~~~~~~~~~~~~~~

Publish MDM accesses spreadsheets on behalf of an end user, so you will need to
create a Google OAuth client ID to authenticate users. To create a new OAuth
client ID, follow the steps below:

1. Follow `For End Users: Using OAuth Client ID
   <https://docs.gspread.org/en/latest/oauth2.html#for-end-users-using-oauth-client-id>`_
   from the gspread documentation to create a new OAuth client ID.
2. Save the client ID and client secret for the next step.

We use the ``https://www.googleapis.com/auth/drive.file`` Google Oauth scope, which
allows users to only give access to specific files in their Google account.
The scope is configured in the ``SOCIALACCOUNT_PROVIDERS`` Django setting.
When adding or editing a form template, a user can select the spreadsheet for that template using
the `Google Picker <https://developers.google.com/drive/picker/guides/overview>`_.


Google API Key
~~~~~~~~~~~~~~

`Create an API key <https://developers.google.com/drive/picker/guides/overview#api-key>`_
and save it for the next step. We need this to use the Google Picker API.


Google App ID
~~~~~~~~~~~~~
Go to your `Google Cloud dashboard <https://console.cloud.google.com/home/dashboard>`_
and save the "Project number" for the next step. We need this to use the Google Picker API.


Setup
-----

A ``docker-compose.yaml`` file exists in the codebase that sets up a PostgreSQL
database and `Infisical <https://infisical.com/>`_, which is used for secrets management.

1. Create a new directory for the project and navigate to it:

.. code-block:: bash

   mkdir publish-mdm
   cd publish-mdm


2. Create a new file named ``docker-compose.yml`` and paste the following
   content:

.. code-block:: yaml

  include:
    - ../docker-compose.yaml

  services:
    app:
      image: ghcr.io/caktus/publish-mdm:main
      command: daphne config.asgi:application -b 0.0.0.0 -p 8000
      env_file:
        - .env
      ports:
        - "8000:8000"
      depends_on:
        infisical:
          condition: service_healthy
        db:
          condition: service_started

  volumes:
    dev_pgdata:

3. Create a new file named ``.env`` and paste the following content.
If you do not have values for the ``INFISICAL_*`` variables yet, you will update them later (in step 6 below).

.. code-block:: shell

  DJANGO_SETTINGS_MODULE="config.settings.deploy"
  DATABASE_URL="postgresql://postgres@db/publish_mdm"
  DJANGO_SECRET_KEY="django-insecure-CHANGEME"
  SESSION_COOKIE_SECURE="False"
  DJANGO_SECURE_SSL_REDIRECT="False"
  DJANGO_MANAGEPY_MIGRATE="on"

  # google oauth for django-allauth
  GOOGLE_CLIENT_ID="your-client-id-from-above"
  GOOGLE_CLIENT_SECRET="your-client-secret-from-above"
  GOOGLE_API_KEY="your-api-key-from-above"
  GOOGLE_APP_ID="your-app-id-from-above"

  # Infisical
  INFISICAL_API_URL=http://localhost:8888
  INFISICAL_TOKEN="your-infisical-access-token"
  INFISICAL_KMS_PROJECT_ID="your-infisical-kms-project-id"
  # Set these if you're going to use Infisical to inject secrets as environment variables
  INFISICAL_SECRETS_PROJECT_ID="your-infisical-secrets-project-id"
  INFISICAL_SECRETS_ENV="your-infisical-secrets-environment-slug"

4. Run the following command to start the application and login:

.. code-block:: bash

   docker compose up

Visit http://localhost:8000 in your browser and log in with your Google account.

5. After logging in, make yourself a superuser by running the following command:

.. code-block:: bash

   docker compose exec app python manage.py shell -c "from apps.users.models import User; User.objects.all().update(is_staff=True, is_superuser=True)"

6. Infisical should be running at http://localhost:8888. You can now
:ref:`set up a KMS project and an access token <infisical:setup>`. If you want
``infisical run`` to inject secrets as environment variables, you'll also need to:

- :ref:`set up a Secrets project <infisical:setup_secrets>` and add your secrets to it.
- Update the ``docker-compose.yml`` file to change the command for the ``app`` service
  to ``infisical run --projectId $INFISICAL_SECRETS_PROJECT_ID --env $INFISICAL_SECRETS_ENV --silent -- daphne config.asgi:application -b 0.0.0.0 -p 8000``.
  For further details on ``infisical run``, see `Infisical's docs <https://infisical.com/docs/cli/commands/run>`_.

Update the ``INFISICAL_*`` variables in the ``.env`` file, then re-run step 4.

Local development
-----------------


Build development image locally
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To build the development image locally, run the following command:

.. code-block:: bash

   docker build -t publish-mdm:latest --target deploy -f Dockerfile .

This will build the image with the tag ``publish-mdm:latest``, which you can use
in your ``docker-compose.yml`` file.
