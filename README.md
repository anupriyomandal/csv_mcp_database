# CSV MCP Database 📋

> An educational command-line application demonstrating how an LLM can use **Model Context Protocol (MCP)** tools to perform CRUD operations on a CSV database through **natural language commands**.

---

## Table of Contents

1. [What is MCP?](#1-what-is-mcp)
2. [MCP Core Concepts](#2-mcp-core-concepts)
3. [Project Overview](#3-project-overview)
4. [How It Works — End to End](#4-how-it-works--end-to-end)
5. [Project Architecture](#5-project-architecture)
6. [File-by-File Reference](#6-file-by-file-reference)
7. [Database Schema](#7-database-schema)
8. [Installation](#8-installation)
9. [Configuration](#9-configuration)
10. [Running the Project](#10-running-the-project)
11. [Example Commands & Session](#11-example-commands--session)
12. [Tool Reference](#12-tool-reference)
13. [How the LLM Decides Which Tool to Call](#13-how-the-llm-decides-which-tool-to-call)
14. [How Tool Results Are Rendered](#14-how-tool-results-are-rendered)
15. [Data Integrity & Edge Cases](#15-data-integrity--edge-cases)
16. [Extending the Project](#16-extending-the-project)
17. [Troubleshooting](#17-troubleshooting)
18. [Key Learning Points](#18-key-learning-points)
19. [Glossary](#19-glossary)
20. [Dependencies](#20-dependencies)

---

## 1. What is MCP?

**Model Context Protocol (MCP)** is an open standard originally developed by Anthropic that defines a structured way for LLMs (and AI agents) to interact with external tools, data sources, and services.

Think of it as a **universal adapter** between an AI model and the outside world:

```
┌──────────────────┐         MCP          ┌────────────────────────┐
│   LLM / Agent    │ ◄──────────────────► │  MCP Server (tools)    │
│  (the reasoner)  │   JSON-RPC over      │  (the capabilities)    │
└──────────────────┘   stdio / HTTP       └────────────────────────┘
```

### Why MCP matters

| Without MCP | With MCP |
|---|---|
| Each tool integration is custom-built | One standard interface for all tools |
| LLM and tools are tightly coupled | Clean separation — swap either side independently |
| Hard to share or reuse tools | Any MCP-compatible client can use any MCP server |
| No standard for discovery | Tool list + schemas served automatically |

MCP is transport-agnostic: tools can be exposed over **stdio** (local subprocess), **HTTP/SSE** (remote server), or other transports.

---

## 2. MCP Core Concepts

This project demonstrates three foundational MCP concepts in code.

### 2.1 Tool Exposure

**What it is:** Registering a Python function as a callable tool so the LLM can invoke it.

**How it works here:** In `server.py`, the `@mcp.tool()` decorator wraps each function:

```python
@mcp.tool()
def add_person(name: str, age: int, city: str) -> str:
    """Add a new person to the CSV database. ..."""
    return create_person(name=name, age=age, city=city)
```

FastMCP automatically:
- Reads the function signature to generate a **JSON Schema** for parameters
- Uses the **docstring** as the tool description that the LLM reads
- Registers the function to handle incoming `call_tool` requests

### 2.2 Tool Discovery

**What it is:** The client fetching the list of available tools from the server before the user types anything.

**How it works here:** In `client.py`, after connecting to the server:

```python
tools_result = await session.list_tools()
```

This returns a list of `Tool` objects, each with:
- `name` — the function identifier (`add_person`, `get_people`, etc.)
- `description` — the docstring written in `server.py`
- `inputSchema` — the JSON Schema derived from the type annotations

These are then converted to OpenAI's function-calling format and passed to the Chat Completions API, so the LLM knows exactly what tools exist and what arguments they need.

### 2.3 Tool Invocation

**What it is:** The LLM choosing to call a tool at runtime and the client executing it.

**How it works here:** When the LLM decides to call a tool, it returns a `tool_calls` object in its response. The client handles this:

```python
for tc in msg.tool_calls:
    args = json.loads(tc.function.arguments)
    tool_result = await session.call_tool(tc.function.name, args)
```

`session.call_tool()` sends a JSON-RPC `call_tool` request to the MCP server (over stdin), which routes it to the correct `@mcp.tool()` function, executes it, and returns the result.

---

## 3. Project Overview

| Attribute | Value |
|---|---|
| **Language** | Python 3.11+ |
| **LLM** | OpenAI GPT-4o-mini (Chat Completions API) |
| **MCP Library** | `mcp` (official Python SDK) |
| **MCP Server** | FastMCP with stdio transport |
| **Database** | CSV file (`db.csv`) via pandas |
| **CLI** | `rich` for formatted terminal output |
| **Config** | `python-dotenv` for API key management |

---

## 4. How It Works — End to End

```
┌─────────────────────────────────────────────────────────────┐
│                        client.py                            │
│                                                             │
│  1. Spawns server.py as a child process (stdio MCP server)  │
│  2. session.list_tools()  →  Tool Discovery                 │
│  3. Converts MCP tools → OpenAI function-calling format     │
│  4. Enters interactive CLI loop                             │
└────────────────────────┬────────────────────────────────────┘
                         │ User types natural language
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenAI Chat Completions API                     │
│                  (GPT-4o-mini)                               │
│                                                             │
│  Receives: system prompt + conversation history + tools     │
│  Decides:  which tool to call (or answer directly)          │
│  Returns:  tool_calls  OR  plain text answer                │
└────────┬──────────────────────────────────┬─────────────────┘
         │ if tool_calls present            │ if no tool_calls
         ▼                                  ▼
┌──────────────────────┐         ┌─────────────────────────┐
│  client.py           │         │  client.py              │
│                      │         │  print_agent_response() │
│  session.call_tool() │         │  → table or panel       │
│  (JSON-RPC over      │         └─────────────────────────┘
│   stdin to server)   │
└──────────┬───────────┘
           ▼
┌─────────────────────────────────────────────────────────────┐
│                        server.py                            │
│             FastMCP  (stdio JSON-RPC handler)               │
│                                                             │
│   @mcp.tool() add_person     →  tools.create_person()      │
│   @mcp.tool() get_people     →  tools.list_people()        │
│   @mcp.tool() modify_person  →  tools.update_person()      │
│   @mcp.tool() remove_person  →  tools.delete_person()      │
└──────────┬──────────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────────┐
│                        tools.py                             │
│         Pure pandas CRUD logic — no MCP dependency          │
│                                                             │
│   _load_db()    →  pd.read_csv("db.csv")                   │
│   _save_db(df)  →  df.to_csv("db.csv", index=False)        │
└──────────┬──────────────────────────────────────────────────┘
           ▼
┌─────────────────────────────────────────────────────────────┐
│                        db.csv                               │
│              name,age,city  (flat text file)                │
└─────────────────────────────────────────────────────────────┘
```

**Round-trip summary for a single tool call:**

1. User: `"add Raj age 30 city Delhi"`
2. LLM sees the `add_person` tool description → decides to call it
3. `client.py` receives `tool_calls = [{ name: "add_person", args: {name:"Raj", age:30, city:"Delhi"} }]`
4. `session.call_tool("add_person", {...})` → JSON-RPC to `server.py` stdin
5. `server.py` invokes `add_person()` → calls `create_person()` in `tools.py`
6. `tools.py` loads `db.csv`, appends the row, saves back
7. Returns `"✅ Successfully added: Raj, age 30, from Delhi."`
8. `client.py` feeds this result back to the LLM as a `tool` message
9. LLM generates a final human-readable confirmation
10. `client.py` prints it in a `rich` panel

---

## 5. Project Architecture

```
csv_mcp_database/
│
├── client.py        # Entry point — CLI loop, MCP client, LLM integration
├── server.py        # MCP server — exposes 4 CRUD tools via @mcp.tool()
├── tools.py         # Business logic — pandas read/write operations on db.csv
├── db.csv           # Flat-file database — auto-created if missing
├── .env             # Your secrets (not in version control)
├── .env.example     # Template for .env
├── requirements.txt # Python dependencies
└── README.md        # This file
```

---

## 6. File-by-File Reference

### `tools.py` — Database Logic

The lowest layer. Pure Python + pandas. Knows nothing about MCP.

| Function | Signature | Description |
|---|---|---|
| `_load_db()` | `() → DataFrame` | Reads `db.csv`; creates it with headers if missing |
| `_save_db(df)` | `(DataFrame) → None` | Overwrites `db.csv` with the given DataFrame |
| `create_person` | `(name, age, city) → str` | Appends a new row; guards against duplicates |
| `list_people` | `(city=None) → list[dict]` | Returns all rows, optionally filtered by city |
| `update_person` | `(name, age=None, city=None) → str` | Updates age/city for an existing record |
| `delete_person` | `(name) → str` | Removes the row with the matching name |

All lookups are **case-insensitive** on the `name` field.

---

### `server.py` — MCP Server

The middle layer. Wraps `tools.py` functions as MCP-discoverable tools.

**Key design choices:**

- Each `@mcp.tool()` function has a **detailed docstring** with example natural language phrases. This docstring is what the LLM reads during Tool Discovery to decide when to invoke the tool.
- The tool functions are thin wrappers — they just delegate to `tools.py`. This keeps concerns separated.
- Transport: `stdio` — the server reads JSON-RPC from stdin and writes to stdout. No network ports needed.

**How FastMCP generates the tool schema:**

```python
@mcp.tool()
def add_person(name: str, age: int, city: str) -> str:
    ...
```

FastMCP reads the type annotations and generates:
```json
{
  "name": "add_person",
  "description": "...(from docstring)...",
  "inputSchema": {
    "type": "object",
    "properties": {
      "name": { "type": "string" },
      "age":  { "type": "integer" },
      "city": { "type": "string" }
    },
    "required": ["name", "age", "city"]
  }
}
```

---

### `client.py` — CLI Agent

The top layer. Orchestrates everything.

**Startup sequence:**

```
main()
  └─ agent_loop()
       ├─ stdio_client(server_params)     # spawns server.py as subprocess
       ├─ ClientSession.initialize()      # MCP handshake
       ├─ session.list_tools()            # Tool Discovery
       ├─ mcp_tool_to_openai()            # convert schemas
       └─ interactive while loop
            ├─ console.input()            # read user text
            ├─ chat.completions.create()  # ask LLM
            ├─ if tool_calls:
            │    session.call_tool()      # Tool Invocation
            │    feed result back to LLM
            │    loop back
            └─ print_agent_response()     # render output
```

**The tool-call loop in detail:**

```python
while True:
    response = oai_client.chat.completions.create(
        model=MODEL,
        tools=openai_tools,
        messages=[system] + history,
    )
    msg = response.choices[0].message
    history.append(msg)

    if not msg.tool_calls:
        break           # ← LLM has a final answer

    for tc in msg.tool_calls:
        result = await session.call_tool(tc.function.name, json.loads(tc.function.arguments))
        history.append({ "role": "tool", "tool_call_id": tc.id, "content": result_text })
    # loop back → LLM sees the tool result and decides what to do next
```

---

### `db.csv` — Database File

A plain UTF-8 CSV file. Example:

```csv
name,age,city
Raj,30,Delhi
Rahul,28,Mumbai
Alice,25,Pune
```

- Created automatically with headers if it doesn't exist on first run.
- Can be opened and edited in any text editor or spreadsheet application.
- No locking or transactions — operations are read-modify-write on the full file.

---

### `.env` / `.env.example` — Secrets

```ini
OPENAI_API_KEY=sk-your-key-here
```

`python-dotenv` loads `.env` at startup so you never need to `export` the key in your shell.

---

### `requirements.txt` — Dependencies

```
pandas>=2.0.0       # CSV read/write and DataFrame operations
openai>=1.50.0      # Chat Completions API + function calling
mcp>=1.0.0          # MCP Python SDK (ClientSession, FastMCP, stdio_client)
rich>=13.0.0        # Terminal formatting (tables, panels, spinners)
python-dotenv>=1.0.0 # Load OPENAI_API_KEY from .env file
```

---

## 7. Database Schema

`db.csv` has exactly three columns:

| Column | Type    | Constraints | Description |
|--------|---------|-------------|-------------|
| `name` | string  | Unique (case-insensitive), required | Full name of the person |
| `age`  | integer | Positive, required | Age in years |
| `city` | string  | Required | City of residence |

### Design notes

- **`name` acts as the primary key.** Duplicate names (case-insensitive) are rejected by `create_person`.
- **No auto-increment ID.** Keeping it simple for educational purposes.
- **No NULL values.** All three fields are required for creation.
- Partial updates are supported: `update_person` accepts `age` or `city` independently.

---

## 8. Installation

### Prerequisites

- Python 3.11 or higher
- An OpenAI API key with access to `gpt-4o-mini`

### Step-by-step

**1. Navigate to the project directory**

```bash
cd /path/to/csv_mcp_database
```

**2. Create a virtual environment**

```bash
python3 -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows PowerShell
```

**3. Install all dependencies**

```bash
pip install -r requirements.txt
```

**4. Set up your API key**

```bash
cp .env.example .env
# Open .env and replace the placeholder with your real key
```

Or set it for the current shell session only:

```bash
export OPENAI_API_KEY="sk-..."
```

---

## 9. Configuration

All configuration lives in two places:

### `.env` file

```ini
OPENAI_API_KEY=sk-...   # required
```

### Top of `client.py`

```python
MODEL         = "gpt-4o-mini"   # change to gpt-4o, gpt-3.5-turbo, etc.
SERVER_SCRIPT = "server.py"     # path to the MCP server
```

### System prompt (in `client.py`)

The `SYSTEM_PROMPT` string controls the LLM's behaviour: how it uses tools, when it answers directly, and how it formats output. Modify it to change the agent's personality or impose different constraints.

---

## 10. Running the Project

### Single command — all you need

```bash
python client.py
```

`client.py` automatically:
- Spawns `server.py` as a background stdio subprocess
- Performs the MCP handshake and discovers tools
- Enters the interactive CLI loop

**You never need to run `server.py` manually.**

### What you'll see on startup

```
╭────────────────────────────────────────────────────────────────────────╮
│ CSV MCP Database · Natural Language CRUD over CSV using MCP + OpenAI  │
╰────────────────────────────────────────────────────────────────────────╯
Type a command in plain English. Type exit or quit to leave.

MCP server ready — 4 tool(s) discovered: add_person, get_people, modify_person, remove_person

User >
```

The "4 tool(s) discovered" line confirms Tool Discovery succeeded.

### Exiting

Type `exit`, `quit`, or press `Ctrl+C`.

---

## 11. Example Commands & Session

### Create records

```
User > pls create a new user with name Raj age 30 city Delhi
User > add a person Rahul age 28 city Mumbai
User > insert a new person named Alice, she is 25 and lives in Pune
User > add user Bob, 35, from Chennai
```

### Read / list records

```
User > show all users
User > list everyone in the database
User > who is in the database?
User > how many people are there?
User > list people from Delhi
User > show me all users from Mumbai
```

### Update records

```
User > update Raj age 31
User > change Rahul's city to Bangalore
User > set Alice's age to 26 and city to Hyderabad
User > Raj moved to Pune
```

### Delete records

```
User > delete Rahul
User > remove Raj from the database
User > erase Alice's record
```

### Non-database questions

The LLM answers general questions without calling any tool:

```
User > what is the capital of France?
Agent > Paris is the capital of France.
```

### Full example session

```
MCP server ready — 4 tool(s) discovered: add_person, get_people, modify_person, remove_person

User > add a person Rahul age 28 city Mumbai
Agent >
╭────────────────────────────────────────────╮
│ ✅  Successfully added: Rahul, age 28, from Mumbai. │
╰────────────────────────────────────────────╯

User > add Priya age 25 city Pune
Agent >
╭────────────────────────────────────────────╮
│ ✅  Successfully added: Priya, age 25, from Pune. │
╰────────────────────────────────────────────╯

User > show all users
Agent >
╭───────┬─────┬────────╮
│ Name  │ Age │ City   │
├───────┼─────┼────────┤
│ Rahul │  28 │ Mumbai │
│ Priya │  25 │ Pune   │
╰───────┴─────┴────────╯

User > how many people are in the database?
Agent >
╭───────────────────────────────────────╮
│ There are 2 people in the database.  │
╰───────────────────────────────────────╯

User > update Rahul age 29
Agent >
╭───────────────────────────────────╮
│ ✅  Updated 'Rahul': age → 29.   │
╰───────────────────────────────────╯

User > delete Priya
Agent >
╭────────────────────────────────────────────────────╮
│ ✅  Successfully deleted the record for 'Priya'.  │
╰────────────────────────────────────────────────────╯

User > exit
Goodbye! 👋
```

---

## 12. Tool Reference

### `add_person`

Inserts a new person into the database.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Full name (must be unique) |
| `age` | integer | ✅ | Age in years |
| `city` | string | ✅ | City of residence |

**Returns:** `"✅ Successfully added: {name}, age {age}, from {city}."` or a duplicate-detection warning.

---

### `get_people`

Retrieves all records, with optional city filtering.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `city` | string | ❌ | Filter by city name (case-insensitive). Omit to return all records. |

**Returns:** A list of dicts `[{ "name": ..., "age": ..., "city": ... }, ...]`. Returns an empty list if no records match.

---

### `modify_person`

Updates an existing person's age and/or city.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Name of the person to update (case-insensitive lookup) |
| `age` | integer | ❌ | New age value. Omit to leave unchanged. |
| `city` | string | ❌ | New city value. Omit to leave unchanged. |

At least one of `age` or `city` must be provided.

**Returns:** `"✅ Updated '{name}': {changed fields}."` or an error message if the person is not found.

---

### `remove_person`

Deletes a person's record by name.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | ✅ | Name of the person to delete (case-insensitive) |

**Returns:** `"✅ Successfully deleted the record for '{name}'."` or an error if not found.

---

## 13. How the LLM Decides Which Tool to Call

The LLM never "sees" the Python source code. It only sees:

1. **The system prompt** — sets the agent's role and rules
2. **The tool list** — names, descriptions (docstrings), and parameter schemas from Tool Discovery
3. **The conversation history** — all previous user and assistant messages

When a user says *"add Raj age 30 city Delhi"*, the LLM:
1. Reads the `add_person` tool description: *"Use this tool when the user wants to insert a new record... Example: 'pls create a new user with name Raj'"*
2. Recognises that the user's intent matches this description
3. Extracts `name="Raj"`, `age=30`, `city="Delhi"` from the natural language
4. Emits a `tool_calls` payload pointing to `add_person` with those arguments

**This is why docstrings matter so much in MCP servers.** A well-written docstring with example phrases dramatically improves the LLM's ability to pick the right tool at the right time.

---

## 14. How Tool Results Are Rendered

`print_agent_response()` in `client.py` applies two-stage rendering:

**Stage 1 — Try to parse as a JSON array:**  
If the LLM response contains a `[...]` block that parses as a list of dicts, it's rendered as a `rich` table with styled columns.

```
╭──────────┬─────┬────────╮
│ Name     │ Age │ City   │
├──────────┼─────┼────────┤
│ Raj      │  30 │ Delhi  │
│ Rahul    │  28 │ Mumbai │
╰──────────┴─────┴────────╯
```

**Stage 2 — Plain text panel:**  
Any other response (status messages, confirmations, general answers) is wrapped in a green rounded panel:

```
╭──────────────────────────────────────────────╮
│ ✅  Successfully added: Raj, age 30, from Delhi. │
╰──────────────────────────────────────────────╯
```

---

## 15. Data Integrity & Edge Cases

| Scenario | Behaviour |
|---|---|
| Adding a duplicate name | Returns a warning; does **not** insert |
| Name lookup (update/delete) | **Case-insensitive** — "raj", "RAJ", "Raj" all match |
| Updating with no fields | Returns a helpful error message |
| Updating a non-existent person | Returns `"❌ No person named '...' found"` |
| Deleting a non-existent person | Returns `"❌ No person named '...' found"` |
| `db.csv` missing on startup | Created automatically with correct headers |
| Partial update | At least one of `age`/`city` must be given; omitted fields are left unchanged |

---

## 16. Extending the Project

### Add a new column (e.g. `email`)

1. **`tools.py`** — Add `email` to `COLUMNS` and update all four functions to handle the new field.
2. **`server.py`** — Add `email: str` parameters to the relevant tool functions and update docstrings.
3. **`db.csv`** — Add the `email` column header (or delete and let it auto-recreate).

### Add a new tool (e.g. `search_by_age_range`)

1. **`tools.py`** — Implement `search_by_age_range(min_age, max_age)` using pandas filtering.
2. **`server.py`** — Decorate it with `@mcp.tool()` and write a descriptive docstring with examples.
3. No changes to `client.py` — new tools are discovered automatically at startup.

### Switch to SQLite instead of CSV

Replace `tools.py` with SQLite operations using Python's built-in `sqlite3` module. `server.py` and `client.py` remain completely unchanged — this is the "separation of concerns" benefit of MCP.

### Change the LLM model

In `client.py`, change:
```python
MODEL = "gpt-4o-mini"   # → "gpt-4o", "gpt-3.5-turbo", etc.
```

### Use a different LLM provider

Replace the OpenAI client with any provider that supports **function calling** (Anthropic Claude, Google Gemini, etc.). The MCP layer (`server.py`, `tools.py`) remains completely unchanged.

---

## 17. Troubleshooting

### `OPENAI_API_KEY` not set

```
Error: OPENAI_API_KEY is not set.
```
**Fix:** Create a `.env` file with `OPENAI_API_KEY=sk-...` or run `export OPENAI_API_KEY=sk-...`.

---

### MCP server crashes silently

The server's stderr is suppressed (piped to `DEVNULL` so it doesn't clutter the CLI). To debug the server directly, run it in isolation:

```bash
python server.py
```

Then paste a JSON-RPC `list_tools` request into stdin to see its response.

---

### LLM calls the same tool multiple times

This is a known LLM behaviour for aggregate queries (e.g. "how many people?"). The system prompt includes an explicit rule: *"Call each tool AT MOST ONCE per user request."* If it still happens, try a more capable model (`gpt-4o` instead of `gpt-4o-mini`).

---

### `db.csv` has unexpected data

You can inspect and reset the database at any time:

```bash
cat db.csv                    # view current contents
echo "name,age,city" > db.csv # reset to empty
```

---

### Import errors on startup

Make sure your virtual environment is activated:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 18. Key Learning Points

1. **MCP decouples tools from LLMs.** `tools.py` contains zero MCP code. You can run and test it independently. MCP is purely additive.

2. **Docstrings are the LLM's instructions.** The quality of tool descriptions directly affects how accurately the LLM picks and uses tools. Write them like documentation for a coworker, not just a computer.

3. **Tool Discovery makes the system dynamic.** Adding a new `@mcp.tool()` to `server.py` automatically makes it available to the LLM on the next startup — no changes to anything else.

4. **stdio is the simplest MCP transport.** A local MCP server is just a Python script. The client spawns it as a subprocess and talks to it over stdin/stdout using JSON-RPC messages.

5. **The tool-call loop is explicit.** Unlike higher-level APIs that hide tool execution, this project shows the full cycle: LLM returns `tool_calls` → client invokes tool → result fed back → LLM produces final answer.

6. **Function calling + MCP is a powerful pattern.** The LLM never touches the database directly. It can only read/write data through the tools you expose — giving you full control over what operations are possible.

---

## 19. Glossary

| Term | Definition |
|---|---|
| **MCP** | Model Context Protocol — open standard for LLM ↔ tool communication |
| **MCP Server** | A process that exposes tools over MCP (this project: `server.py`) |
| **MCP Client** | The code that connects to an MCP server and invokes tools (`client.py`) |
| **FastMCP** | High-level Python library for building MCP servers with minimal boilerplate |
| **stdio transport** | MCP communication over stdin/stdout between a parent and child process |
| **Tool Exposure** | Registering a function as a callable MCP tool using `@mcp.tool()` |
| **Tool Discovery** | Fetching the list of available tools via `list_tools()` at session start |
| **Tool Invocation** | Calling a specific tool with arguments via `call_tool()` |
| **JSON-RPC** | The underlying message format MCP uses for all communication |
| **Function Calling** | OpenAI Chat Completions feature that lets the LLM request tool execution |
| **CRUD** | Create, Read, Update, Delete — the four basic database operations |
| **pandas** | Python library for tabular data manipulation (used here for CSV I/O) |
| **rich** | Python library for beautiful, formatted terminal output |
| **dotenv** | Convention for storing secrets in a `.env` file; loaded by `python-dotenv` |

---

## 20. Dependencies

| Package | Version | Purpose |
|---|---|---|
| `pandas` | ≥ 2.0.0 | CSV database operations (read, filter, append, update, delete rows) |
| `openai` | ≥ 1.50.0 | Chat Completions API with function calling |
| `mcp` | ≥ 1.0.0 | MCP Python SDK — `ClientSession`, `FastMCP`, `stdio_client`, `StdioServerParameters` |
| `rich` | ≥ 13.0.0 | Terminal tables, panels, spinners, styled text |
| `python-dotenv` | ≥ 1.0.0 | Load `OPENAI_API_KEY` from a `.env` file automatically |

Install all at once:

```bash
pip install -r requirements.txt
```
