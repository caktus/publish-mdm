Core Concepts
=============

Publish MDM is a tool for managing and publishing forms to `ODK Central`_, a
powerful data collection platform. It offers support for:

* Single sign-on with Google and access to Google Sheets
* Form templates and variables, which can be used to create multiple versions of
  a form for different app users
* A user-friendly interface for publishing form versions
* MDM integration with :doc:`TinyMDM <mdm>` to automatically configure devices with the
  correct forms and settings
* VPN integration with :doc:`Tailscale <vpn>` to securely connect devices to ODK Central

Form Design Workflow
--------------------

If you're here, you're probably already familiar with the form design workflow
in ODK Central as outlined in the `XLSForm tutorial: Your first form
<https://docs.getodk.org/tutorial-first-form/>`_. At a high level, the workflow
looks like this:

.. mermaid::

    sequenceDiagram
        autonumber
        loop Repeat to fix errors
            Form Designer->>Google Sheets: Update form definition
            Google Sheets->>Desktop: Download .xlsx file
            Desktop->>ODK Central: Create new draft and upload .xlsx file
        end
        Form Designer->>ODK Central: Refresh form list on device
        ODK Central->>Form Designer: Form is available on device

Let's step through the process above from the Form Designer's perspective:

1. Update the form definition in Google Sheets.

2. Save or download the form as an XLSX file.

3. Log into your Central server.

4. If you don't already have a Project, create one and give it a name.

5. Click on the New button next to Forms.

6. Drag and drop your XLSX file onto the file uploader.

7. Click on the Save button and test the form.

This is a simple example, but it demonstrates the process of creating a form in
ODK Central. It can become more complex when you have multiple forms, app users,
projects, and devices.

Publish MDM builds on this workflow in several ways. Form publishing is a single
click in Publish MDM, and the form is published to ODK Central without the need
to download the form to your desktop and upload it to ODK Central.

.. mermaid::

    sequenceDiagram
        autonumber
        loop Repeat to fix errors
            Form Designer->>Google Sheets: Update form definition
            Form Designer->>Publish MDM: Publish next version
        end
        Form Designer->>ODK Central: Refresh form list on device
        ODK Central->>Form Designer: Form is available on device

Publish MDM also introduces the concept of form templates, which are reusable
form definitions that can be published to multiple ODK Central forms. A single
publish event can trigger the creation of many versions of a form, each with
different template variables. This is where Publish MDM really shines.

ODK Central Concepts
--------------------

In order to understand how Publish MDM works, it's important to understand the
concepts behind ODK Central.

ODK Central Form
    The heart of the ODK ecosystem is the form. Forms provide a structured way
    to collect and provide information. They are defined in XML and can be
    published to ODK Central.

ODK Central Server
    An instance of ODK Central that hosts projects, forms, and app users. Publish
    MDM can connect to multiple ODK Central servers, each associated with an
    organization. Servers are configured with base URL, username, and password
    credentials that are encrypted and stored securely.

ODK Central App User
    App Users interact with the ODK Central through the `ODK Collect`_ app. They
    are granted limited access to specific forms within a project.

    .. tip::

        A key feature of Publish MDM is the ability to link devices to ODK
        Central App Users through MDM. Devices assigned to an ODK Central App
        User will automatically configure ODK Collect with the correct forms and
        settings without needing to scan a QR code (using `ODK Collect's MDM
        configuration`_).

ODK Central Project
    A container within ODK Central that groups related forms and app users
    together. Projects in Publish MDM are synchronized with ODK Central projects
    and can be created either locally or by syncing from existing ODK Central
    projects.

Publish MDM Concepts
--------------------

Publish MDM extends the ODK Central concepts in the following ways:

Publish MDM Form Template
    A reusable form definition that can be published to multiple ODK Central
    Forms. Form templates can include template variables that are substituted
    with specific values for each app user. One form, many versions.

Publish MDM Template Variables
    Placeholder values that are replaced with specific data for each ODK Central
    App User, such as a name or label, password, or other contextual data.
    Template variables can be SHA256 digested to ensure confidentiality.

Publish MDM Form Template Version
    A specific version of a Publish MDM Form Template that has been published to
    ODK Central, one per ODK Central App User. The entire history is stored in
    Publish MDM and can be rolled back to any previous version.

API Integration
    Publish MDM uses the `pyODK`_ library to interact with ODK Central's REST
    API, providing:

    - Authentication and session management
    - Project and form CRUD operations
    - App user management
    - Form publishing and assignment
    - Real-time synchronization

Publish MDM QR Code
    Automatic generation of QR codes for each app user containing:

    - Server URL and authentication token
    - Project-specific settings
    - App user assignments
    - Language and display preferences
    - Admin password (if configured)

    QR codes are generated as PNG images and can be downloaded or displayed
    for manual device configuration.


Managing Large Entity Lists with Form Templates
-----------------------------------------------

As your project scales, you may encounter performance limitations with very
large Entity Lists in ODK Central. A single list containing hundreds of
thousands of records can be slow to download and process on mobile devices,
impacting fieldwork efficiency. For more context, see the `ODK documentation on
Entity List limitations <https://docs.getodk.org/entities-intro/#limitations>`_.

Publish MDM offers a powerful solution to this challenge. It allows you to use a
**single form template** to serve different, manageable portions of a large
entity list to different app users, typically segmented by a factor like region,
team, or district.

This approach avoids the need to maintain multiple, nearly identical form
templates, streamlining form design and project management.

The Core Concept
~~~~~~~~~~~~~~~~

The feature works by dynamically modifying the name of the entity list
referenced in your form during the publishing process. Publish MDM appends the
app user's username to the base entity list name specified in your XForm.

The transformation follows this pattern::

    [entity_list_name]_[app_user_name]

For example, if your form is designed to use an entity list named ``voter_list``
and you publish it for an app user named ``north``, Publish MDM will
automatically modify the published form to reference an entity list named
``voter_list_north``.

Prerequisite: Preparing Your Segmented Lists
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. important::

   **Publish MDM does not split the entity list data itself.** Its role is to
   connect the correct form to the correct, pre-existing entity list during the
   publishing process.

The responsibility for dividing a master entity list into smaller, segmented
lists (e.g., ``voter_list_north``, ``voter_list_south``) rests with your
organization's data manager.

Before you can use the form templating feature, you must first create and upload
each segmented entity list to your ODK Central project. This is done using the
standard ODK Central tools:

1. Uploading a ``.csv`` file directly via the **ODK Central web interface**.
2. Updating the list programmatically via the **ODK Central API**.

Publish MDM's automation begins *after* these correctly named and populated
entity lists are already present in your project.

How to Implement Entity List Splitting
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Follow these steps to set up your project to use this feature. We will use the
example of a national voter registration drive that needs to be split by region.

Step 1: Split and Upload Your Master Entity List
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Following the prerequisite above, segment your large entity list. The name of
each new list must follow the ``[base_name]_[suffix]`` pattern, where the suffix
will correspond to an app user's name.

For our example, you would create and upload the following Entity Lists to ODK Central:

* ``voter_list_north``
* ``voter_list_south``
* ``voter_list_east``
* ``voter_list_west``

Step 2: Create Corresponding App Users
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In Publish MDM, create an app user for each segment. The username must exactly
match the suffix you used for your split entity lists.

Following our example, you would create these app users:

* ``north``
* ``south``
* ``east``
* ``west``

Step 3: Design a Single Form Template
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Now, create your Publish MDM Form Template in Google Sheets. In your form
definition, you will reference the **base name** of the entity list. Do not
include the suffix. This allows the same form template to be used for all
regions.

For example, in your Google Sheet, you would define your choice list like this:

.. list-table::
   :header-rows: 1

   * - type
     - name
     - label
   * - select_one_from_entity voter_list
     - voter
     - Select a voter

Step 4: Publish with Publish MDM
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When you use Publish MDM to publish this single form, the system will
automatically handle the rest. When publishing the form for the app user
``north``, Publish MDM will modify the form definition to point to
``voter_list_north``. When publishing for ``south``, it will point to
``voter_list_south``, and so on.

The Result
~~~~~~~~~~

Each app user will now receive a version of the form tailored to their specific
region.

* The user ``north`` will see a form that only downloads and searches within the
  ``voter_list_north`` entity list.
* The user ``west`` will see a form that only downloads and searches within the
  ``voter_list_west`` entity list.

This ensures that the form on each device remains fast and responsive by only
loading the necessary subset of data, all while allowing you to manage a single,
universal form template.

Key Considerations
~~~~~~~~~~~~~~~~~~

* **Naming Convention:** The separator between the base name and the suffix
  **must** be an underscore (``_``).
* **Exact Match:** The app username in ODK Central must be an exact match for
  the suffix of the entity list name.
* **Data Management:** You are responsible for the logic and process of
  splitting the large entity list into smaller ones and keeping them updated in
  ODK Central. This feature does not manage the data itself, only the form's
  reference to it.



.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
.. _ODK Collect's MDM configuration: https://forum.getodk.org/t/odk-collect-v2025-2-beta-edit-finalized-sent-forms-mdm-configuration-android-15-support/54254
.. _Infisical KMS: https://infisical.com/
.. _pyODK: https://getodk.github.io/pyodk/
