Dagster
=======


Dagster Overview
----------------

`Dagster`_, an orchestration platform for managing data pipelines (DAGs), automates
Tailscale and TinyMDM workflows in this project, ensuring efficient and reliable
task execution.

Integrating Dagster with Django allows access to Django's ORM, settings, and
management commands within pipelines. This exploratory feature aims to simplify
tasks like database interactions by leveraging Django for schema management and
maintaining consistency between application and data workflows.

For production, Dagster is deployed in a Kubernetes environment, but it can also
be run locally for development and testing.

.. _Dagster: https://dagster.io/


Running the Development Server
------------------------------

Set the following environment variables in your shell before running the Dagster
development server:

.. code-block:: bash

    # sample .envrc file
    # tinymdm
    export TINYMDM_ACCOUNT_ID=
    export TINYMDM_APIKEY_PUBLIC=
    export TINYMDM_APIKEY_SECRET=
    # tailscale
    export TAILSCALE_API_KEY=
    export TAILSCALE_TAILNET=


To run the Dagster development server locally, just run the following command:

.. code-block:: bash

    dagster dev

This command starts the Dagster web server, which provides a user interface for
monitoring and managing your pipelines. You can access the web server at
http://localhost:3000 in your web browser.
