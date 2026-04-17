Enrolling a Personally-Owned Device
=====================================

This guide walks you through enrolling your personal Android phone into Publish MDM
using a **Work Profile**. A Work Profile creates a separate, secure space on your device
for work apps and data; your personal apps, photos, messages, and usage remain
completely private and are not visible to your organization.

Follow these steps after your IT administrator has provided you with a QR code or
enrollment link.

.. note::
   This guide is for **personally-owned** devices using a Work Profile. Your organization
   manages only the work profile. **Your personal data stays private.** If you are setting up
   a company-owned or dedicated field device, see
   :doc:`Enrolling a Company-Owned Device <enroll_company_owned_device>` instead.

What You'll Need
----------------

- An Android device running Android 5.1 or later
- The enrollment QR code from your IT administrator (shown in Publish MDM under
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
- If you leave your organization or unenroll, only the Work Profile is removed; your
  personal data is unaffected.

.. |briefcase| unicode:: U+1F4BC

For more details, see `What is an Android Work Profile?
<https://support.google.com/work/android/answer/6191949>`_

Option A: Enroll via Android Device Policy (Recommended)
----------------------------------------------------------

This is the most straightforward method for most users.

**Step 1: Install Android Device Policy**

On your Android device, open the **Google Play Store** and search for
**"Android Device Policy"**, or tap the badge below:

.. image:: https://play.google.com/intl/en_us/badges/static/images/badges/en_badge_web_generic.png
   :target: https://play.google.com/store/apps/details?id=com.google.android.apps.work.clouddpc
   :alt: Get it on Google Play
   :height: 60px

Tap **Install**. If the app is already installed and an update is available, tap **Update** instead.

.. tip::
   Android Device Policy is published by **Google LLC**. Make sure you're installing the
   official app — not a third-party app with a similar name.

**Step 2: Open Android Device Policy**

Once installed, tap **Open**. The app will launch and display a QR code scanner.

**Step 3: Scan the QR Code**

Hold your phone's camera over the enrollment QR code provided by your IT administrator.
The QR code is shown in Publish MDM on the **Devices** page under the **Enroll** button.

The app will read the QR code and begin setting up your Work Profile automatically.

**Step 4: Accept Work Profile Setup**

You will be asked to confirm that you want to set up a Work Profile. Follow the on-screen
prompts to accept. You may also be asked to:

- Set a Work Profile PIN, password, or pattern
- Agree to your organization's terms

Android will then:

1. Create the Work Profile on your device
2. Configure it according to your organization's policy
3. Install any required work apps (such as ODK Collect)

This may take a few minutes. Once complete, you will see work apps appear under a "Work"
tab in your app drawer.

Option B: Enroll via an Enrollment Link
-----------------------------------------

If your IT administrator sent you an enrollment link by email, SMS, or another method:

1. Open the link on your Android device.
2. Follow the on-screen prompts to complete Work Profile setup.

.. note::
   If the link doesn't open correctly, make sure Google Play Services is up to date.
   Go to **Settings → Apps → Google Play Services** and check for updates.

Verifying Enrollment
---------------------

Your IT administrator can confirm your device is enrolled by checking the **Devices**
page in Publish MDM.

On your device, enrollment was successful when:

- Work apps (with briefcase badges) appear in your app drawer
- A **Work** tab or section appears in your app drawer or settings
- You receive a notification that the Work Profile has been set up

If work apps don't appear after 10 minutes, open the **Android Device Policy** app to
check for any pending setup steps.

.. note::
   For personally-owned devices, the serial number shown in Publish MDM is a randomly
   generated identifier assigned to the Work Profile; it is **not** the device's
   actual serial number. This Google limitation is by design to protect users' privacy.

Learn More
----------

Once enrolled, we recommend reviewing the following resources to better understand
how to manage your Work Profile and use work apps:

- `What is an Android Work Profile? <https://support.google.com/work/android/answer/6191949>`_
- `Learn about work profile <https://support.google.com/work/android/topic/7069773>`_

Unenrolling
-----------

If you need to remove the Work Profile (for example, if you leave the organization),
your IT administrator can remove it remotely. You can also remove it yourself by going
following the instructions to `Remove a work account from an Android device <https://support.google.com/a/users/answer/7579983>`_.
Only the Work Profile and its data are removed — your personal apps and data are not affected.
