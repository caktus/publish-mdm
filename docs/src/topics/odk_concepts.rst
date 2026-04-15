ODK Central Concepts
====================

In order to understand how Publish MDM works, it's important to understand the
concepts behind ODK Central.

Core Concepts
-------------

ODK Central Form
""""""""""""""""

The heart of the ODK ecosystem is the form. Forms provide a structured way
to collect and provide information. They are defined in XML and can be
published to ODK Central.

ODK Central Server
""""""""""""""""""

An instance of ODK Central that hosts projects, forms, and app users. Publish
MDM can connect to multiple ODK Central servers, each associated with an
organization. Servers are configured with base URL, username, and password
credentials that are encrypted and stored securely.

ODK Central App User
""""""""""""""""""""

App Users interact with ODK Central through the `ODK Collect`_ app. They
are granted limited access to specific forms within a project.

.. tip::

    A key feature of Publish MDM is the ability to link devices to ODK
    Central App Users through MDM. Devices assigned to an ODK Central App
    User will automatically configure ODK Collect with the correct forms and
    settings without needing to scan a QR code (using `ODK Collect's MDM
    configuration`_).

ODK Central Project
"""""""""""""""""""

A container within ODK Central that groups related forms and app users
together. Projects in Publish MDM are synchronized with ODK Central projects
and can be created either locally or by syncing from existing ODK Central
projects.

How Publish MDM Extends These Concepts
--------------------------------------

Publish MDM builds on these core ODK Central concepts by introducing form templates,
template variables, and device management capabilities. Instead of creating separate
forms for each user or data source, you can create a single form template and have
Publish MDM automatically generate custom versions for different users, regions, or
teams.

See the :doc:`Dynamic Forms with Template Variables <form_templates>` guide for more
information on how to use template variables to create flexible, reusable forms.

.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
.. _ODK Collect's MDM configuration: https://forum.getodk.org/t/odk-collect-v2025-2-beta-edit-finalized-sent-forms-mdm-configuration-android-15-support/54254
