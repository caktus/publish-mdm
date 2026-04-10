Quickstart Guide
================

This guide provides a step-by-step walkthrough for new users to set up an organization, enroll a device, and automate ODK project deployment using Publish MDM.

Step 1: Create a New Organization
---------------------------------

All organizations in Publish MDM are independent, with their own settings and devices. To begin:

1. Log in to the Publish MDM frontend at https://app.publishmdm.com/ using a Google account.
2. If this is your first time logging in, you will be prompted to create a new organization.
3. If you are not prompted or want to create additional organizations, click on your user initials (e.g., **GC**) in the top-right corner, select **Switch Organization**, and choose the option to create a new one (e.g., "Field Team A").

Step 2: Setup Android Enterprise
--------------------------------

To manage devices, your organization must be linked to Android Enterprise. An "enterprise" is a resource tied to a Google account (personal Gmail or a dedicated work account) that you own.

1. Navigate to the **Fleets** or **Devices** page in the sidebar.
2. Click the **Setup Android Enterprise** button.
3. **Requirement:** You must use a personal Gmail account for this enrollment, not a Google Workspace account.
4. **Recommendation:** Open the enrollment link in a separate Chrome profile or an incognito window logged into your personal Gmail to avoid session conflicts with your work account.
5. Select the **Sign up for Android only** option and follow the prompts to complete the enrollment.
6. Once complete, you'll see an "Android Enterprise enrollment completed successfully" message. Return to your original work profile in Publish MDM.

Step 3: Sync Your Default Policy
--------------------------------

Initial enrollment automatically creates a **Default Policy** and a **Default Fleet**. To ensure the system-generated policy is active:

1. Navigate to the **Policies** page.
2. Open the **Default Policy**.
3. Scroll to the bottom and click **Save**. This step is required to sync the policy with the Android Management API.

Step 4: Enroll Your First Device
--------------------------------

There are two primary enrollment methods depending on the device's use case:

**Option A: Fully Managed (QR Code)**
*This method is for devices that have been factory reset.*

1. Factory reset your Android device.
2. On the initial setup screen, tap the same spot on the screen **seven times** (or more) to reveal the hidden QR code scanner.
3. Use the scanner to scan the QR code displayed under the **Enroll** button on the **Devices** page.

**Option B: Work Profile (Link)**
*This method allows "Bring Your Own Device" (BYOD) where a separate work profile is created on a personal device.*

1. On the target device, navigate to the enrollment link provided at the bottom of the **Enroll** dialog on the **Devices** page. Send this link to the device via email, SMS, or another method.
2. Open the link and follow the prompts to create a work profile.

Step 5: Link ODK Central and Assign Projects
--------------------------------------------

Once a device is enrolled, you can automate its configuration to deploy ODK Collect.

1. **Add Central Server:** Navigate to **Central Servers**, click **Add Central Server**, and enter your ODK Central URL and credentials.
2. **Sync Project:** Navigate to **Sync Project**, select your server, and choose the ODK project to deploy.
3. **Assign to Fleet:** Navigate to **Fleets**, select your **Default Fleet**, and assign the ODK project and an **App User** to it.
4. **Verification:** Your device should automatically install the ODK Collect app and receive the project configuration via real-time enrollment.

In case of any questions, please refer to the :doc:`Troubleshooting Guide <troubleshooting>` or contact support.
