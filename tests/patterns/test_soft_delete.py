import pytest
from django.utils.timezone import now

from apps.infisical.api import InfisicalKMS
from apps.mdm.models import Device
from tests.mdm.factories import DeviceFactory
from tests.publish_mdm.factories import OrganizationFactory


@pytest.fixture(autouse=True)
def disable_infisical_encryption(mocker):
    # Never attempt to encrypt/decrypt with Infisical
    def side_effect(key_name, value):
        # Return the value unchanged
        return value

    mocker.patch.object(InfisicalKMS, "encrypt", side_effect=side_effect)
    mocker.patch.object(InfisicalKMS, "decrypt", side_effect=side_effect)


@pytest.fixture
def organization():
    return OrganizationFactory()


@pytest.mark.django_db
class TestSoftDeleteModel:
    """Tests for SoftDeleteModel abstract mixin, exercised via the concrete Device model."""

    @pytest.fixture
    def device(self, organization):
        return DeviceFactory(fleet__organization=organization)

    # --- is_deleted property ---

    def test_is_deleted_false_by_default(self, device):
        assert device.is_deleted is False

    def test_is_deleted_true_after_soft_delete(self, device):
        device.soft_delete()
        assert device.is_deleted is True

    # --- soft_delete(commit=True) ---

    def test_soft_delete_sets_deleted_at_in_db(self, device):
        before = now()
        device.soft_delete()
        device.refresh_from_db()
        assert device.deleted_at is not None
        assert device.deleted_at >= before

    # --- soft_delete(commit=False) ---

    def test_soft_delete_commit_false_sets_attribute_but_not_db(self, device):
        device.soft_delete(commit=False)
        assert device.deleted_at is not None  # set in memory
        fresh = Device.all_objects.get(pk=device.pk)
        assert fresh.deleted_at is None  # not yet in DB

    def test_soft_delete_commit_false_then_bulk_update_persists(self, device):
        device.soft_delete(commit=False)
        Device.all_objects.filter(pk=device.pk).update(deleted_at=device.deleted_at)
        device.refresh_from_db()
        assert device.deleted_at is not None

    # --- restore() ---

    def test_restore_clears_deleted_at(self, device):
        device.soft_delete()
        device.restore()
        device.refresh_from_db()
        assert device.deleted_at is None
        assert device.is_deleted is False

    # --- objects manager (active only) ---

    def test_objects_excludes_soft_deleted(self, device):
        device.soft_delete()
        assert not Device.objects.filter(pk=device.pk).exists()

    def test_objects_includes_active(self, device):
        assert Device.objects.filter(pk=device.pk).exists()

    # --- all_objects manager ---

    def test_all_objects_includes_soft_deleted(self, device):
        device.soft_delete()
        assert Device.all_objects.filter(pk=device.pk).exists()

    # --- SoftDeleteQuerySet bulk helpers ---

    def test_queryset_soft_delete_sets_deleted_at(self, organization):
        devices = DeviceFactory.create_batch(3, fleet__organization=organization)
        pks = [d.pk for d in devices]
        Device.objects.filter(pk__in=pks).soft_delete()
        assert Device.objects.filter(pk__in=pks).count() == 0
        assert Device.all_objects.filter(pk__in=pks, deleted_at__isnull=False).count() == 3

    def test_queryset_restore_clears_deleted_at(self, organization):
        devices = DeviceFactory.create_batch(3, fleet__organization=organization)
        pks = [d.pk for d in devices]
        Device.all_objects.filter(pk__in=pks).soft_delete()
        Device.all_objects.filter(pk__in=pks).restore()
        assert Device.objects.filter(pk__in=pks).count() == 3

    def test_queryset_active_filters_correctly(self, organization):
        active = DeviceFactory(fleet__organization=organization)
        deleted = DeviceFactory(fleet__organization=organization)
        deleted.soft_delete()
        qs = Device.all_objects.filter(pk__in=[active.pk, deleted.pk]).active()
        assert list(qs) == [active]

    def test_queryset_deleted_filters_correctly(self, organization):
        active = DeviceFactory(fleet__organization=organization)
        deleted = DeviceFactory(fleet__organization=organization)
        deleted.soft_delete()
        qs = Device.all_objects.filter(pk__in=[active.pk, deleted.pk]).deleted()
        assert list(qs) == [deleted]
