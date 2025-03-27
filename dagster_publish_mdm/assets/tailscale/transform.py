import pandas as pd


def make_snake_case(df: pd.DataFrame) -> pd.DataFrame:
    """Convert camelCase column names from API to snake_case for PostgreSQL."""
    df.columns = df.columns.str.replace("(?<=[a-z])(?=[A-Z])", "_", regex=True).str.lower()
    return df


def convert_to_datetime(df: pd.DataFrame) -> pd.DataFrame:
    """Convert columns to datetime objects."""
    df["created"] = pd.to_datetime(df["created"], utc=True)
    df["expires"] = pd.to_datetime(df["expires"], utc=True, errors="coerce")
    df["last_seen"] = pd.to_datetime(df["last_seen"], utc=True)
    return df


def extract_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Extract important columns for PostgreSQL import."""
    return df[
        [
            "addresses",
            "client_version",
            "created",
            "expires",
            "hostname",
            "last_seen",
            "name",
            "node_id",
            "os",
            "tags",
            "update_available",
            "user",
        ]
    ].copy()
