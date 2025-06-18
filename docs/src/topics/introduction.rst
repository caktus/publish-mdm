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

Dynamic Forms with Template Variables
-------------------------------------

Advanced data collection projects require more than just a static form. You
often need to customize the form experience. For example, you may want to
pre-fill a location's name, set a default facility ID, or embed a hidden
password unique to each user.

Creating separate forms for each case is inefficient and error-prone. Publish
MDM solves this with **Publish MDM Templates and Template Variables**, allowing
you to design a single, generic form that gets populated with App User-specific
data upon publishing.

This guide explains how to use these variables to create dynamic, personalized
forms.

Core Concepts
~~~~~~~~~~~~~

First, let's define the two key components of this feature.

Publish MDM Form Template
    A reusable form definition (in a Google Sheet) that can be published as
    multiple, distinct Forms in ODK Central. Form Templates can include template
    variables that are substituted with specific values for each App User. It
    allows for a "one form, many variations" approach.

Publish MDM Template Variables
    Placeholders in your Form Template that are replaced with specific data for
    each ODK Central App User. This data can include a name, a location, a
    unique ID, a password, or other contextual information. For security, these
    variables can be automatically SHA256 digested to protect sensitive
    information. See :ref:`security-confidential-variables`.

Publish MDM Form Template Version
    A specific version of a Publish MDM Form Template that has been published to
    ODK Central, one per ODK Central App User. The entire history of .xlsx files
    is stored in Publish MDM.

How It Works
~~~~~~~~~~~~

The mechanism is simple and builds on standard Google Sheet form functionality.

1. You define a variable in your Google Sheet using a row with the ``calculate``
   question type.
2. The ``name`` column of that row becomes the **variable name** (e.g.,
   ``location``, ``facility_id``).
3. You define the corresponding values for each App User within the Publish MDM
   system.
4. When you publish the Form Template for a specific user, Publish MDM
   automatically populates the ``calculation`` column of the final XForm with
   that user's specific value.

How to Implement Template Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Follow these steps to configure and use template variables in your project.

Step 1: Define Values for App Users
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Before adding variables to your form, you must define the data for each App User
within a Publish MDM Project. This involves associating key-value pairs with
each App User. 

For example, for an app user named ``north``, you might define the following values:

* ``location``: North Clinic
* ``login_pin``: 1234

You can set these values in several ways:

* Editing individual App Users in Publish MDM web interface and saving values
  for each Template Variable.
* Using the App User Import feature to upload a CSV file with App Users and
  values for each Template Variable.

Step 2: Add Template Variables to Your Form
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

In your Google Sheet, add a new row for each variable you want to use on the
``survey`` sheet.

* Set the ``type`` to ``calculate``.
* Set the ``name`` to the exact name of the variable you defined in Step 1
  (e.g., ``facility_id``, ``location``).
* The ``label`` is for your own reference and is not required.
* Leave the ``calculation`` column **blank**. Publish MDM will fill this in
  automatically.

Survey sheet example:

.. list-table::
   :widths: 25 25 25 25
   :header-rows: 1

   * - type
     - name
     - label
     - calculation
   * - ``calculate``
     - ``location``
     - Assigned Clinic Location
     - *leave blank*

These variables are now available within your form but will be invisible to the
user by default.

Step 3: Use the Variables in Your Form
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To make the variables useful, you need to reference them elsewhere in your form using the standard ``${variable_name}`` syntax.

You can use them to:

* **Display a welcome message:** Create a ``note`` question with a label like:
  ``Welcome, ${full_name}!``
* **Set a default value:** For a ``text`` question, set the ``default`` column
  to ``${location}`` to pre-fill the user's assigned clinic.
* **Store as metadata:** The calculate variables will be saved as part of the
  submission data, automatically tagging each record with the App User's
  information.

Survey sheet example of usage:

.. list-table::
   :widths: 25 25 25 25
   :header-rows: 1

   * - type
     - name
     - label
     - default
   * - ``text``
     - ``clinic_name``
     - ``You are submitting from ${location}``
     -


Step 4: Publish the Form Template
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When you publish this template for the App User ``north``, Publish MDM generates
a unique ODK Form where the ``calculation`` column for the ``location`` variable
now contains ``"North Clinic"``, making it available to the rest of the form.

.. _security-confidential-variables:

Security: Confidential Variables
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For sensitive data like PINs or passwords, Publish MDM allows you to
automatically insert a **SHA256 hash** of a variable instead of the variable
itself.

This is done by selecting the ``SHA256_DIGEST`` transform option when defining
Template Variables in the Publish MDM web interface.

Example: Implementing a PIN Check
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Let's say you have a ``admin_pin`` value for each App User (e.g., "4815").

1. **In your Google Sheet**, define the ``calculate`` variable with the
   ``admin_pin`` variable. You can then use the ``calculation`` and
   ``constraint`` columns to check the user's input against the stored hash.

   .. list-table::
      :widths: 25 25 25 25
      :header-rows: 1

      * - type
        - name
        - calculation
        - constraint
      * - ``calculate``
        - ``admin_pin``
        - 
        - 
      * - ``text``
        - ``manager_pin_typed``
        -
        - ``digest(${admin_pin}, "SHA-256", "hex") = ${admin_pin_sha256}``
      * - ``calculate``
        - ``admin_pin_extracted``
        - ``digest(${manager_pin_typed}, "SHA-256", "hex") = ${admin_pin}``
        -

2. When publishing, Publish MDM will:

   * Find the ``admin_pin`` value for the App User ("4815").
   * Compute its SHA256 hash (e.g., ``c158...d5ee``).
   * Inject this hash into the ``calculation`` for the ``admin_pin`` variable.

This process ensures the correct PIN is verified without ever exposing the
actual PIN in the form's logic or the submission data.

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
definition, you must append the special placeholder ``_APP_USER`` to the base name
of the entity list. This placeholder signals to Publish MDM that this is a
dynamic entity list name.

For example, in your Google Sheet, you would define your choice list like this:

.. list-table::
   :header-rows: 1

   * - type
     - name
     - label
   * - select_one_from_entity voter_list_APP_USER.csv
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
