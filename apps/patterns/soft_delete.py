from django.db import models
from django.utils import timezone


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet mixin with soft-delete and restore helpers."""

    def active(self):
        return self.filter(deleted_at__isnull=True)

    def deleted(self):
        return self.filter(deleted_at__isnull=False)

    def soft_delete(self):
        return self.update(deleted_at=timezone.now())

    def restore(self):
        return self.update(deleted_at=None)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Manager that returns all rows, including soft-deleted ones."""


class ActiveManager(AllObjectsManager):
    """Default manager - returns only non-deleted rows."""

    def get_queryset(self):
        return super().get_queryset().active()


class SoftDeleteModel(models.Model):
    """Abstract mixin that adds soft-delete support to a model.

    Apply by listing this class before other base models so its default manager
    takes precedence::

        class MyModel(SoftDeleteModel, AbstractBaseModel):
            ...

    ``objects`` (the default manager) excludes soft-deleted rows.
    ``all_objects`` includes every row regardless of deletion state.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = ActiveManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark this row as deleted without removing it from the database."""
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def restore(self) -> None:
        """Un-delete this row, making it visible to the default manager again."""
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])
