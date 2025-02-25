ODK Central
===========

This guide will walk you through setting up ODK Central locally using Docker
Compose for development purposes with ODK Publish. This guide is not intended
for production use. For production deployments, see the official `Installing ODK
Central <https://docs.getodk.org/central-install/>`_ guide.


Prerequisites
-------------

- `Docker <https://docs.docker.com/get-docker/>`_ and `Docker Compose <https://docs.docker.com/compose/install/>`_
- `git <https://git-scm.com/downloads>`_
- `PostgreSQL <https://www.postgresql.org/download/>`_ (optional, to use a shared database cluster with ODK Publish)


Setup
-----

1. Create a `central` PostgreSQL database in your local PostgreSQL instance:

.. code-block:: bash

    dropdb --if-exists central && createdb central

2. Start the ODK Central services:

.. code-block:: bash

    cd services/
    docker-compose up -d

3. Create an admin user:

.. code-block:: bash

    # Create a new account
    docker-compose exec service odk-cmd --email YOUREMAIL@ADDRESSHERE.com user-create
    # Make the new account an administrator
    docker compose exec service odk-cmd --email YOUREMAIL@ADDRESSHERE.com user-promote
