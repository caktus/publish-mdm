Enrolling a Personally-Owned Device
=====================================

This guide walks you through enrolling your personal Android phone into Publish MDM
using a **Work Profile**. A Work Profile creates a separate, secure space on your device
for work apps and data — your personal apps, photos, messages, and usage remain
completely private and are not visible to your organization.

Follow these steps after your IT administrator has provided you with a QR code or
enrollment link.

.. note::
   This guide is for **personally-owned** devices using a Work Profile. Your organization
   manages only the work profile — your personal data stays private. If you are setting up
   a company-owned or dedicated field device, see
   :doc:`Enrolling a Company-Owned Device <enroll_company_owned_device>` instead.

What You'll Need
----------------

- An Android device running Android 5.1 or later
- The enrollment QR code from your IT administrator (displayed in Publish MDM under
  **Devices → Enroll**), or an enrollment link sent to you by email or SMS
- A Wi-Fi or mobile data connection

What a Work Profile Means for You
-----------------------------------

When you set up a Work Profile:

- Work apps appear with a **briefcase badge** (|briefcase|) to distinguish them from
  personal apps.
- Your organization can manage work apps and their data, but **cannot see your personal
  apps, messages, photos, or browsing history**.
- You can pause the Work Profile at any time to temporarily stop work notifications
  (for example, on weekends or holidays).
- If you leave your organization or unenroll, only the Work Profile is removed — your
  personal data is unaffected.

.. |briefcase| unicode:: U+1F4BC

For more details, see `What is an Android Work Profile?
<https://support.google.com/work/android/answer/6191949>`_

Option A: Enroll via the Android Device Policy App (Recommended)
-----------------------------------------------------------------

This is the most straightforward method for most users.

**Step 1: Install Android Device Policy**

On your Android device, open the **Google Play Store** and search for
**"Android Device Policy"**, or go directly to:

`play.google.com/store/apps/details?id=com.google.android.apps.work.clouddpc
<https://play.google.com/store/apps/details?id=com.google.android.apps.work.clouddpc>`_

Tap **Install** and wait for the download to complete. If an update is pending, tap **Update** instead.

.. tip::
   Android Device Policy is published by **Google LLC**. Make sure you're installing the
   official app from Google, not a third-party app with a similar name.

**Step 2: Open Android Device Policy**

Once installed, tap **Open**. The app will launch and show an enrollment screen.

**Step 3: Scan the QR Code**

The app will open a QR scanner. Point your camera at the enrollment QR code
provided by your IT administrator. The QR code is shown in Publish MDM on the
**Devices** page under the **Enroll** button.

The app will read the QR code and begin setting up your Work Profile automatically.

**Step 4: Accept Work Profile Setup**

You will be asked to confirm that you want to set up a Work Profile on your device.
Review the information and tap **Accept** or **Set up** to continue.

Android will then:

1. Create the Work Profile on your device
2. Configure it according to your organization's policy
3. Install any required work apps (such as ODK Collect)

This may take a few minutes.

**Step 5: Complete Setup**

Follow any remaining on-screen prompts. You may be asked to:

- Set a Work Profile PIN, password, or pattern
- Agree to your organization's terms

Once complete, you will see work apps appear under a "Work" tab in your applications list.

Option B: Enroll via an Enrollment Link
-----------------------------------------

If your IT administrator sent you an enrollment link (by email, SMS, or another
method), you can use it instead of scanning a QR code.

1. Open the link on your Android device.
2. You will be guided through Work Profile setup automatically.
3. Follow the on-screen prompts to complete enrollment.

.. note::
   If the link doesn't open correctly, make sure Google Play Services is up to date on
   your device. Go to **Settings → Apps → Google Play Services** and check for updates.

Verifying Enrollment
---------------------

Your IT administrator can confirm your device is enrolled by checking the **Devices**
page in Publish MDM.

On your device, you'll know enrollment was successful when:

- Work apps (with briefcase badges) appear in your app drawer
- A **Work** tab or section appears in your app drawer or settings
- You receive a notification that the Work Profile has been set up

If apps don't appear after 10 minutes, try opening the **Android Device Policy** app
and checking for any pending setup steps.

.. note::
   For personally-owned devices, the serial number shown in Publish MDM is a randomly
   generated identifier assigned to your Work Profile — it is **not** your device's
   actual serial number. This is by design to protect your privacy.

Managing Your Work Profile
---------------------------

Once enrolled, you can:

- **Pause work notifications**: Swipe down the notification shade and toggle the
  Work Profile on/off, or go to **Settings → Work profile**.
- **Access work apps**: Look for the briefcase badge on apps, or find a dedicated
  Work tab in your app drawer.
- **Check your work policy**: Open **Android Device Policy** to see what settings
  your organization has applied to your Work Profile.

Unenrolling
-----------

If you need to remove the Work Profile (for example, if you leave the organization),
your IT administrator can remove it remotely. You can also remove it yourself by going
to **Settings → Work profile → Remove work profile**. This removes only the Work Profile
and all work data — your personal apps and data are not affected.
