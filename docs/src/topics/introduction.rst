Introduction
============

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

    ---
    title: ODK Central Form Design Workflow
    ---
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

    ---
    title: Publish MDM Form Design Workflow
    ---
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
    App Users interact with ODK Central through the `ODK Collect`_ app. They
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

Publish MDM extends the ODK Central concepts, as well as introduces new concepts
to support its features. See the following sections for more information.

.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
.. _ODK Collect's MDM configuration: https://forum.getodk.org/t/odk-collect-v2025-2-beta-edit-finalized-sent-forms-mdm-configuration-android-15-support/54254
.. _pyODK: https://getodk.github.io/pyodk/
