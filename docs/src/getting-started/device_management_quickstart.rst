Getting Started with Device Management
========================================

This guide provides a step-by-step walkthrough for new users to set up an organization, enroll a device, and automate ODK project deployment using Publish MDM.

.. note::
   Device management with Publish MDM is optional but enables powerful features like remote configuration, security policies, and automated form deployment. If you just want to publish forms without managing devices, check out the :doc:`Publishing Your First Form <publish_first_form>` guide instead.

.. note::
   This guide covers the **Google Android Management API** integration. If your organization is using **TinyMDM**, refer to the `TinyMDM documentation <https://www.tinymdm.net/help-resources/>`_ instead.

Step 1: Create a New Organization
---------------------------------

All organizations in Publish MDM are independent, with their own settings and devices.

.. important::
   Due to Android Enterprise enrollment requirements, you must enroll the organization with a **dedicated Gmail account** (e.g., ``name@gmail.com``), **not** a Google Workspace account linked to your company or organization.

   Additionally, the dedicated Gmail account **must be the only and primary account** in the browser profile you use for Android Enterprise enrollment and Publish MDM administration. Using a separate browser profile ensures Google's enrollment process works smoothly.


To begin:

1. **Create a dedicated Gmail account** for your organization (e.g., ``myorg.myuser.publishmdm@gmail.com``).

   - Visit https://support.google.com/mail/answer/56256 for step-by-step account creation instructions.
   - You may also use a personal Gmail account, but it cannot be a Google Workspace (business) account.

   .. tip::

      A dedicated account also keeps your organization's enrollment separate from personal Gmail. This makes it easier to manage access and hand off the account to new team members if needed. **You can still invite Google accounts for yourself and your colleagues as team members later.**

2. **Set up a separate browser profile or incognito window** for this dedicated account to keep it separate from your personal and/or work email accounts. While this is not a requirement for Publish MDM, the Android Enterprise enrollment workflow does not support multiple Google accounts in the same browser profile, so the Gmail account you want to use **must** be the first and primary Google account in your browser profile.

   - For a persistent separate profile, see `Chrome's multiple profiles documentation <https://support.google.com/chrome/answer/2364824>`__.
   - Alternatively, use an **incognito or private window** (Ctrl+Shift+N in Chrome on Windows, Cmd+Shift+N in Chrome on Mac, Ctrl+Shift+P in Firefox on Windows, or Cmd+Shift+P in Firefox on Mac) for a temporary session.

3. Log in to the Publish MDM frontend at https://app.publishmdm.com/ using this dedicated Gmail account (from your separate profile or incognito window).
4. You will be prompted to create a new organization. Name it appropriately (e.g., "My Organization"). You can create separate device fleets for different field teams later; in general, a single company or non-profit will only need one Publish MDM organization.
5. After setup is complete, you can invite team members with their work Google accounts to join the organization (they will have the same access as the account that created it).

Step 2: Set up Android Enterprise
---------------------------------

To manage devices, your organization must be linked to Android Enterprise. An "enterprise" is a Google-managed resource tied to your dedicated Gmail account that acts as the enrollment authority for your devices. Since you created the organization with a dedicated Gmail account in Step 1, you are already set up for this step.

.. important::

   Make sure you're still in the browser profile with your **dedicated Gmail account** before starting this step. If you've closed your profile or logged out, switch back to it now.

1. While still logged in with your **dedicated Gmail account** (using the browser profile or incognito window from Step 1), navigate to the **Fleets**, **Policies**, or **Devices** page in the sidebar.
2. Click the **Setup Android Enterprise** link.
3. You will be redirected to Google's Android Enterprise enrollment page. If prompted, make sure you are logged into the **dedicated Gmail account** (the same one you used to create the organization).
4. Select the **Sign up for Android only** option and follow the prompts to authorize Publish MDM to manage Android Enterprise on your behalf.
5. Once complete, you'll see an "Android Enterprise enrollment completed successfully" message. You are now ready to enroll devices.

Step 3: Sync Your Default Policy
--------------------------------

Initial enrollment automatically creates a **Default Policy** (which defines device settings like restrictions, apps, and security rules) and a **Default Fleet** (a logical group of devices). To activate the default policy with Google's Android Management API:

1. Navigate to the **Policies** page.
2. Open the **Default Policy**.
3. Scroll to the bottom and click **Save**. This sends the policy to Google's servers and makes it active for future device enrollments.

   .. tip::

      The Default Policy is a basic policy with minimal apps and restrictions. It's designed for testing. Once you're ready for production, you can modify the policy to add security restrictions, app bundles, VPN, and other settings. See the :doc:`Mobile Device Management <../topics/mdm>` guide for more details.

Step 4: Enroll Your First Device
--------------------------------

There are two primary enrollment methods depending on the device's use case:

**Option A: Fully Managed — Company-Owned Device (QR Code)**
*Recommended for dedicated field devices. Provides full control over the device, including app installation, security policies, and restrictions. Requires a factory reset.*

.. tip::

   :doc:`📱 Enroll a Company-Owned Device <enroll_company_owned_device>` — Share this guide with the person setting up the device.

   Once enrolled, refresh the **Devices** page to confirm the device appears in the list.

**Option B: Work Profile — Personally-Owned Device**
*"Bring Your Own Device" (BYOD) option. Creates a separate work profile on a personal phone. Provides less control than fully managed mode, but allows employees or field staff to use their personal devices. Personal data remains private.*

.. tip::

   :doc:`👤 Enroll a Personally-Owned Device <enroll_personally_owned_device>` — Share this guide with the device owner.

   Once enrolled, refresh the **Devices** page to confirm the device appears in the list.

.. note::
   For work profiles, the serial number that appears is a random identifier assigned to the work profile, not the actual serial number of the device.

Step 5: Link ODK Central and Assign Projects
--------------------------------------------

Once a device is enrolled, you can automate its configuration to deploy ODK Collect.

1. **Add Central Server:** Navigate to **Central Servers**, click **Add Central Server**, and enter your ODK Central URL and credentials.

   .. important::

      Your ODK Central credentials are encrypted and stored securely.

2. **Sync Project:** Navigate to **Sync Project**, select your server, and choose the ODK project to deploy.
3. **Assign to Fleet:** Navigate to **Fleets**, select your **Default Fleet**, and assign the ODK project and an **App User** (a service account in ODK Central used for automated deployments) to it.
4. **Verification:** Your enrolled device will automatically receive the configuration and install the ODK Collect app. Check the Devices page to confirm the app status. Forms should be available in ODK Collect within a few minutes.

   .. tip::

      If forms don't appear on the device within a few minutes, check that:

      - The device has internet connectivity
      - ODK Collect is installed and opened at least once
      - The app user has been assigned to both the project and the form

What's Next?
------------

**Congratulations!** You've successfully set up Publish MDM with Android Enterprise and enrolled your first device. Your device is now managed and will automatically receive forms and policy updates from Publish MDM.

Here are some useful next steps:

- **Enroll More Devices:** Share the :doc:`company-owned <enroll_company_owned_device>` or :doc:`personally-owned <enroll_personally_owned_device>` enrollment guides with your team to enroll additional devices.
- **Create Device Fleets:** Use the **Fleets** section to organize devices by region, team, or project, and assign different forms to different groups.
- **Learn More about Device Management:** Visit the :doc:`Mobile Device Management <../topics/mdm>` guide to understand policies, device security, and advanced MDM concepts.
- **Customize Forms with Template Variables:** Check out :doc:`Dynamic Forms with Template Variables <../topics/form_templates>` to learn how to personalize forms for different users or locations without creating multiple form versions.
- **Troubleshoot Issues:** If you encounter any problems, refer to the :doc:`Troubleshooting Guide <troubleshooting>` or contact support.
