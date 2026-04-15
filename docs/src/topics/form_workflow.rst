Form Design Workflow
====================

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

Publish MDM Simplifies Form Publishing
----------------------------------------

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

**Key Benefits:**

* Direct publishing from Google Sheets—no manual download/upload steps
* Automated transformation of forms for different users
* Single publish event can create multiple form versions

Publish MDM also introduces the concept of form templates, which are reusable
form definitions that can be published to multiple ODK Central forms. A single
publish event can trigger the creation of many versions of a form, each with
different template variables. This is where Publish MDM really shines.

Learn more about this in the :doc:`Dynamic Forms with Template Variables <form_templates>` guide.

.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
