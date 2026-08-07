import logging

from django.apps import apps
from django.core.management.base import BaseCommand

from apps.data_warehouse.publication import (
    PUBLICATION_NAME,
    get_publication_status_messages,
    get_publication_table_specs,
    refresh_publication,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Create or update a PostgreSQL publication for data warehouse replication."

    def add_arguments(self, parser):
        parser.add_argument(
            "--status",
            action="store_true",
            help="Show publication and replication status without making changes.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the SQL without executing it.",
        )

    def handle(self, *args, **options):
        if options["status"]:
            self._show_status()
            return

        table_specs = get_publication_table_specs(apps.get_models(include_auto_created=True))
        if not table_specs:
            self.stderr.write("No models with data_warehouse_fields found.")
            return

        sql = refresh_publication(table_specs, dry_run=options["dry_run"])

        if options["dry_run"]:
            self.stdout.write(sql)
            return

        self.stdout.write(self.style.SUCCESS(f"Publication '{PUBLICATION_NAME}' configured."))
        for spec in table_specs:
            self.stdout.write(f"  {spec.as_sql_target()}")

    def _show_status(self):
        for message, is_success in get_publication_status_messages():
            style = self.style.SUCCESS if is_success else self.style.ERROR
            self.stdout.write(style(message))
