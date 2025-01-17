from apps.odk_publish.etl.transform import group_by_common_prefixes


def test_group_by_common_prefixes():
    strings = ["staff_registration_10000", "staff_registration_10001", "staff_training_10000"]
    prefixes = group_by_common_prefixes(strings)
    assert prefixes.keys() == {"staff_registration", "staff_training"}
    assert prefixes["staff_registration"] == [
        "staff_registration_10000",
        "staff_registration_10001",
    ]
    assert prefixes["staff_training"] == ["staff_training_10000"]
