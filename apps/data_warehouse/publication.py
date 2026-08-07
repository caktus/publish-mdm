from dataclasses import dataclass

from django.db import connection
from django.db.models import Model

PUBLICATION_NAME = "data_warehouse_pub"
PUBLICATION_SQL_TEMPLATE = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_publication
        WHERE pubname = '{publication_name}'
    )
    THEN
        CREATE PUBLICATION {publication_name};
    END IF;
END $$;

ALTER PUBLICATION {publication_name} SET TABLE {table_list};
""".strip()
STATUS_PUBLICATION_SQL = f"SELECT pubname FROM pg_publication WHERE pubname = '{PUBLICATION_NAME}';"
STATUS_REPLICATION_SQL = (
    "SELECT application_name, client_addr, state, sync_state FROM pg_stat_replication;"
)


@dataclass(frozen=True)
class PubTable:
    """A table spec for publication."""

    app_name: str
    table_name: str
    columns: tuple[str, ...] | None

    def as_sql_target(self) -> str:
        """Format the table spec as a SQL target for the publication.

        Example: 'app_table (col1, col2)'.
        """
        if self.columns is None:
            return self.table_name
        columns = ", ".join(f'"{column}"' for column in self.columns)
        return f"{self.table_name} ({columns})"


def get_publication_table_specs(models: list[type[Model]]) -> list[PubTable]:
    """Build publication table specifications from models with data_warehouse_fields.

    Also includes auto-created M2M through tables for M2M fields that are part of
    data_warehouse_fields. Custom through tables (with their own model class) must
    define data_warehouse_fields on their own to be included.
    """
    table_specs = []
    for model in models:
        fields = getattr(model, "data_warehouse_fields", None)
        if fields is None:
            continue
        columns = tuple(fields) if fields != "__all__" else None
        table_specs.append(
            PubTable(
                app_name=model._meta.app_label, table_name=model._meta.db_table, columns=columns
            )
        )

        # Include auto-created M2M through tables
        _add_auto_created_m2m_tables(model, fields, table_specs)

    return table_specs


def _add_auto_created_m2m_tables(model, data_warehouse_fields, table_specs: list[PubTable]):
    """Add auto-generated M2M through tables whose parent field is in data_warehouse_fields.

    Only auto-created through models are handled here. Custom through tables
    (defined with a through= model) are regular models and must define
    data_warehouse_fields on their own to be replicated.
    """
    for m2m_field in model._meta.many_to_many:
        if not m2m_field.remote_field.through._meta.auto_created:
            # Custom through table — skip; it needs its own data_warehouse_fields
            continue

        included = data_warehouse_fields == "__all__" or (
            isinstance(data_warehouse_fields, (list, tuple))
            and m2m_field.name in data_warehouse_fields
        )
        if not included:
            continue

        through_model = m2m_field.remote_field.through

        table_specs.append(
            PubTable(
                app_name=through_model._meta.app_label,
                table_name=through_model._meta.db_table,
                columns=None,  # All columns
            )
        )


def get_publication_sql(table_specs: list[PubTable]) -> str:
    """Build the SQL needed to create and update the data warehouse publication."""
    table_list = ", \n".join(spec.as_sql_target() for spec in table_specs)
    return PUBLICATION_SQL_TEMPLATE.format(publication_name=PUBLICATION_NAME, table_list=table_list)


def refresh_publication(table_specs: list[PubTable], dry_run: bool = False) -> str | None:
    """Execute the publication SQL for the given table specs.

    Returns the SQL when dry_run is True.
    """
    sql = get_publication_sql(table_specs=table_specs)
    if dry_run:
        return sql
    with connection.cursor() as cursor:
        cursor.execute(sql)
    return None


def get_publication_status_messages() -> list[tuple[str, bool]]:
    """Check publication status and return messages with success flags."""
    with connection.cursor() as cursor:
        cursor.execute(STATUS_PUBLICATION_SQL)
        publication = cursor.fetchone()
        cursor.execute(STATUS_REPLICATION_SQL)
        replication_rows = cursor.fetchall()

    messages: list[tuple[str, bool]] = []
    if publication:
        messages.append((f"Publication '{PUBLICATION_NAME}' exists.", True))
    else:
        messages.append((f"Publication '{PUBLICATION_NAME}' does not exist.", False))

    if replication_rows:
        messages.append(("Replication connections:", True))
        for application_name, client_addr, state, sync_state in replication_rows:
            messages.append(
                (
                    f"  {application_name} | {client_addr} | {state} | {sync_state}",
                    True,
                )
            )
    else:
        messages.append(("No active replication connections found.", False))

    return messages
