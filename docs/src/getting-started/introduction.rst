Introduction
============

Publish MDM is a tool for managing and publishing forms to `ODK Central`_, a
powerful data collection platform. It offers support for:

* Single sign-on with Google and access to Google Sheets
* Form templates and variables, which can be used to create multiple versions of
  a form for different app users
* A user-friendly interface for publishing form versions
* MDM integration with :doc:`either TinyMDM or Android EMM <../topics/mdm>` to automatically configure devices with the
  correct forms and settings
* VPN integration with :doc:`Tailscale <../topics/vpn>` to securely connect devices to ODK Central

Getting Started
---------------

There are two main workflows depending on your needs:

**1. Basic Form Publishing**
   If you want to publish forms from Google Sheets to ODK Central and share them with data collectors,
   start with the :doc:`Publishing Your First Form <publish_first_form>` guide. This is the simplest
   way to get started—no device management required.

**2. Advanced: Automated Device Management**
   If you want to manage Android devices and automatically configure them with forms, policies, and
   security settings, see :doc:`Getting Started with Device Management <device_management_quickstart>`. This enables
   enterprise-grade device management and automated deployment.

Next Steps
----------

To learn more about how Publish MDM works, check out:

- :doc:`Understanding the Form Workflow <../topics/form_workflow>` — See how Publish MDM simplifies publishing forms compared to manual ODK Central workflows
- :doc:`ODK Central Concepts <../topics/odk_concepts>` — Understand the core concepts behind ODK Central that power Publish MDM
- :doc:`Dynamic Forms with Template Variables <../topics/form_templates>` — Learn how to create customizable forms for different users and use cases

.. _ODK Central: https://docs.getodk.org/central-intro/
.. _ODK Collect: https://docs.getodk.org/collect-intro/
