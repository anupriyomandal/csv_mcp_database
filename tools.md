# MCP Tool Reference — CSV Database 🛠️

> Detailed documentation for all four MCP tools exposed by `server.py`.
> These tools are discovered automatically by the client at startup and made available to the LLM.

---

## Table of Contents

1. [Overview](#1-overview)
2. [How Tools Are Registered](#2-how-tools-are-registered)
3. [Tool: `add_person`](#3-tool-add_person)
4. [Tool: `get_people`](#4-tool-get_people)
5. [Tool: `modify_person`](#5-tool-modify_person)
6. [Tool: `remove_person`](#6-tool-remove_person)
7. [Tool Discovery Schema](#7-tool-discovery-schema)
8. [Shared Behaviour](#8-shared-behaviour)
9. [Error Messages Reference](#9-error-messages-reference)

---

## 1. Overview

| Tool | Operation | Underlying Function | Trigger Phrase Examples |
|---|---|---|---|
| `add_person` | **Create** | `tools.create_person()` | "add Raj age 30 city Delhi" |
| `get_people` | **Read** | `tools.list_people()` | "show all users", "list people from Mumbai" |
| `modify_person` | **Update** | `tools.update_person()` | "update Raj age 31", "change Rahul's city" |
| `remove_person` | **Delete** | `tools.delete_person()` | "delete Rahul", "remove Raj" |

Each tool is a thin MCP wrapper around the pandas logic in `tools.py`. The separation means:
- `tools.py` can be tested in isolation without any MCP infrastructure
- Swapping the database backend (e.g., CSV → SQLite) requires changes only in `tools.py`

---

## 2. How Tools Are Registered

Tools are registered using the `@mcp.tool()` decorator from `FastMCP`:

```python
from mcp.server.fastmcp import FastMCP
mcp = FastMCP("CSV Database")

@mcp.tool()
def add_person(name: str, age: int, city: str) -> str:
    """...(docstring seen by the LLM)..."""
    return create_person(name=name, age=age, city=city)
```

FastMCP does three things automatically:

1. **Generates a JSON Schema** from the Python type annotations (`str`, `int`, `str | None`, etc.)
2. **Exposes the docstring** as the tool description served during Tool Discovery (`list_tools`)
3. **Routes incoming `call_tool` requests** to the correct function at runtime

The server runs on **stdio transport** — it reads JSON-RPC messages from `stdin` and writes responses to `stdout`. No network port is needed.

---

## 3. Tool: `add_person`

### Purpose

Inserts a new row into `db.csv`. This is the **Create** operation in CRUD.

### Registration (server.py)

```python
@mcp.tool()
def add_person(name: str, age: int, city: str) -> str:
```

### Parameters

| Parameter | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `name` | `string` | ✅ | Must be unique (case-insensitive) | Full name of the person to add |
| `age` | `integer` | ✅ | Must be a whole number | Age of the person in years |
| `city` | `string` | ✅ | Free text | City where the person currently lives |

### What it does internally (`tools.create_person`)

```python
def create_person(name: str, age: int, city: str) -> str:
    df = _load_db()                              # 1. Load db.csv into a DataFrame

    # 2. Check for duplicates (case-insensitive)
    if df["name"].str.lower().eq(name.lower()).any():
        return f"⚠️  A person named '{name}' already exists."

    # 3. Append the new row
    new_row = pd.DataFrame([{"name": name, "age": int(age), "city": city}])
    df = pd.concat([df, new_row], ignore_index=True)

    _save_db(df)                                 # 4. Write back to db.csv
    return f"✅  Successfully added: {name}, age {age}, from {city}."
```

**Step-by-step:**
1. Load the entire CSV into a pandas DataFrame
2. Scan the `name` column for a case-insensitive match to prevent duplicates
3. If no duplicate exists, create a one-row DataFrame and concatenate it
4. Write the updated DataFrame back to `db.csv`

### Return value

| Scenario | Return string |
|---|---|
| Success | `"✅ Successfully added: Raj, age 30, from Delhi."` |
| Duplicate name | `"⚠️ A person named 'Raj' already exists in the database."` |

### Natural language triggers

The LLM uses these example phrases from the docstring to identify when to call this tool:

```
"pls create a new user with name Raj age 30 city Delhi"
"add a person Rahul age 28 city Mumbai"
"insert a new person named Alice, she is 25 and lives in Pune"
"add user Bob, 35, from Chennai"
"create a record for Priya, age 22, city Kolkata"
```

### Example JSON-RPC call (what the client sends to the server)

```json
{
  "jsonrpc": "2.0",
  "method": "tools/call",
  "params": {
    "name": "add_person",
    "arguments": {
      "name": "Raj",
      "age": 30,
      "city": "Delhi"
    }
  },
  "id": 1
}
```

### Effect on db.csv

Before:
```csv
name,age,city
Rahul,28,Mumbai
```

After:
```csv
name,age,city
Rahul,28,Mumbai
Raj,30,Delhi
```

---

## 4. Tool: `get_people`

### Purpose

Reads and returns rows from `db.csv`. This is the **Read** operation in CRUD. Supports optional city-level filtering.

### Registration (server.py)

```python
@mcp.tool()
def get_people(city: str | None = None) -> list[dict]:
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `city` | `string` or `null` | ❌ | `null` | If provided, only return people from this city (case-insensitive). If omitted or `null`, return all records. |

### What it does internally (`tools.list_people`)

```python
def list_people(city: str | None = None) -> list[dict]:
    df = _load_db()              # 1. Load db.csv

    if city:
        # 2. Apply case-insensitive city filter if requested
        df = df[df["city"].str.lower() == city.lower()]

    df["age"] = df["age"].astype(int)   # 3. Ensure age is a Python int
    return df.to_dict(orient="records") # 4. Return as list of dicts
```

**Step-by-step:**
1. Load the CSV into a DataFrame
2. If `city` is provided, filter rows where the city matches (case-insensitive)
3. Cast `age` to native Python `int` for clean JSON serialisation
4. Convert each row to a dictionary and return the list

### Return value

A **list of dictionaries**, one per matching person:

```json
[
  {"name": "Raj",   "age": 30, "city": "Delhi"},
  {"name": "Rahul", "age": 28, "city": "Mumbai"}
]
```

Returns an **empty list `[]`** if:
- The database is empty
- No records match the city filter

### Rendering in the CLI

`client.py` detects that the LLM response contains a JSON array and renders it as a `rich` table:

```
╭───────┬─────┬────────╮
│ Name  │ Age │ City   │
├───────┼─────┼────────┤
│ Raj   │  30 │ Delhi  │
│ Rahul │  28 │ Mumbai │
╰───────┴─────┴────────╯
```

### Natural language triggers

```
"show all users"
"list everyone in the database"
"who is in the database?"
"how many people are there?"
"list people from Delhi"
"show me all users from Mumbai"
"get everyone from Pune"
"display all records"
```

### Counting behaviour

For queries like *"how many people are there?"*, the LLM calls `get_people` once to retrieve the full list, then counts the items in the returned list itself — it does **not** call the tool multiple times.

### Effect on db.csv

`get_people` is **read-only** — it never writes to `db.csv`.

---

## 5. Tool: `modify_person`

### Purpose

Updates an existing person's `age` and/or `city`. This is the **Update** operation in CRUD. At least one field must be provided.

### Registration (server.py)

```python
@mcp.tool()
def modify_person(name: str, age: int | None = None, city: str | None = None) -> str:
```

### Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | `string` | ✅ | — | Name of the person to update. Lookup is case-insensitive. |
| `age` | `integer` or `null` | ❌ | `null` | New age value. Omit to leave the current age unchanged. |
| `city` | `string` or `null` | ❌ | `null` | New city value. Omit to leave the current city unchanged. |

> **Rule:** At least one of `age` or `city` must be non-null. If both are omitted, the tool returns an error without touching `db.csv`.

### What it does internally (`tools.update_person`)

```python
def update_person(name, age=None, city=None) -> str:
    if age is None and city is None:
        return "⚠️  Nothing to update — please provide at least an age or city."

    df = _load_db()              # 1. Load db.csv

    # 2. Locate the row (case-insensitive name match)
    mask = df["name"].str.lower() == name.lower()

    if not mask.any():
        return f"❌  No person named '{name}' found."

    # 3. Apply changes only to specified fields
    if age is not None:
        df.loc[mask, "age"] = int(age)
    if city is not None:
        df.loc[mask, "city"] = city

    _save_db(df)                 # 4. Write back to db.csv

    # 5. Build a readable summary of what changed
    updated_fields = []
    if age is not None:  updated_fields.append(f"age → {age}")
    if city is not None: updated_fields.append(f"city → {city}")
    return f"✅  Updated '{name}': {', '.join(updated_fields)}."
```

**Step-by-step:**
1. Validate that at least one field is being changed
2. Load the CSV; find the row with a case-insensitive name match
3. Update only the fields that were provided (partial update support)
4. Save the changed DataFrame back to disk
5. Return a human-readable summary of what changed

### Return value

| Scenario | Return string |
|---|---|
| Age updated | `"✅ Updated 'Raj': age → 31."` |
| City updated | `"✅ Updated 'Rahul': city → Bangalore."` |
| Both updated | `"✅ Updated 'Alice': age → 26, city → Hyderabad."` |
| Person not found | `"❌ No person named 'Unknown' found in the database."` |
| No fields provided | `"⚠️ Nothing to update — please provide at least an age or city."` |

### Natural language triggers

```
"update Raj age 31"
"change Rahul's city to Bangalore"
"update Alice, she moved to Hyderabad"
"Raj's age is now 32"
"set Priya's age to 23 and city to Jaipur"
"edit Bob's record — city should be Surat"
```

### Effect on db.csv

Before (`update Rahul age 29`):
```csv
name,age,city
Raj,30,Delhi
Rahul,28,Mumbai
```

After:
```csv
name,age,city
Raj,30,Delhi
Rahul,29,Mumbai
```

---

## 6. Tool: `remove_person`

### Purpose

Permanently deletes a person's row from `db.csv`. This is the **Delete** operation in CRUD.

### Registration (server.py)

```python
@mcp.tool()
def remove_person(name: str) -> str:
```

### Parameters

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | `string` | ✅ | Name of the person to delete. Lookup is case-insensitive. |

### What it does internally (`tools.delete_person`)

```python
def delete_person(name: str) -> str:
    df = _load_db()              # 1. Load db.csv

    # 2. Locate the row (case-insensitive)
    mask = df["name"].str.lower() == name.lower()

    if not mask.any():
        return f"❌  No person named '{name}' found."

    df = df[~mask]               # 3. Drop the matching row(s)
    _save_db(df)                 # 4. Write back to db.csv

    return f"✅  Successfully deleted the record for '{name}'."
```

**Step-by-step:**
1. Load the full CSV
2. Create a boolean mask for rows where the name matches (case-insensitive)
3. Use the inverted mask (`~mask`) to keep all rows *except* the deleted one
4. Save the filtered DataFrame back to `db.csv`

### Return value

| Scenario | Return string |
|---|---|
| Success | `"✅ Successfully deleted the record for 'Rahul'."` |
| Not found | `"❌ No person named 'Rahul' found in the database."` |

> ⚠️ **Deletion is permanent.** There is no undo. The row is removed from `db.csv` immediately.

### Natural language triggers

```
"delete Rahul"
"remove Raj from the database"
"delete the record for Alice"
"erase Bob's entry"
"wipe Priya's data"
```

### Effect on db.csv

Before (`delete Rahul`):
```csv
name,age,city
Raj,30,Delhi
Rahul,28,Mumbai
```

After:
```csv
name,age,city
Raj,30,Delhi
```

---

## 7. Tool Discovery Schema

When the client calls `session.list_tools()`, the MCP server responds with a schema like this for each tool. This is exactly what the LLM receives to understand what tools exist:

```json
{
  "tools": [
    {
      "name": "add_person",
      "description": "Add a new person to the CSV database.\n\nUse this tool when the user wants to insert a new record...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "name": { "type": "string",  "title": "Name" },
          "age":  { "type": "integer", "title": "Age"  },
          "city": { "type": "string",  "title": "City" }
        },
        "required": ["name", "age", "city"]
      }
    },
    {
      "name": "get_people",
      "description": "Retrieve all people stored in the CSV database...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "city": { "anyOf": [{"type": "string"}, {"type": "null"}], "title": "City", "default": null }
        }
      }
    },
    {
      "name": "modify_person",
      "description": "Update an existing person's age and/or city...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "name": { "type": "string" },
          "age":  { "anyOf": [{"type": "integer"}, {"type": "null"}], "default": null },
          "city": { "anyOf": [{"type": "string"},  {"type": "null"}], "default": null }
        },
        "required": ["name"]
      }
    },
    {
      "name": "remove_person",
      "description": "Delete a person's record from the CSV database...",
      "inputSchema": {
        "type": "object",
        "properties": {
          "name": { "type": "string" }
        },
        "required": ["name"]
      }
    }
  ]
}
```

In `client.py`, each tool's schema is converted to OpenAI's function-calling format via `mcp_tool_to_openai()`:

```python
def mcp_tool_to_openai(tool) -> dict:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.inputSchema,
        },
    }
```

---

## 8. Shared Behaviour

All four tools share these behaviours:

### File I/O on every call

Every call to a tool does a **full read → modify → write** cycle on `db.csv`:

```
_load_db()  →  pd.read_csv("db.csv")
              ... operation ...
_save_db(df) →  df.to_csv("db.csv", index=False)
```

This is simple and reliable for small datasets. For large datasets, a proper database (SQLite, PostgreSQL) would be more appropriate.

### Auto-creation of db.csv

`_load_db()` creates `db.csv` with the correct headers if it doesn't exist:

```python
if not os.path.exists(DB_PATH):
    df = pd.DataFrame(columns=["name", "age", "city"])
    df.to_csv(DB_PATH, index=False)
    return df
```

### Case-insensitive name lookups

All operations that search by name (`modify_person`, `remove_person`, `create_person` duplicate check) use `.str.lower()` for comparison. So `"raj"`, `"Raj"`, and `"RAJ"` all refer to the same record.

### Return values are human-readable strings

Tool return values are plain English strings designed to be read and summarised by the LLM. The LLM then paraphrases or passes them through to the user.

---

## 9. Error Messages Reference

| Situation | Tool | Message |
|---|---|---|
| Duplicate name on create | `add_person` | `"⚠️ A person named '{name}' already exists in the database."` |
| Name not found on update | `modify_person` | `"❌ No person named '{name}' found in the database."` |
| No fields to update | `modify_person` | `"⚠️ Nothing to update — please provide at least an age or city."` |
| Name not found on delete | `remove_person` | `"❌ No person named '{name}' found in the database."` |
| Empty result set | `get_people` | Returns `[]` (empty list) |
