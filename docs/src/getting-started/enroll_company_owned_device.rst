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

Power on the factory-reset device. You will see a welcome or "Hi there" screen; this is
the initial Android setup wizard.

Step 2: Open the QR Code Scanner
---------------------------------

On the welcome screen, tap the same spot **very fast and repeatedly** until a QR code scanner
appears. The exact location varies by Android version and manufacturer:

- In general, you want to tap a blank area and avoid any buttons or links.
- On some devices, tap the **center** of the screen.
- On others, tap the **bottom** of the screen.
- If nothing happens, try another location and keep tapping.

The QR code scanner should appear directly. Keep tapping or increase the speed of your tapping
until it does. Google's official documentation states that six taps are required, however, rather
than counting it's easier to simply keep tapping until the scanner appears.

.. tip::
   If tapping doesn't work after many attempts, try the
   `DPC identifier method <https://developers.google.com/android/management/provision-device#dpc_identifier_method>`_ instead:
   proceed through the normal setup wizard, connect to Wi-Fi when prompted, and when
   asked to sign in to a Google account, type ``afw#setup`` instead of an email address.
   This will download Android Device Policy and prompt you to scan a QR code.

Step 3: Scan the Enrollment QR Code
-------------------------------------

Point the device's camera at the enrollment QR code provided by your IT administrator.
The QR code is shown in Publish MDM on the **Devices** page under the **Enroll** button.

Step 4: Complete the Setup Wizard
----------------------------------

.. tip::
   An internet connection is required to download the management software.

Continue through the remaining prompts. When asked, connect to your Wi-Fi network and
enter the password.

The device will automatically:

1. Download **Android Device Policy** (Google's device management app)
2. Configure the device according to your organization's policy
3. Install any required apps (such as ODK Collect)

This process may take a few minutes. Depending on your organization's policy, you may
also be asked to set a PIN, password, or pattern lock and agree to terms and conditions.

Once setup is complete, the device will show the standard Android home screen (or a
managed home screen, if your organization uses one). The device is now enrolled and
managed by your organization.

Verifying Enrollment
--------------------

Your IT administrator can confirm the device is enrolled by checking the **Devices** page
in Publish MDM. The device should appear in the list within a few minutes of completing
setup.

If the device does not appear, check that:

- The device is connected to the internet
- You scanned the correct QR code (ask your IT admin to confirm)
- The device meets the minimum Android version requirement (7.0+)

Next Steps
----------

Once enrolled, your device will automatically receive:

- ODK Collect and any other apps assigned by your IT administrator
- Form configurations for your project
- Security and usage policies defined by your organization

You do not need to do anything else; the apps and forms will appear on the device
automatically within a few minutes. If they don't appear after 10 minutes, try opening
ODK Collect manually to trigger a sync.
