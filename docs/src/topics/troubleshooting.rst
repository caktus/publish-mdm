Troubleshooting Guide
=====================

This guide provides solutions for common issues encountered while setting up organizations, enrolling devices, and syncing ODK projects in Publish MDM.

Organization & Account Setup
----------------------------

**I created a new organization, but I'm still seeing data from a different one.**

    **Cause:** There is a known bug where superusers may be automatically redirected to a default organization regardless of their selection.
    **Solution:** Check the organization name in the page header. If it is incorrect, use the **Switch Organization** menu again. If the issue persists, clear your browser cookies or try an incognito window to reset the session.

Android Enterprise (AE) Linkage
-------------------------------

**The Google enrollment page says "Your account cannot be used."**

    **Cause:** You are likely logged into a Google Workspace (business) account. Android Enterprise enrollment for Publish MDM requires a personal Gmail account (e.g., ``name@gmail.com``).
    **Solution:** Sign out of all Google accounts in your browser or—ideally—open the enrollment link in a dedicated Chrome Profile or Incognito window where you are only logged into your personal Gmail.

**After completing Google enrollment, I didn't see the success message.**

    **Cause:** The callback from Google to Publish MDM may have been blocked or timed out.
    **Solution:** Refresh the **Fleets** or **Devices** page. If the "Setup Android Enterprise" button still appears, repeat the enrollment process. Ensure you see the final confirmation on Google's side and click the button to return to Publish MDM.

**I want to unlink my Gmail account from Publish MDM.**

    **Cause:** Unlinking needs to be performed directly by the user in their Google account settings.
    **Solution:** Navigate to https://play.google.com/work/adminsettings in your personal Chrome profile, and delete the organization that links your Gmail account to Publish MDM.

Policy & Fleet Configuration
----------------------------

**Settings changed in the Policy are not updating on the device.**

    **Cause:** The system-generated Default Policy does not always trigger an automatic sync to the Android Management API upon creation.
    **Solution:** Navigate to the **Policies** page, open your policy, and click **Save** at the bottom of the form. This manual save forces a sync of all configurations to the cloud.

Device Enrollment
-----------------

**The "Seven Taps" method isn't showing the QR scanner.**

    **Cause:** You may not be on the first setup screen or the device is not fully factory reset.
    **Solution:** Ensure you're on the initial setup screen. Tap a white space area (away from buttons) repeatedly. You may need to tap more than 7 times; keep tapping until the QR scanner appears. If the device has progressed to Wi-Fi setup, factory reset it again.

**The QR code scanner says "Invalid QR Code."**

    **Cause:** The enrollment token may have expired, or the device lacks an internet connection.
    **Solution:** Refresh the **Devices** page in Publish MDM and tap "Enroll" again to generate a fresh QR code. After scanning, ensure the device is connected to a stable Wi-Fi network.

ODK Project Provisioning
------------------------

**The device is enrolled, but ODK Collect is blank or shows no projects.**

    **Cause:** The ODK Project or App User has not been correctly assigned to the Fleet.
    **Solution:**

        1. Go to the **Fleets** page and verify that an ODK project is assigned to the Fleet for your device.
        2. Go to the **Devices** page and verify the device is assigned to an App User.
        3. To force a sync, you can edit the Policy assigned to your Fleet and click "Save" to trigger a push of all settings to the associated devices.

**ODK Collect is asking for a QR code manually.**

    **Cause:** The "Managed Configuration" (which automates setup) hasn't reached the app yet.
    **Solution:** Ensure the device has finished downloading ODK Collect from the Play Store. Installation may take 1-2 minutes.

**My device has multiple projects, and the one I selected in Publish MDM isn't selected in ODK Collect.**

    **Cause:** ODK Collect does not enforce that your selected project in Publish MDM is the active one. This is a known limitation.
    **Solution:** Train data collectors to manually select the correct project in ODK Collect, or clear the app data (after confirming all data has been synced to ODK Central) to reinstall only your selected project on the devices.
