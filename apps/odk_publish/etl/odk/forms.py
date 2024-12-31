import datetime as dt

from pyodk import Client


def maybe_fail_loudly_for_odk_resp(resp):
    "Fail loudly (including body/error message) on error from ODK Central"
    try:
        resp.raise_for_status()
    except:
        print(resp.content)
        raise


def get_existing_forms(client: Client, project_id: str):
    # Get the forms that exist now.
    url = f"/projects/{project_id}/forms"
    response = client.get(url)
    maybe_fail_loudly_for_odk_resp(response)
    return response.json()


def get_unique_version_by_form_id(client: Client, project_id: str, form_id_base: str):
    """
    Generates a new, unique version for the form whose xmlFormId starts with
    the given form_id_base.
    """
    today = dt.datetime.today().strftime("%Y-%m-%d")
    forms = get_existing_forms(client=client, project_id=project_id)
    versions = [
        int(form["version"].split("v")[1])
        for form in forms
        if form["xmlFormId"].startswith(form_id_base) and form["version"].startswith(today)
    ]
    new_version = max(versions) + 1 if versions else 1
    return f"{today}-v{new_version}"
