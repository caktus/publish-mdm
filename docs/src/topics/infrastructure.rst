Infrastructure and Security
===========================

Publish MDM is designed to be deployed as a cloud-based service that integrates with various external systems. This document outlines the infrastructure components, requirements, and deployment options for running Publish MDM.

Architecture Overview
--------------------

Publish MDM uses a modern architecture with the following core components:

.. mermaid::

    architecture-beta
        group publishmdm(cloud)[Publish MDM]

        service db(database)[PostgreSQL] in publishmdm
        service storage(disk)[S3 Object Storage] in publishmdm
        service web(server)[Django App] in publishmdm
        service dagster(server)[Dagster Data Orchestrator Platform] in publishmdm
        service secrets(database)[Infisical Secrets Storage] in publishmdm

        web:R -- L:db
        web:L -- R:storage
        web:B -- T:secrets
        web:T -- B:dagster

        service tinymdm(internet)[TinyMDM]
        service tailscale(internet)[Tailscale VPN]
        service central(internet)[ODK Central]
        service sentry(internet)[Sentry]
        service google(internet)[Google Sheets]

Components
----------

Web Application Server
~~~~~~~~~~~~~~~~~~~~~~

The Django web application runs on:

* **Gunicorn** (WSGI server): for serving the Django web application
* **Daphne** (ASGI server): for asynchronous WebSocket support (real-time publishing of forms)

The application server handles:

* User authentication and session management
* Form template management and publishing
* API endpoints for external integrations
* WebSocket connections for real-time publishing updates

Database (PostgreSQL)
~~~~~~~~~~~~~~~~~~~~~

Publish MDM requires a PostgreSQL database (version 15 or later) to store:

* User accounts and authentication data
* Form templates and their versions
* ODK Central server configurations
* MDM device and fleet information
* Project and organization data
* Template variables and user-specific data

Object Storage (S3-compatible)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

S3-compatible object storage is used for:

* Form template file storage (.xlsx files)
* Generated QR codes and temporary files
* Media uploads and exports

Data Orchestration (Dagster)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Dagster provides data orchestration capabilities for:

* Automated periodic device snapshot collection from MDM and VPN provider
* Bulk data synchronization between Publish MDM and MDM provider when configuring devices

Secrets Management (Infisical)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Infisical provides secure secrets management for:

* ODK Central server credentials (encrypted before database storage)
* TinyMDM API keys

External Service Integrations
----------------------------

Google Cloud Platform
~~~~~~~~~~~~~~~~~~~~

Publish MDM integrates with several Google services:

* **Google OAuth 2.0**: User authentication and single sign-on
* **Google Drive API**: Access to form template spreadsheets
* **Google Picker API**: File selection interface for users
* **Google Sheets API**: Reading and processing form definitions

ODK Central
~~~~~~~~~~~

Publish MDM connects to one or more ODK Central instances:

* Form publishing and management
* App user creation and management
* Project synchronization

Mobile Device Management (MDM)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Publish MDM integrates with MDM providers for device management:

* **TinyMDM**: Primary MDM provider for Android device management
* Device enrollment and policy application
* Application deployment and configuration
* Device monitoring and compliance reporting

VPN Integration
~~~~~~~~~~~~~~~

* **Tailscale**: Secure VPN connectivity for devices
* Automatic device configuration
* Network access control
* Secure communication channels
