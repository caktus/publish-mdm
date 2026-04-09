Publish MDM
===========

This guide will walk you through setting up Publish MDM locally with a Postgres database
running on your development machine (or another host accessible from your machine). If you'd
rather use Docker, see :doc:`../running/docker-compose`.

1. Install these applications:

  - `uv <https://docs.astral.sh/uv/getting-started/installation/>`_
  - `direnv <https://direnv.net/docs/installation.html>`_ (and hook it into your shell)

2. Configure your environment by creating a ``.envrc`` file with these contents:

.. code-block:: bash

    # Configure a venv path that won't conflict with the agent sandbox (if any)
    export UV_PROJECT_ENVIRONMENT=.venv-local/

    # set up Python and other requirements using uv
    uv sync --locked

    # add uv's venv to the PATH
    PATH_add .venv-local/bin

    # use Node.js 22
    use node 22

    export DJANGO_SETTINGS_MODULE=config.settings.dev

    # postgres
    export PGHOST=localhost
    export PGPORT=5432
    export PGUSER=$USER
    export PGDATABASE=publish_mdm
    export DATABASE_URL=postgresql://$PGUSER@$PGHOST:$PGPORT/$PGDATABASE

    # google oauth for django-allauth
    export GOOGLE_CLIENT_ID=
    export GOOGLE_CLIENT_SECRET=
    export GOOGLE_API_KEY=
    export GOOGLE_APP_ID=

    # If using TinyMDM as your MDM service provider (the default)
    export TINYMDM_ACCOUNT_ID=
    export TINYMDM_APIKEY_PUBLIC=
    export TINYMDM_APIKEY_SECRET=

    # If using Android EMM as your MDM service provider
    export ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE=
    export ACTIVE_MDM_NAME="Android Enterprise"
    export ACTIVE_MDM_CLASS=apps.mdm.mdms.AndroidEnterprise
    # Optional: needed if you want to enable real-time device enrollment notifications.
    # This is the shared secret token that will be used for the notifications push
    # endpoint at /mdm/api/amapi/notifications/. If you enable notifications and
    # this is not set, all requests to the endpoint will be rejected.
    # You can generate it with `pwgen -s 32 1`
    export ANDROID_ENTERPRISE_PUBSUB_TOKEN=
    # Optional domain (no scheme, no trailing slash, e.g. "myapp.example.com") used to build
    # the Android Enterprise enrollment callback URL over HTTPS. When set, it replaces the host
    # derived from the incoming request, which is useful for local development where the request
    # host is "localhost" and Google's API rejects it.
    export ANDROID_ENTERPRISE_CALLBACK_DOMAIN=

Update the environment variables as needed for your local setup. You may need to
add a ``PGPASSWORD`` variable if your database expects a password. If the database
does not exist yet, create it with the ``createdb`` `command <https://www.postgresql.org/docs/current/app-createdb.html>`_.

See :doc:`the tutorial <../running/tutorial>` for more details on the Google and ODK Central variables.

3. Install the required dependencies.

.. code-block:: bash

    direnv allow
    npm install


4. Setup the database.

.. code-block:: bash

    python manage.py migrate

5. Run the development server and :doc:`./dagster`.

.. code-block:: bash

    # in one terminal
    npm run dev
    # in another terminal
    python manage.py runserver
    # in another terminal
    dagster dev

6. Set up sample data. Log in with Google first so that your user is added to the sample Organization that will be created.

.. code-block:: bash

    python manage.py populate_sample_odk_data

7. If you are using Android EMM and would like to configure real-time device enrollment notifications, run the following command:

.. code-block:: bash

    python manage.py configure_amapi_pubsub

This will create the Pub/Sub topic ``projects/{project_id}/topics/publish-mdm-{environment}`` and
subscription ``projects/{project_id}/subscriptions/publish-mdm-{environment}`` (where ``{environment}``
is the value of the ``ENVIRONMENT`` setting), grant Android Device Policy the publisher role on the
topic, and configure the push endpoint at ``/mdm/api/amapi/notifications/``.
Before running this, the Pub/Sub API must be enabled for the Google project used to create the service
account, and the service account must have the "Pub/Sub Admin" role. See `this guide <https://docs.cloud.google.com/pubsub/docs/publish-receive-messages-console#before-you-begin>`__ for more details.
Only complete the steps under 'Before you begin' -- the ``configure_amapi_pubsub`` command will create the topic and subscription.

By default, the notification endpoint will be set up using the domain of the current ``Site`` model object. If you need to set up the notification endpoint with a different domain (e.g. to use ngrok to expose your localhost) run:

.. code-block:: bash

    python manage.py configure_amapi_pubsub --push-endpoint-domain <domain>
