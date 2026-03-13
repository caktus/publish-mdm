Tutorial
========

This guide will walk you through publishing a form to ODK Central using ODK
Publish.


1. Setup ODK Central
--------------------

Create or access an existing ODK Central instance. You can use `ODK Cloud`_, a
:doc:`local Docker-based instance <../local-development/odk-central>`, or your own
deployment.

1. Create an admin user for Publish MDM to use. This user will be used to
   publish forms to ODK Central.

2. Create a project for the forms you will be publishing.

.. _ODK Cloud: https://getodk.org/#pricing


2. Setup Publish MDM
--------------------

Follow the :doc:`Quickstart with Docker <../running/docker-compose>` or :doc:`Local
Development <../local-development/index>` guide to run Publish MDM locally.

1. Configure Publish MDM environment variables. You will need to set the
   following environment variables:

   - ``GOOGLE_CLIENT_ID`` and ``GOOGLE_CLIENT_SECRET``: These are the OAuth
     credentials for the Google account you will use to authenticate with ODK
     Central and to download forms from Google Sheets.

   - ``GOOGLE_API_KEY`` and ``GOOGLE_APP_ID`` are used to enable the `Google Picker <https://developers.google.com/drive/picker/guides/overview>`_,
     which users will use to give access to specific spreadsheets in their Google accounts.
     To get the API key, `create it in your Google Cloud dashboard <https://developers.google.com/drive/picker/guides/overview#setup>`_.
     The ``GOOGLE_APP_ID`` is the "Project number" in the `Google Cloud dashboard <https://console.cloud.google.com/home/dashboard>`_.

   - ``INFISICAL_API_URL``, ``INFISICAL_TOKEN``, and ``INFISICAL_KMS_PROJECT_ID``: See :doc:`../local-development/infisical`.

   - To use Android EMM as your :ref:`mdm-service-provider`, set the following environment variables:

      - ``ACTIVE_MDM_NAME="Android Enterprise"``
      - ``ACTIVE_MDM_CLASS=apps.mdm.mdms.AndroidEnterprise``
      - ``ANDROID_ENTERPRISE_SERVICE_ACCOUNT_FILE``: The path to a Google service account file.
        See the `Google docs <https://developers.google.com/android/management/service-account>`_ on how to create one.
      - ``ANDROID_ENTERPRISE_ID``: The ID of an Android EMM Enterprise, without the ``enterprises/`` prefix.
        You can create an enterprise by following `this guide <https://developers.google.com/android/management/quickstart>`_.
        You may also need to `request an initial quota of devices <https://developers.google.com/android/management/permissible-usage#quotas_and_restrictions>`_
        in order to successfully enroll devices in the MDM.

   - To use TinyMDM as your MDM service provider (the default if ``ACTIVE_MDM_NAME`` is not set),
     set ``TINYMDM_ACCOUNT_ID``, ``TINYMDM_APIKEY_PUBLIC``, and ``TINYMDM_APIKEY_SECRET``.
     You can also set the ID of your default :ref:`mdm-policy` in ``MDM_DEFAULT_POLICY``, or you
     can create a default policy in Admin once your server is up and running (see Step 5 below).

2. Start the Publish MDM server, login with your Google account, and make
   yourself an admin.

3. Create a Central Server using your ODK Central server's base URL and credentials.
   You can do this in Admin (``/admin/publish_mdm/centralserver/``) or on the frontend.

   If you're using the local Docker-based ODK Central instance, you can set the base
   URL to ``http://central-dev.localhost:9100``.
   Additionally, you may need to add ``central-dev.localhost`` to your
   ``/etc/hosts`` so Python can resolve the lookback address.

4. Sync your ODK Central project by visiting
   http://localhost:8000/odk/servers/sync/.

5. Create a default MDM policy in Admin (``/admin/mdm/policy/``). If Android EMM is your MDM service provider,
   add a JSON template for the policy, which will be used to create device-specific policies. This can be a
   Django template which will get the following in its context:

    - ``device``: A ``mdm.models.Device`` object.
    - ``tailscale_auth_key``: The value of the ``TAILSCALE_AUTH_KEY`` environment variable, if set.

   See the `Google docs <https://developers.google.com/android/management/reference/rest/v1/enterprises.policies>`_
   for the expected JSON format.

3. Setup project in Publish MDM
-------------------------------

Now that you have ODK Central and Publish MDM set up, you can add form templates
to Publish MDM.

1. **Define variables:** If your forms use template variables, you will need to `add template
   variables`_ and then associate them with the `project in the admin`_.

2. **Add forms:** Use `Add a form template`_ in the Django admin to add each project form to
   Publish MDM. You will need to provide the form's title, form ID base, and the
   form's Google Sheet URL.

3. **Create app users with variables:** `Export App Users`_  and fill in app
   user details, variable values, and assign them to forms. Then `Import App
   Users`_  using the exported file to create or update app users in Publish MDM.

4. **Generate ODK Collect QR codes:** Generate QR codes by clicking
   Actions->Regenerate QR Codes on the `App Users`_ page.

5. **Publish forms:** Publish the forms to ODK Central by clicking Publish on a
   form detail page.

.. _Add a form template: http://localhost:8000/admin/publish_mdm/formtemplate/add/
.. _Add template variables: http://localhost:8000/admin/publish_mdm/templatevariable/add/
.. _project in the admin: http://localhost:8000/admin/publish_mdm/project/
.. _Export App Users: http://localhost:8000/odk/1/app-users/export/
.. _Import App Users: http://localhost:8000/odk/1/app-users/import/
.. _App Users: http://localhost:8000/odk/1/app-users/
