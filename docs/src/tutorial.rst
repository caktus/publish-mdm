Tutorial
========

This guide will walk you through publishing a form to ODK Central using ODK
Publish.


1. Setup ODK Central
--------------

Create or access an existing ODK Central instance. You can use `ODK Cloud`_, a
:doc:`local Docker-based instance <local-development/odk-central>`, or your own
deployment.

1. Create an admin user for ODK Publish to use. This user will be used to
   publish forms to ODK Central.

2. Create a project for the forms you will be publishing.

.. _ODK Cloud: https://getodk.org/#pricing


2. Setup ODK Publish
--------------------

Follow the :doc:`Quickstart with Docker <docker-compose>` or :doc:`Local
Development <local-development/index>` guide to run ODK Publish locally.

1. Configure ODK Publish environment variables. You will need to set the
   following environment variables:

   - ``GOOGLE_CLIENT_ID`` and ``GOOGLE_CLIENT_SECRET``: These are the OAuth
     credentials for the Google account you will use to authenticate with ODK
     Central and to download forms from Google Sheets.

   - ``ODK_CENTRAL_CREDENTIALS``: The ODK Central server and credentials of the admin user
     you created above.
     
     If you're using the local Docker-based instance, you can set this to
     ``base_url=http://central-dev.localhost:9100;username=user1;password=pass1``.
     Additionally, you may need to add ``central-dev.localhost`` to your
     ``/etc/hosts`` so Python can resolve the lookback address.

2. Start the ODK Publish server, login with your Google account, and make
   yourself an admin.

3. Sync your ODK Central project by visiting
   http://localhost:8000/odk/servers/sync/.


3. Setup project in ODK Publish
-------------------------------

Now that you have ODK Central and ODK Publish set up, you can add form templates
to ODK Publish.

1. **Define variables:** If your forms use template variables, you will need to `add template
   variables`_ and then associate them with the `project in the admin`_.

2. **Add forms:** Use `Add a form template`_ in the Django admin to add each project form to
   ODK Publish. You will need to provide the form's title, form ID base, and the
   form's Google Sheet URL.

3. **Create app users with variables:** `Export App Users`_  and fill in app
   user details, variable values, and assign them to forms. Then `Import App
   Users`_  using the exported file to create app users in ODK Publish and ODK
   Central.

4. **Generate ODK Collect QR codes:** Generate QR codes by clicking
   Actions->Regenerate QR Codes on the `App Users`_ page.

.. _Add a form template: http://localhost:8000/admin/odk_publish/formtemplate/add/
.. _Add template variables: http://localhost:8000/admin/odk_publish/templatevariable/add/
.. _project in the admin: http://localhost:8000/admin/odk_publish/project/
.. _Export App Users: http://localhost:8000/odk/1/app-users/export/
.. _Import App Users: http://localhost:8000/odk/1/app-users/import/
.. _App Users: http://localhost:8000/odk/1/app-users/ 
