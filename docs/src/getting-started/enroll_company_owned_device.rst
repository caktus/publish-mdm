Enrolling a Company-Owned Device
=================================

This guide walks you through enrolling a company-owned Android device into Publish MDM
using the QR code method. Follow these steps after your IT administrator has set up the
organization and given you a QR code to scan.

.. note::
   This guide is for **fully managed** (company-owned) devices. The device will be
   completely managed by your organization. If you are setting up your own personal
   phone, see :doc:`Enrolling a Personally-Owned Device <enroll_personally_owned_device>`
   instead.

What You'll Need
----------------

- An Android device (Android 7.0 or later) that has been **factory reset**
- The enrollment QR code from your IT administrator (displayed in Publish MDM under
  **Devices → Enroll**)
- A Wi-Fi network to connect to during setup

.. important::
   The device **must be factory reset** before enrolling. If the device has already been
   set up (i.e., has a home screen), you need to factory reset it first before following
   these steps.

Step 1: Start the Device
------------------------

Power on the factory-reset device. You will see a welcome or **"Hi there"** screen; this is
the initial Android setup wizard.

.. tip::
   Don't tap Start or any other buttons yet—you'll tap the screen itself in the next step.

Step 2: Open the QR Code Scanner
---------------------------------

On the same screen, tap the **center** on a blank area (avoid buttons or text) **six times as quickly as possible**.
A QR code scanner should appear.

If nothing happens after six quick taps, try the **bottom** of the screen and keep tapping rapidly.
**This often takes several attempts**—stay consistent with fast, repeated taps until the scanner opens.

.. note::
   If tapping never opens the scanner, you can use an alternative method: continue through
   the normal setup wizard, connect to Wi-Fi when prompted, and when asked to sign in to a
   Google account, type ``afw#setup`` instead of an email address. This downloads Android
   Device Policy and prompts you to scan a QR code.

Step 3: Scan the Enrollment QR Code
-------------------------------------

Point the device's camera at the enrollment QR code provided by your IT administrator.
The QR code is shown in Publish MDM on the **Devices** page under the **Enroll** button.

Step 4: Complete the Setup Wizard
----------------------------------

.. important::
   The device needs an internet connection to complete setup. Connect to Wi-Fi when prompted.

Continue through the remaining prompts. The device will automatically:

1. Download **Android Device Policy** (Google's device management app)
2. Configure the device according to your organization's policy
3. Install any required apps (such as ODK Collect)

This may take a few minutes. You may also be asked to set a PIN, password, or pattern
lock, and to agree to your organization's terms.

Once setup is complete, the device will show the home screen and is ready to use. It
is now enrolled and managed by your organization.

Verifying Enrollment
--------------------

Your IT administrator can confirm the device is enrolled by checking the **Devices** page
in Publish MDM. The device should appear within a few minutes of completing setup.

If the device does not appear, check that:

- The device is connected to the internet
- You scanned the correct QR code (check with your IT administrator)
- The device is running Android 7.0 or later

Next Steps
----------

Once enrolled, your device will automatically receive:

- ODK Collect and any other apps assigned by your IT administrator
- Form configurations for your project
- Security and usage policies defined by your organization

You don't need to do anything else — the apps and forms will appear on the device
within a few minutes. If they don't appear after 10 minutes, try opening ODK Collect
manually to trigger a sync.
