Virtual Private Network (VPN)
=============================

A Virtual Private Network (VPN) is a secure connection that allows devices to
access resources over the internet as if they were connected to a private
network. Publish MDM integrates with a VPN service provider to enable secure
access to internal resources, such as an ODK Central server or other services,
from devices connected to the VPN. Data security is important for many
organizations, and using a VPN helps ensure that sensitive data is transmitted
securely over the internet.


Concepts
--------

VPN Service Provider
    The entity that provides VPN services. PublishMDM currently uses
    `Tailscale`_ as its VPN service provider.

VPN Device
    A device connected to the `Tailnet`_. This device can securely access
    resources on the VPN network, such as an ODK Central server or other
    internal services.

VPN Device Snapshot
    A snapshot of a device's current state, including when it was last connected to
    the VPN, its operating system, and tags associated with the device. Snapshots are
    taken periodically (using :doc:`../local-development/dagster`) to ensure that
    device states are up-to-date.

VPN ACLs
    `Access Control Lists (ACLs)`_ are used to define which devices can access
    specific resources on the VPN network.

    .. note::

        ACLs are managed by the Publish MDM admin team and are not
        configurable by end users. The admin team will ensure that the ACLs are
        set up to allow access to the necessary resources for your organization.

VPN Auth Key
    Reusable pre-authentication keys (called `auth keys`_) are used to securely
    connect a device to the VPN. This key is generated in Tailscale and is
    loaded automatically to the device using the :ref:`mdm-policy` managed
    configuration for the Tailscale app. See `Deploy Tailscale using TinyMDM`_
    for more information on how this is configured when using TinyMDM as the :ref:`mdm-service-provider`.

.. _Tailscale: https://tailscale.com/
.. _Tailnet: https://tailscale.com/kb/1136/tailnet
.. _Access Control Lists (ACLs): https://tailscale.com/kb/1018/acls
.. _auth keys: https://tailscale.com/kb/1085/auth-keys
.. _Deploy Tailscale using TinyMDM: https://tailscale.com/kb/1385/mdm-tinymdm
