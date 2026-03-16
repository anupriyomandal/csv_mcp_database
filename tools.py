"""
tools.py — CSV Database Operations using Pandas

This module contains the core business logic for performing CRUD operations
on a CSV file (db.csv). These functions are called by the MCP server tools
when the LLM decides to invoke them based on the user's natural language input.

MCP Concept: These are the actual "tool implementations". The MCP server (server.py)
wraps each of these functions as an MCP tool so the LLM can discover and invoke them.
"""

import os
import pandas as pd

# Path to the CSV database file
DB_PATH = os.path.join(os.path.dirname(__file__), "db.csv")

# Column definitions for the database
COLUMNS = ["name", "age", "city"]


def _load_db() -> pd.DataFrame:
    """
    Load the CSV database into a pandas DataFrame.

    If the file does not exist, create it with the correct columns.

    Returns:
        pd.DataFrame: The current state of the database.
    """
    if not os.path.exists(DB_PATH):
        # Create an empty CSV with the correct headers if it doesn't exist
        df = pd.DataFrame(columns=COLUMNS)
        df.to_csv(DB_PATH, index=False)
        return df

    return pd.read_csv(DB_PATH)


def _save_db(df: pd.DataFrame) -> None:
    """
    Save the given DataFrame back to the CSV file.

    Args:
        df: The DataFrame to persist.
    """
    df.to_csv(DB_PATH, index=False)


def create_person(name: str, age: int, city: str) -> str:
    """
    Add a new person record to the CSV database.

    Loads the existing data, appends the new row, and saves it back.
    Prevents duplicate entries by checking if the name already exists.

    Args:
        name: Full name of the person to add.
        age:  Age of the person (must be a positive integer).
        city: City where the person lives.

    Returns:
        A human-readable string describing the result of the operation.
    """
    df = _load_db()

    # Guard against duplicate names (case-insensitive check)
    if df["name"].str.lower().eq(name.lower()).any():
        return f"⚠️  A person named '{name}' already exists in the database."

    # Build the new row and concatenate
    new_row = pd.DataFrame([{"name": name, "age": int(age), "city": city}])
    df = pd.concat([df, new_row], ignore_index=True)

    _save_db(df)
    return f"✅  Successfully added: {name}, age {age}, from {city}."


def list_people(city: str | None = None) -> list[dict]:
    """
    Retrieve all person records from the CSV database.

    Optionally filter by city. Returns a list of dictionaries suitable for
    display or further processing by the LLM.

    Args:
        city: Optional city name to filter results. If None, return all records.

    Returns:
        A list of dicts, each representing one person record.
        Returns an empty list if no matching records exist.
    """
    df = _load_db()

    if city:
        # Case-insensitive city filter
        df = df[df["city"].str.lower() == city.lower()]

    # Convert age column to native int for clean JSON serialisation
    df["age"] = df["age"].astype(int)

    return df.to_dict(orient="records")


def update_person(
    name: str,
    age: int | None = None,
    city: str | None = None,
) -> str:
    """
    Update an existing person's age and/or city in the CSV database.

    At least one of `age` or `city` must be provided. The lookup is
    case-insensitive on the name field.

    Args:
        name: The name of the person whose record should be updated.
        age:  New age value. Pass None to leave unchanged.
        city: New city value. Pass None to leave unchanged.

    Returns:
        A human-readable string describing the outcome of the update.
    """
    if age is None and city is None:
        return "⚠️  Nothing to update — please provide at least an age or city."

    df = _load_db()

    # Locate the row using a case-insensitive match
    mask = df["name"].str.lower() == name.lower()

    if not mask.any():
        return f"❌  No person named '{name}' found in the database."

    if age is not None:
        df.loc[mask, "age"] = int(age)
    if city is not None:
        df.loc[mask, "city"] = city

    _save_db(df)

    updated_fields = []
    if age is not None:
        updated_fields.append(f"age → {age}")
    if city is not None:
        updated_fields.append(f"city → {city}")

    return f"✅  Updated '{name}': {', '.join(updated_fields)}."


def delete_person(name: str) -> str:
    """
    Delete a person record from the CSV database by name.

    The lookup is case-insensitive. If no matching record exists the
    function returns a friendly error message rather than raising.

    Args:
        name: The name of the person to remove from the database.

    Returns:
        A human-readable string confirming deletion or reporting the error.
    """
    df = _load_db()

    mask = df["name"].str.lower() == name.lower()

    if not mask.any():
        return f"❌  No person named '{name}' found in the database."

    df = df[~mask]
    _save_db(df)

    return f"✅  Successfully deleted the record for '{name}'."
