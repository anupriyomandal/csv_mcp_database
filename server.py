"""
server.py — MCP Server using FastMCP (stdio transport)

This module creates and runs the MCP server over stdio — the standard
transport for local MCP servers. The client spawns this script as a
child process and exchanges JSON-RPC messages over stdin/stdout.

MCP Concept — "Tool Exposure":
  Each @mcp.tool() decorated function becomes a discoverable, callable
  tool. The LLM can only call tools that are exposed this way.

MCP Concept — "Tool Discovery":
  When the client connects it calls list_tools(), which returns the name,
  description, and parameter schema of every @mcp.tool() function. This
  is what lets the LLM know what it can do before any user input.

MCP Concept — "Tool Invocation":
  When the LLM decides to call a tool, the client calls session.call_tool()
  with the tool name and arguments. FastMCP routes that call here and
  returns the result.

Run standalone for manual testing:
    python server.py
(use MCP inspector or pipe JSON-RPC messages via stdin)
"""

from mcp.server.fastmcp import FastMCP
from tools import create_person, list_people, update_person, delete_person

# Initialise the FastMCP server — "CSV Database" is surfaced to the LLM
# during tool discovery so the model understands the context of all tools.
mcp = FastMCP("CSV Database")


# ---------------------------------------------------------------------------
# Tool: add_person
# ---------------------------------------------------------------------------
@mcp.tool()
def add_person(name: str, age: int, city: str) -> str:
    """
    Add a new person to the CSV database.

    Use this tool when the user wants to insert a new record.

    Example user inputs that should trigger this tool:
    - "pls create a new user with name Raj age 30 city Delhi"
    - "add a person Rahul age 28 city Mumbai"
    - "insert a new person named Alice, she is 25 and lives in Pune"
    - "add user Bob, 35, from Chennai"

    Args:
        name: Full name of the person to add.
        age:  Age of the person (positive integer).
        city: City where the person currently lives.
    """
    return create_person(name=name, age=age, city=city)


# ---------------------------------------------------------------------------
# Tool: get_people
# ---------------------------------------------------------------------------
@mcp.tool()
def get_people(city: str | None = None) -> list[dict]:
    """
    Retrieve all people stored in the CSV database.

    Use this tool when the user wants to see records — all of them or
    filtered by a specific city.

    Example user inputs that should trigger this tool:
    - "show all users"
    - "list everyone in the database"
    - "who is in the database?"
    - "list people from Delhi"
    - "show me all users from Mumbai"
    - "display all records"

    Args:
        city: Optional city filter. Leave None to return all records.
    """
    return list_people(city=city)


# ---------------------------------------------------------------------------
# Tool: modify_person
# ---------------------------------------------------------------------------
@mcp.tool()
def modify_person(name: str, age: int | None = None, city: str | None = None) -> str:
    """
    Update an existing person's age and/or city in the CSV database.

    Use this tool when the user wants to change or correct an existing record.

    Example user inputs that should trigger this tool:
    - "update Raj age 31"
    - "change Rahul's city to Bangalore"
    - "set Priya's age to 23 and city to Jaipur"
    - "edit Bob's record — city should be Surat"

    Args:
        name: Name of the person to update.
        age:  New age value (omit to leave unchanged).
        city: New city value (omit to leave unchanged).
    """
    return update_person(name=name, age=age, city=city)


# ---------------------------------------------------------------------------
# Tool: remove_person
# ---------------------------------------------------------------------------
@mcp.tool()
def remove_person(name: str) -> str:
    """
    Delete a person's record from the CSV database.

    Use this tool when the user wants to remove or delete an entry.

    Example user inputs that should trigger this tool:
    - "delete Rahul"
    - "remove Raj from the database"
    - "erase Bob's entry"

    Args:
        name: The name of the person to delete.
    """
    return delete_person(name=name)


# ---------------------------------------------------------------------------
# Entry point — stdio transport (standard for local MCP servers)
# ---------------------------------------------------------------------------
# stdio means the server reads JSON-RPC from stdin and writes to stdout.
# The client (client.py) spawns this script as a child process and
# communicates through the pipe — no network port required.
if __name__ == "__main__":
    mcp.run(transport="stdio")
