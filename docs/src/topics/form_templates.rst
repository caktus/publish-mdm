Dynamic Forms with Template Variables
=====================================

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
-------------

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
------------

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
-----------------------------------

Follow these steps to configure and use template variables in your project.

Step 1: Define Values for App Users
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

When you publish this template for the App User ``north``, Publish MDM generates
a unique ODK Form where the ``calculation`` column for the ``location`` variable
now contains ``"North Clinic"``, making it available to the rest of the form.

.. _security-confidential-variables:

Security: Confidential Variables
--------------------------------

For sensitive data like PINs or passwords, Publish MDM allows you to
automatically insert a **SHA256 hash** of a variable instead of the variable
itself.

This is done by selecting the ``SHA256_DIGEST`` transform option when defining
Template Variables in the Publish MDM web interface.

Example: Implementing a PIN Check
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

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
