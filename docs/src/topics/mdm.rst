Mobile Device Management (MDM)
==============================

A core feature of Publish MDM is its Mobile Device Management (MDM) integrations
and capabilities. The MDM integration allows administrators to enforce security
policies, deploy applications, and monitor device compliance across an
organization's mobile and tablet devices.

Concepts
--------
.. _mdm-service-provider:

MDM Service Provider
    The entity that provides MDM services. PublishMDM can currently use either `TinyMDM`_
    or `Android EMM`_ as its MDM service provider.

MDM Device
    A device is any Android tablet or mobile device that is managed through the
    MDM integration.

    .. tip::

        A key feature of Publish MDM is the ability to link devices to `ODK
        Central App Users`_. Devices assigned to an ODK Central App User will
        automatically configure `ODK Collect`_ with the correct forms and
        settings without needing to scan a QR code (using `ODK Collect's MDM
        configuration`_).

MDM Device Snapshot
    A snapshot of a device's current state, including its installed
    applications, battery level, operating system version, manufacturer,
    geolocation, and compliance status. Snapshots are taken periodically (using
    :doc:`../local-development/dagster`) to ensure that device states are
    up-to-date.

.. _mdm-policy:

MDM Policy
    A set of rules and configurations that are applied to devices within a
    fleet. Policies can include security settings, application installations,
    `managed configurations`_, VPN settings, and wallpaper configurations, etc.
    Policies are created and managed in the MDM service provider (e.g., TinyMDM)
    and can be applied to devices in a fleet.

.. _mdm-fleet:

MDM Fleet
    A collection of devices that are managed together. When using TinyMDM as the MDM service provider, fleets are linked to
    `TinyMDM Groups`_ and `TinyMDM Policies`_ and use the `multiple enrollment
    feature`_ to manage devices in bulk.

.. _mdm-zero-touch-enrollment:

Zero-Touch Enrollment
    Zero-touch enrollment is a streamlined process for Android devices to be
    provisioned for enterprise management. A device is pre-registered for
    zero-touch enrollment by an IT admin. TinyMDM can take advantage of this
    feature to automatically enroll devices into a fleet and apply the
    appropriate policy.

.. _TinyMDM: https://www.tinymdm.net/
.. _Android EMM: https://www.android.com/enterprise/management
.. _TinyMDM Groups: https://www.tinymdm.net/how-to/add-single-user/
.. _TinyMDM Policies: https://www.tinymdm.net/how-to/create-policy/
.. _multiple enrollment feature: https://www.tinymdm.net/how-to/enrollment-in-a-row/
.. _managed configurations: https://developer.android.com/work/managed-configurations
.. _ODK Collect: https://docs.getodk.org/collect-intro/
.. _ODK Collect's MDM configuration: https://forum.getodk.org/t/odk-collect-v2025-2-beta-edit-finalized-sent-forms-mdm-configuration-android-15-support/54254
.. _ODK Central App Users: https://docs.getodk.org/central-users/#managing-app-users

Fleets By Example
-----------------

To illustrate how fleets work, consider the following example:

.. mermaid::

    classDiagram

        namespace PublishMDM {
            class Fleet-ProdDevices {
                - device1 [appuser1]
                - device2 [appuser2]
            }
            class Fleet-TestDevices {
                - device3 [appuser1]
                - device4 [appuser2]
            }
            class CentralProject-Survey {
                - form1
                - form2
                - appuser1
                - appuser2
            }
        }

        namespace TinyMDM {
            class Group-ProdDevices {
                - device1
                - device2
            }
            class Policy-ProdApps {
                - app1
                - app2
            }
            class Group-TestDevices {
                - device3
                - device4
            }
            class Policy-TestApps {
                - app1
                - app2
            }
        }

        Fleet-ProdDevices --|> Group-ProdDevices
        Group-ProdDevices --|> Policy-ProdApps
        Fleet-TestDevices --|> Group-TestDevices
        Group-TestDevices --|> Policy-TestApps
        Fleet-ProdDevices --|> CentralProject-Survey
        Fleet-TestDevices --|> CentralProject-Survey

In this example, we have two fleets: ``Fleet-ProdDevices`` and
``Fleet-TestDevices`` with different devices assigned to each fleet. Each fleet
is linked to a TinyMDM group and policy. Devices can easily move between fleets,
and the associated policies and groups in TinyMDM will automatically update to
reflect the changes. This allows for efficient management of devices across
different environments (e.g., production and testing) while maintaining the
necessary security and compliance standards.
