Getting Started with Device Management
========================================

This guide provides a step-by-step walkthrough for new users to set up an organization, enroll a device, and automate ODK project deployment using Publish MDM.

.. note::
   Device management with Publish MDM is optional but enables powerful features like remote configuration, security policies, and automated form deployment. If you just want to publish forms without managing devices, check out the :doc:`Publishing Your First Form <publish_first_form>` guide instead.

Step 1: Create a New Organization
---------------------------------

All organizations in Publish MDM are independent, with their own settings and devices.

.. important::
   Due to Android Enterprise enrollment requirements, you must enroll the organization with a **dedicated Gmail account** (not a Google Workspace account).

   Additionally, the dedicated Gmail account **must be the only and primary account** in the browser profile you use for Android Enterprise enrollment and Publish MDM administration. Using a browser separate profile ensures Google's enrollment process works smoothly.


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

Step 2: Setup Android Enterprise
--------------------------------

To manage devices, your organization must be linked to Android Enterprise. An "enterprise" is a Google-managed resource tied to your dedicated Gmail account that acts as the enrollment authority for your devices. Since you created the organization with a dedicated Gmail account in Step 1, you are already set up for this step.

.. important::

   Make sure you're still in the browser profile with your **dedicated Gmail account** before starting this step. If you've closed your profile or logged out, switch back to it now.

1. While still logged in with your **dedicated Gmail account** (using the browser profile or incognito window from Step 1), navigate to the **Fleets** or **Devices** page in the sidebar.
2. Click the **Setup Android Enterprise** button.
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

      The Default Policy is a basic policy with minimal apps and restrictions. It's designed for testing. Once you're ready for production, you can modify the policy to add security restrictions, app bundles, VPN, and other settings. See the :doc:`Mobile Device Management <mdm>` guide for more details.

Step 4: Enroll Your First Device
--------------------------------

There are two primary enrollment methods depending on the device's use case:

**Option A: Fully Managed (QR Code)**
*This method is for devices that have been factory reset. If possible, this approach is generally recommended as it provides more control over the devices (e.g., app installation, security policies, restrictions).*

1. Factory reset your Android device.
2. On the initial setup screen ("Hi there" or "Welcome", depending on your Android version), **rapidly** tap the center or bottom of the screen **seven times or more** to reveal the hidden QR code scanner.

   .. tip::

      The QR code scanner is only available during the **first setup** of brand-new devices. If the device has already been set up, you must factory reset it again. The scanner location varies by Android version, so be patient and try different areas if needed.

3. Use the QR code scanner to scan the QR code displayed under the **Enroll** button on the **Devices** page in Publish MDM.
4. Follow the prompts on the device to complete the enrollment process. Once enrollment finishes, you will see the standard Android home screen or a kiosk screen (depending on your policy settings).
5. Refresh the **Devices** page to confirm your device appears in the list. The device will be configured according to the assigned **Policy**.

**Option B: Work Profile (Link)**
*This method allows "Bring Your Own Device" (BYOD) where a separate work profile is created on a personal device. This provides less control over the device than fully managed mode (e.g., you cannot block system apps or force certain security settings), but allows employees or field staff to use their personal phones.*

1. On the target device, navigate to the enrollment link provided at the bottom of the **Enroll** dialog on the **Devices** page. You may need to send this link to the device via email, SMS, QR code, or another method.
2. Open the link and follow the prompts to create a work profile. Once complete, the work profile is enrolled and will receive app assignments and policies. For more details on the work profile user experience, see `What is an Android Work Profile? <https://support.google.com/work/android/answer/6191949>`_
3. Refresh the **Devices** page to confirm your device appears in the list. The device will be configured according to the assigned **Policy**.

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

- **Enroll More Devices:** Follow the same steps in Step 4 to enroll additional devices using the same or different methods.
- **Create Device Fleets:** Use the **Fleets** section to organize devices by region, team, or project, and assign different forms to different groups.
- **Learn More about Device Management:** Visit the :doc:`Mobile Device Management <mdm>` guide to understand policies, device security, and advanced MDM concepts.
- **Customize Forms with Template Variables:** Check out :doc:`Dynamic Forms with Template Variables <form_templates>` to learn how to personalize forms for different users or locations without creating multiple form versions.
- **Troubleshoot Issues:** If you encounter any problems, refer to the :doc:`Troubleshooting Guide <troubleshooting>` or contact support.
