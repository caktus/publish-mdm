import pytest

from tests.publish_mdm.factories import OrganizationFactory


@pytest.fixture
def organization():
    return OrganizationFactory()
