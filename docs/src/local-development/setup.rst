Publish MDM
===========

This guide will walk you through setting up Publish MDM locally with a Postgres database
running on your development machine (or another host accessible from your machine). If you'd
rather use Docker, see :doc:`/src/docker-compose`.

1. Install `direnv <https://direnv.net/docs/installation.html>`_ and hook it into your shell.

2. Configure your environment by creating a ``.envrc`` file with these contents:

.. code-block:: bash

    # use Python 3.12
    layout python python3.12

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

Update the environment variables as needed for your local setup. You may need to
add a ``PGPASSWORD`` variable if your database expects a password. If the database
does not exist yet, create it with the ``createdb`` `command <https://www.postgresql.org/docs/current/app-createdb.html>`_.

See :doc:`the tutorial </src/tutorial>` for more details on the Google and ODK Central variables.

3. Install the required dependencies.

.. code-block:: bash

    direnv allow
    make setup
    npm install


4. Setup the database.

.. code-block:: bash

    python manage.py migrate

5. Run the development server.

.. code-block:: bash

    # in one terminal
    npm run dev
    # in another terminal
    python manage.py runserver

6. Set up sample data. Log in with Google first so that your user is added to the sample Organization that will be created.

.. code-block:: bash

    python manage.py populate_sample_odk_data
