Publishing Your First Form
============================

This guide walks you through the essential steps to publish your first form from Google Sheets to `ODK Central`_ using Publish MDM. This is the **easiest way to get started**—no device management required.

**What you'll learn:**

- Set up a connection to your ODK Central server
- Create a form template from a Google Sheet
- Publish your form to ODK Central
- Share the form with data collectors

.. note::

   If you want to manage Android devices and automatically configure them with forms, see the :doc:`Quickstart Guide (MDM) <quickstart_mdm>`. Device management is optional and not required for basic form publishing.

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
2. You will be prompted to create a new organization on first login.
3. Name it appropriately (e.g., "My Organization") and click **Create**.

**Note:** For form publishing, you can use any Google account.

Step 2: Connect Your ODK Central Server
---------------------------------------

To publish forms, Publish MDM needs credentials to access your ODK Central server:

1. Navigate to **Central Servers** in the sidebar.
2. Click **Add Central Server**.
3. Enter the following information:

   - **Server Name:** A friendly name for your server (e.g., "Production Server")
   - **Server URL:** The base URL of your ODK Central instance (e.g., ``https://central.example.com``)
   - **Username:** Your ODK Central username
   - **Password:** Your ODK Central password (or `app password <https://docs.getodk.org/central-api/#authentication>`_)

4. Click **Save**. Publish MDM will verify the connection.

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

**Option B: Create a New Project**

1. Navigate to **Projects** in the sidebar (if this option is available).
2. Click **Create Project**.
3. Enter a project name and click **Create**.
4. (Optional) Add a description for context.

Step 4: Create Form Template(s)
-------------------------------

A **form template** is your Google Sheet form that will be published to ODK Central. You can create one or more templates for different form types:

1. Navigate to **Form Templates** in the sidebar.
2. Click **Create Form Template**.
3. Fill in the form details:

   - **Name:** A descriptive name for your form (e.g., "Household Survey")
   - **Project:** Select the project you synced or created in Step 3
   - **Google Sheet URL:** Paste the URL of your published Google Sheet (make sure you have `edit access <https://support.google.com/docs/answer/9711469>`_)
   - **(Optional) Description:** Add notes about the form's purpose

4. Click **Create**. Publish MDM will download and validate your form.

**Form Requirements:**
The Google Sheet must follow the `XLSForm standard <https://xlsform.org/>`_. For a simple test, you can use the `XLSForm tutorial <https://docs.getodk.org/tutorial-first-form/>`_ to create a basic form.

Step 5: Create App User(s)
---------------------------

An **app user** is a data collector who will fill out forms using `ODK Collect`_. Create one or more app users for your project:

1. Navigate to **App Users** in the sidebar (within your project).
2. Click **Create App User**.
3. Enter a username (e.g., "collector_01", "field_team_a") and click **Create**.

**Tip:** Create one app user per data collector, or create multiple app users to segment data (e.g., by region or team).

Step 6: Assign Forms to App Users
---------------------------------

Tell Publish MDM which forms each app user should have access to:

1. Navigate to **Form Templates** → your form.
2. Find the **Assign App Users** section.
3. Select the app user(s) you created in Step 5.
4. Click **Save**.

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

Your data collectors now need to configure `ODK Collect`_ with the form. They have two options:

**Option A: QR Code (Recommended)**

1. Navigate to your project's **App Users** page.
2. Find the app user assigned to your data collector.
3. Click the **QR Code** icon to display or download the QR code.
4. On their Android device, open ODK Collect.
5. Tap the **Menu** → **Configure via QR code** (or **General Settings** → **Server**).
6. Scan the QR code.
7. The form is now ready to use!

**Option B: Manual Configuration**

If QR codes are unavailable, data collectors can manually enter:
- Server URL
- App user credentials (username and password)

Step 9: Collect Data
-------------------

Your data collectors can now:

1. Open `ODK Collect`_ on their device.
2. Tap **Fill Blank Form** (or **Get Blank Form** if forms aren't downloaded).
3. Select your form and start collecting data.
4. Submit completed forms.

The data will appear in your ODK Central project for analysis.

Optional: Update Your Form
---------------------------

To make changes to your form:

1. Edit your Google Sheet.
2. Return to **Form Templates** → your form.
3. Click **Publish New Version**.
4. The updated form will be published to ODK Central.
5. Data collectors will receive a prompt to update their forms in ODK Collect.

What's Next?
------------

**Want to customize forms for different users or data sources?** Check out :doc:`Dynamic Forms with Template Variables <form_templates>` to learn how to use template variables to personalize forms without creating multiple versions.

**Want to automate device management?** See the :doc:`Quickstart Guide (MDM) <quickstart_mdm>` to set up Android device management, automatic form deployment, and policy enforcement.

**Need to manage large datasets efficiently?** Explore the :doc:`Managing Large Entity Lists <large_entity_lists>` guide.

**Have questions?** Refer to the :doc:`Troubleshooting Guide <troubleshooting>` or contact support.

.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
.. _XLSForm: https://xlsform.org/
