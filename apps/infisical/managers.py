from django.db import connections, models

from .fields import EncryptedMixin


class EncryptedQuery(models.sql.Query):
    """A Query that decrypts encrypted values after fetching them from the DB."""

    def get_compiler(self, using=None, connection=None, elide_empty=True):
        """Get an SQLCompiler that decrypts encrypted values."""
        if using is None and connection is None:
            raise ValueError("Need either using or connection")
        if using:
            connection = connections[using]

        # Create a subclass of the default compiler for the connection
        class EncryptedQueryCompiler(connection.ops.compiler(self.compiler)):
            def get_select(self, with_col_aliases=False):
                ret, klass_info, annotations = super().get_select(with_col_aliases)
                # Change the output_field on the encrypted columns.
                # It defaults to model.TextField(), which doesn't decrypt.
                updated_ret = []
                for col, (sql, params), alias in ret:
                    if isinstance(col.target, EncryptedMixin):
                        col = col.target.get_col(col.alias, output_field=col.target)
                    updated_ret.append((col, (sql, params), alias))
                return updated_ret, klass_info, annotations

        return EncryptedQueryCompiler(self, connection, using, elide_empty)


class EncryptedManager(models.Manager):
    """A manager that decrypts encrypted values after fetching them from the DB."""

    def get_queryset(self):
        return models.QuerySet(self.model, query=EncryptedQuery(self.model), using=self._db)
