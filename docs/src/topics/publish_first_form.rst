Publishing Your First Form
============================

This guide walks you through the essential steps to publish your first form from Google Sheets to `ODK Central`_ using Publish MDM. This is the **easiest way to get started**—no device management required.

**What you'll learn:**

- Set up a connection to your ODK Central server
- Create a form template from a Google Sheet
- Publish your form to ODK Central
- Share the form with data collectors

.. note::

   If you want to manage Android devices and automatically configure them with forms, see :doc:`Getting Started with Device Management <device_management_quickstart>`. Device management is optional and not required for basic form publishing.

Prerequisites
--------------

Before starting, you'll need:

1. **A Publish MDM account** — log in at https://app.publishmdm.com/
2. **An ODK Central server** — either `self-hosted <https://docs.getodk.org/central-setup/>`_ or from a service provider
3. **ODK Central login credentials** — username and password (or app password)
4. **A Google Sheet with your form** — use `XLSForm <https://xlsform.org/>`_ to design your form

Step 1: Create an Organization
--------------------------------

If you haven't already, create a Publish MDM organization:

1. Log in to Publish MDM at https://app.publishmdm.com/
2. On first login, you will be prompted to create a new organization. If you already have an existing organization, click your initials in the top right corner, select **Switch organization**, and then click **Create a new organization**.
3. Enter an organization name (e.g., "My Organization") and click **Create**.

.. note::

   For form publishing, you can use any Google account.
Step 2: Connect Your ODK Central Server
---------------------------------------

To publish forms, Publish MDM needs credentials to access your ODK Central server:

1. Navigate to **Central Servers** in the sidebar.
2. Click **Add Central Server**.
3. Enter the following information:

   - **Server Name:** A friendly name for your server (e.g., "Production Server")
   - **Server URL:** The base URL of your ODK Central instance (e.g., ``https://central.example.com``)
   - **Username:** Your ODK Central username
   - **Password:** Your ODK Central password

4. Click **Save**. Publish MDM will verify your credentials and connection.

.. important::

   Your credentials are encrypted and stored securely.

Step 3: Sync or Create an ODK Project
--------------------------------------

Publish MDM organizes forms within ODK projects. You can either sync an existing project or create a new one:

**Option A: Sync an Existing ODK Central Project**

1. Navigate to **Sync Project** in the sidebar.
2. Select your Central Server.
3. Select the project you want to sync from ODK Central.
4. Click **Sync**. Publish MDM will import the project and its existing app users.

.. note::

   This is a read-only operation, and will not alter your ODK Central project until you publish a form from within Publish MDM.

**Option B: Create a New Project**

1. Navigate to **Projects** in the sidebar (if this option is available).
2. Click **Create Project**.
3. Enter a project name and click **Create**.
4. (Optional) Add a description for context.

.. note::

   This option requires that your user is an administrator on the ODK Central server so it can create projects.

Step 4: Create Form Template(s)
-------------------------------

A **form template** is your Google Sheet form that will be published to ODK Central. You can use an existing Google Sheet you have, or create a new one for testing.

.. note::
    The Google Sheet must follow the `XLSForm standard <https://xlsform.org/>`_. For a simple test, you can use the `XLSForm tutorial <https://docs.getodk.org/tutorial-first-form/>`_ to create a basic form.

Once you have a Google Sheet ready, create a form template in Publish MDM:

1. Navigate to **Form Templates** in the sidebar.
2. Click **Create Form Template**.
3. Fill in the form details:

   - **Title Base:** A descriptive name for your form (e.g., "Household Survey")
   - **Form ID Base:** A unique identifier for your form (e.g., "household_survey")
   - **Template URL:** Click "Select with Google Picker" and paste the URL of your published Google Sheet, or browse to your form (make sure you have `edit access <https://support.google.com/docs/answer/9711469>`_)
   - **App users:** Leave blank for now

4. Click **Create**. Publish MDM will download and validate your form.


Step 5: Create App User(s)
---------------------------

An **app user** is a data collector who will fill out forms using `ODK Collect`_. Create one or more app users for your project:

1. Navigate to your project's **App Users** page in the sidebar.
2. Click the **Actions** button (or the plus icon) and select **Add an app user**.
3. Enter a username (e.g., "collector_01", "field_team_a").
4. Click **Create** or **Save**.

.. tip::

   Create one app user per data collector, or create multiple app users to segment data (e.g., by region or team).
.. important::

   A powerful feature in Publish MDM is its ability to publish customized versions of a form to different app users using template variables. Refer to :doc:`Dynamic Forms with Template Variables <form_templates>` to learn how this works.

Step 6: Assign Forms to App Users
---------------------------------

Tell Publish MDM which forms each app user should have access to:

1. Navigate to **Form Templates** and select your form.
2. Scroll to the **App Users** section.
3. Select the app user(s) you created in Step 5 to assign this form to them.
4. Click **Save** or **Update**.

Step 7: Publish Your Form
--------------------------

Now you're ready to publish:

1. Navigate to your form template.
2. Click **Publish** (or **Publish New Version** if you've published before).
3. Publish MDM will:

   - Download your Google Sheet
   - Transform it for each assigned app user
   - Upload it to ODK Central
   - Create/update the form for each app user

4. Once complete, you'll see a confirmation message.

**Troubleshooting:** If publication fails, check that:
- Your Google Sheet URL is correct and you have edit access
- Your ODK Central server credentials are valid
- Your form follows the `XLSForm standard <https://xlsform.org/>`_

Step 8: Share the Form with Data Collectors
-------------------------------------------

.. important::
    For larger projects or more advanced use cases, you can follow :doc:`Getting Started with Device Management <device_management_quickstart>` to set up Android device management and avoid the need to distribute ODK Collect QR codes manually, even across multiple projects and surveys.

Your data collectors now need to configure `ODK Collect`_ with their assigned form. To get them set up:

1. Navigate to your project's **App Users** page.
2. Find the app user assigned to your data collector.
3. Click or tap the **QR Code** icon next to the app user to display or download the QR code.
4. Send the QR code to your data collector (via email, print it, or display it on screen).
5. On their Android device, open ODK Collect.
6. Tap **Menu** → **Configure via QR code** (or go to **General Settings** → **Server**).
7. Scan the QR code.
8. ODK Collect will automatically configure with the server settings and forms assigned to that app user.


Step 9: Collect Data
-------------------

Your data collectors can now:

1. Open `ODK Collect`_ on their device.
2. Tap **Get Blank Form** to download any new forms (if they haven't been auto-downloaded).
3. Tap **Fill Blank Form** to start collecting data.
4. Select your form and fill it out in the field.
5. Mark the form as complete when done.
6. Submit completed forms when they reconnect to the internet.

The submitted data will appear in your ODK Central project under the **Submissions** tab for analysis.

Optional: Update Your Form
---------------------------

To make changes to your form:

1. Edit your Google Sheet.
2. Return to the **Form Templates** page and select your form.
3. Click **Publish** or **Publish New Version** (depending on whether this is the first publish or an update).
4. Publish MDM will upload the updated form to ODK Central.
5. When data collectors open ODK Collect, they will see a notification that a new version is available and can download the latest form.

What's Next?
------------

**Want to customize forms for different users or data sources?** Check out :doc:`Dynamic Forms with Template Variables <form_templates>` to learn how to use template variables to personalize forms without creating multiple versions.

**Want to automate device management?** See :doc:`Getting Started with Device Management <device_management_quickstart>` to set up Android device management, automatic form deployment, and policy enforcement.

**Need to manage large datasets efficiently?** Explore the :doc:`Managing Large Entity Lists <large_entity_lists>` guide.

**Have questions?** Refer to the :doc:`Troubleshooting Guide <troubleshooting>` or contact support.

.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
.. _XLSForm: https://xlsform.org/
