import dagster as dg
import sqlalchemy


class PostgresResource(dg.ConfigurableResource):
    """A resource that configures a SQLAlchemy engine."""

    database_url: str

    def engine(self) -> sqlalchemy.Engine:
        """Return a SQLAlchemy engine connected to the configured PostgreSQL database."""
        return sqlalchemy.create_engine(url=self.database_url)
