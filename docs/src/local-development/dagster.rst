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

To run the Dagster development server locally, just run the following command:

.. code-block:: bash

    dagster dev

This command starts the Dagster web server, which provides a user interface for
monitoring and managing the pipelines. You can access the web server at
http://localhost:3000 in your web browser.


Tailscale
---------

Tailscale integration maintains a list of devices and metadata, including device
names, IP addresses, and last seen timestamps. `Tailscale OAuth clients`_ allow
fine-grained control on the access granted to the client using scopes, unlike a
fully-permitted access token which grants full access to the Tailscale API.

To configure Tailscale OAuth, follow the `Setting up an OAuth client`_ guide to
create a new client with the ``devices:core:read`` scope, and then configure the
following environment variables:

.. code-block:: bash

    export TAILSCALE_OAUTH_CLIENT_ID=
    export TAILSCALE_OAUTH_CLIENT_SECRET=
    export TAILSCALE_TAILNET=

Now you can run the Dagster development server and sync Tailscale device
snapshots from your tailnet.

.. _Tailscale OAuth clients: https://tailscale.com/kb/1215/oauth-clients
.. _Setting up an OAuth client: https://tailscale.com/kb/1215/oauth-clients#setting-up-an-oauth-client
