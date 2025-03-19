import os

from django.db.models import Q

from requests_ratelimiter import LimiterSession
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from apps.mdm.models import Policy, Device


def get_tinymdm_session():
    session = LimiterSession(per_second=5)

    headers = {
        # TODO: Move these to secure credential store
        "X-Tinymdm-Manager-Apikey-Public": os.getenv("TINYMDM_APIKEY_PUBLIC"),
        "X-Tinymdm-Manager-Apikey-Secret": os.getenv("TINYMDM_APIKEY_SECRET"),
        "X-Account-Id": os.getenv("TINYMDM_ACCOUNT_ID"),
    }
    session.headers.update(headers)

    retries = Retry(
        total=5,
        backoff_factor=0.1,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))

    return session


def pull_devices(policy):
    url = "https://www.tinymdm.net/api/v1/devices"
    querystring = {"policy_id": policy.policy_id, "per_page": 1000}

    session = get_tinymdm_session()
    response = session.request("GET", url, params=querystring)
    response.raise_for_status()
    mdm_devices = response.json()["results"]

    devices_by_id = {device["id"]: device for device in mdm_devices}
    devices_by_serial = {device["serial_number"]: device for device in mdm_devices}

    our_devices = Device.objects.filter(
        Q(policy=policy)
        & (Q(device_id__in=devices_by_id.keys()) | Q(serial_number__in=devices_by_serial.keys()))
    )

    for our_device in our_devices:
        if our_device.device_id:
            mdm_device = devices_by_id.get(our_device.device_id)
        else:
            mdm_device = devices_by_serial.get(our_device.serial_number)
        if not mdm_device:
            # TODO: Remove the device from our database?
            continue
        our_device.serial_number = mdm_device["serial_number"] or ""
        our_device.device_id = mdm_device["id"]
        our_device.name = mdm_device["nickname"] or mdm_device["name"]
        our_device.raw_mdm_device = mdm_device

    Device.objects.bulk_update(
        our_devices, fields=["serial_number", "device_id", "raw_mdm_device", "name"]
    )

    our_device_ids = {device.device_id for device in our_devices}
    mdm_devices_to_create = [
        Device(
            policy=policy,
            serial_number=mdm_device["serial_number"] or "",
            device_id=mdm_device["id"],
            name=mdm_device["nickname"] or mdm_device["name"],
            raw_mdm_device=mdm_device,
        )
        for mdm_device in mdm_devices
        if mdm_device["id"] not in our_device_ids
    ]
    Device.objects.bulk_create(mdm_devices_to_create)


def push_device_config(device):
    session = get_tinymdm_session()
    user_id = device.raw_mdm_device["user_id"]
    url = f"https://www.tinymdm.net/api/v1/users/{user_id}"
    response = session.get(url)
    data = response.json()

    data.update(
        {
            "custom_field_1": "test",
        }
    )

    response = session.request("PUT", url, json=data)

    print(response.text)


def sync_policy(policy):
    pull_devices(policy)
    for device in policy.devices.select_related("policy").all():
        push_device_config(device)
        break


def sync_policies():
    for policy in Policy.objects.all():
        sync_policy(policy)
