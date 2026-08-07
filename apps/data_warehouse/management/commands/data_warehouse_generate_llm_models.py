from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import models
from apps.data_warehouse.publication import get_publication_table_specs


class Command(BaseCommand):
    help = "Generate a models.py file for the LLM data warehouse agent, derived from models defining data_warehouse_fields."

    def add_arguments(self, parser):
        parser.add_argument(
            "-o",
            "--output",
            type=str,
            help="Path to save the generated models.py file.",
        )

    def handle(self, *args, **options):
        output_file = options.get("output")
        generated_code = self.generate_models_code()

        if output_file:
            with open(output_file, "w") as f:
                f.write(generated_code)
            self.stdout.write(
                self.style.SUCCESS(f"Models.py file generated at {output_file}")
            )
        else:
            self.stdout.write(generated_code)

    def generate_models_code(self) -> str:
        models_definition = [
            "# Auto-generated models.py for Data Warehouse Agent project.",
            "# Generated from publish_mdm repo from publication.py specs via `uv run manage.py data_warehouse_generate_llm_models -o <file_name>.py`",
            "# Once <file_name>.py is generated, copy it over to `apps/vr/models.py`.",
            "# Model fields are derived directly from the `data_warehouse_fields` definitions in publish_mdm project.",
            "",
            "from django.db import models",
            "",
            "",
        ]

        # Use get_models(include_auto_created=True) so auto-created M2M models are included.
        all_models = apps.get_models(include_auto_created=True)
        table_specs = get_publication_table_specs(apps.get_models())

        if not table_specs:
            return "# No tables found for publication."

        model_map = {
            (model._meta.app_label, model._meta.db_table): model for model in all_models
        }

        rendered_tables = set()

        for spec in table_specs:
            # Prevent duplicate model generation if M2M tables are referenced twice
            if spec.table_name in rendered_tables:
                continue

            model = model_map.get((spec.app_name, spec.table_name))
            if not model:
                model = next((app_model for app_model in all_models if app_model._meta.db_table == spec.table_name), None)

            if not model:
                models_definition.append(f"# Warning: Could not find model for table '{spec.table_name}'")
                continue

            model_code = self._render_model(model, spec.columns)
            models_definition.append(model_code)
            models_definition.append("\n")
            rendered_tables.add(spec.table_name)

        return "\n".join(models_definition)

    def _resolve_field_and_var_name(self, model: type[models.Model], col_spec: str):
        """
        Maps a column name from PubTable.columns to its matching field on the django model,
        returning the field object along with the output variable name.
        """
        for field in model._meta.concrete_fields:
            if field.is_relation:
                # Matches either relation name ('user') or DB attribute ('user_id')
                if col_spec in (field.name, field.attname, field.column):
                    return field, field.attname, field.column
            else:
                if col_spec in (field.name, field.column):
                    return field, field.name, field.column

        return None, None, None

    def _render_model(self, model: type[models.Model], spec_columns: tuple[str, ...] | None) -> str:
        """Generates the Python code string for a single Django model class."""
        class_name = model.__name__
        db_table = model._meta.db_table

        model_class_definition = [
            f"class {class_name}(models.Model):",
        ]

        # Use model._meta.concrete_fields to iterate ONLY over actual DB columns
        if spec_columns is None:
            field_specs = []
            for model_field in model._meta.concrete_fields:
                if model_field.is_relation:
                    field_specs.append(model_field.attname)
                else:
                    field_specs.append(model_field.name)
        else:
            field_specs = list(spec_columns)

        exported_any_field = False

        for col_spec in field_specs:
            field, var_name, db_column = self._resolve_field_and_var_name(model, col_spec)

            if not field:
                model_class_definition.append(f"    # Warning: Field or column '{col_spec}' not found on model meta.")
                continue

            field_def = self._render_field(field, var_name, db_column)
            model_class_definition.append(f"    {var_name} = {field_def}")
            exported_any_field = True

        if not exported_any_field:
            model_class_definition.append("    pass")

        model_class_definition.append("")
        model_class_definition.append("    class Meta:")
        model_class_definition.append(f'        db_table = "{db_table}"')
        model_class_definition.append("        managed = True")

        return "\n".join(model_class_definition)

    def _get_base_django_field_name(self, field: models.Field) -> str:
        """Translates custom fields to standard django.db.models fields."""
        if hasattr(models, field.__class__.__name__):
            return f"models.{field.__class__.__name__}"

        internal_type = field.get_internal_type()
        if hasattr(models, internal_type):
            return f"models.{internal_type}"

        fallback_map = {
            "NullBooleanField": "models.BooleanField",
        }
        return fallback_map.get(internal_type, "models.TextField")

    def _render_field(self, field: models.Field, var_name: str, db_column: str) -> str:
        """Reconstruct a standard Django Field definition string for LLM data warehouse agent project."""
        kwargs = {}

        # Foreign Keys are output as flat Integer or BigInteger fields
        if field.is_relation:
            target_type = field.target_field.get_internal_type() if hasattr(field, "target_field") else "IntegerField"
            field_class_name = "models.BigIntegerField" if "Big" in target_type else "models.IntegerField"
            kwargs["null"] = getattr(field, "null", False)
            kwargs["blank"] = True
        else:
            field_class_name = self._get_base_django_field_name(field)
            if getattr(field, "max_length", None) is not None:
                kwargs["max_length"] = field.max_length
            if getattr(field, "null", False):
                kwargs["null"] = True
            if getattr(field, "blank", False):
                kwargs["blank"] = True
            if getattr(field, "decimal_places", None) is not None:
                kwargs["decimal_places"] = field.decimal_places
            if getattr(field, "max_digits", None) is not None:
                kwargs["max_digits"] = field.max_digits

        if field.primary_key:
            kwargs["primary_key"] = True

        # Explicit db_column override if Python var_name differs from PostgreSQL column
        if db_column and db_column != var_name:
            kwargs["db_column"] = f'"{db_column}"'

        kwargs_str = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        return f"{field_class_name}({kwargs_str})"