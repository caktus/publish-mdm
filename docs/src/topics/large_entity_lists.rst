Managing Large Entity Lists with Form Templates
===============================================

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

Core Concepts
-------------

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
--------------------------------------------

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
--------------------------------------

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
^^^^^^^^^^

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
------------------

* **Naming Convention:** The separator between the base name and the suffix
  **must** be an underscore (``_``).
* **Exact Match:** The app username in ODK Central must be an exact match for
  the suffix of the entity list name.
* **Data Management:** You are responsible for the logic and process of
  splitting the large entity list into smaller ones and keeping them updated in
  ODK Central. This feature does not manage the data itself, only the form's
  reference to it.

.. _Infisical KMS: https://infisical.com/
