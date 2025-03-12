ODK Central
===========

This guide will walk you through setting up ODK Central locally using Docker
Compose for development purposes with ODK Publish. This is not intended for
production use. For production deployments, see the official `Installing ODK
Central <https://docs.getodk.org/central-install/>`_ guide.

.. note::

    The compose file in this guide uses forked images of ODK Central services to
    support overriding the default configuration with environment variables. The
    images are hosted on `Caktus Group's GitHub Container Registry`_ and
    are built from the `caktus/central`_ repository.

.. _Caktus Group's GitHub Container Registry: https://github.com/orgs/caktus/packages
.. _caktus/central: https://github.com/caktus/central


Prerequisites
-------------

- `Docker <https://docs.docker.com/get-docker/>`_ and `Docker Compose <https://docs.docker.com/compose/install/>`_
- `PostgreSQL <https://www.postgresql.org/download/>`_ (to use a shared database cluster with ODK Publish)
- `ngrok <https://ngrok.com/download>`_ or `Tailscale <https://tailscale.com/download>`_ (for tunneling connections from ODK Collect to your ODK Central instance)


Tunnel
------

ODK Collect requires a valid HTTPS certificate to connect to ODK Central. To
create a secure tunnel to your local services, you can use a tunneling service
like `ngrok` or `Tailscale`.


ngrok
~~~~~

1. Install ngrok and connect your ngrok agent to your ngrok account following
   the `Getting Started <https://ngrok.com/docs/getting-started/>`_ guide.

2. Create a static subdomain for your ngrok account.

   Make a note of the HTTPS URL ngrok provides. You will need this to configure
   ODK Collect to connect to your local ODK Central instance.

3. Start a tunnel to your local ODK Central instance:

.. code-block:: bash

    ngrok http 9100 --url https://<your-static-subdomain>.ngrok-free.app


Setup
-----

1. Create a ``central`` database in your local PostgreSQL instance:

.. code-block:: bash

    dropdb --if-exists central && createdb central

.. note::

    If you're on Linux, you may need to update the PostgreSQL configuration to
    allow connections from the Docker network. Here's how you can do that on
    a fresh PostgreSQL 17 installation:

    .. code-block:: bash

        sudo -u postgres psql -c "ALTER SYSTEM SET listen_addresses TO '*';"
        sudo -u postgres createuser --superuser <your-username>
        sudo -u postgres psql -c "ALTER USER <your-username> WITH PASSWORD '<your-password>';"
        sudo -u postgres sh -c "echo 'host    all             all             0.0.0.0/0               md5' >> /etc/postgresql/17/main/pg_hba.conf"
        sudo systemctl restart postgresql

    Then you can start the services with the following command:

    .. code-block:: bash

        DOMAIN=<your-tunnel-fqdn> DB_HOST=172.17.0.1 DB_PASSWORD=<your-pass> docker compose up -d

    Or you can set the environment variables in a `.env` file.

2. Start the ODK Central services:

.. code-block:: bash

    cd services/
    DOMAIN=<your-tunnel-fqdn> docker-compose up -d

3. Create an admin user:

.. code-block:: bash

    # Create a new account
    docker compose exec service odk-cmd --email YOUREMAIL@ADDRESSHERE.com user-create
    # Make the new account an administrator
    docker compose exec service odk-cmd --email YOUREMAIL@ADDRESSHERE.com user-promote

4. Access the ODK Central web interface at https://<your-tunnel-fqdn>
   and log in with the admin user you created.

5. Finally, when you configure ODK Publish, set the ``ODK_CENTRAL_CREDENTIALS``
   environment variable to use ``base_url=https://<your-tunnel-fqdn>``.
