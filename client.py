"""
client.py — CLI Agent: MCP SDK (stdio) + OpenAI Chat Completions

How it works:
  1. Spawns server.py as a child process using the MCP stdio transport.
  2. Tool Discovery — calls list_tools() to get all tools from the server.
  3. Converts MCP tool schemas into OpenAI function-calling format.
  4. Interactive loop:
       a. User types natural language.
       b. OpenAI Chat Completions decides which tool(s) to call.
       c. Tool Invocation — call_tool() sends each tool call to the MCP server.
       d. Tool results are fed back to the LLM for a final answer.

dotenv: put OPENAI_API_KEY=sk-... in a .env file here.
"""

import os
import sys
import json
import asyncio

from dotenv import load_dotenv
load_dotenv()

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from openai import OpenAI
from openai.types.chat import ChatCompletionMessageParam
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich import box


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
MODEL          = "gpt-4o-mini"
SERVER_SCRIPT  = os.path.join(os.path.dirname(__file__), "server.py")

console = Console()

SYSTEM_PROMPT = (
    "You are a helpful database assistant managing a CSV database of people "
    "(name, age, city). Rules:\n"
    "1. Call each tool AT MOST ONCE per user request. Never repeat a tool call.\n"
    "2. For listing or counting records, call get_people ONCE then derive the answer "
    "from the returned data yourself (e.g. count the items in the list).\n"
    "3. Always respond in natural language. When listing records, include a JSON array "
    "of the records at the END of your response so the client can render a table, BUT "
    "also include a brief natural language summary (e.g. 'Here are the 3 people in the database:').\n"
    "4. For non-database questions, answer directly without calling any tool."
)


# ---------------------------------------------------------------------------
# Rich formatting helpers
# ---------------------------------------------------------------------------

def print_banner() -> None:
    banner = Text()
    banner.append("CSV MCP Database", style="bold cyan")
    banner.append(" · ", style="dim")
    banner.append("Natural Language CRUD over CSV using MCP + OpenAI", style="italic white")
    console.print(Panel(banner, border_style="cyan", box=box.ROUNDED))
    console.print(
        "[dim]Type a command in plain English. "
        "Type [bold]exit[/bold] or [bold]quit[/bold] to leave.[/dim]\n"
    )


def render_people_table(records: list[dict]) -> None:
    """Render person records as a rich table."""
    if not records:
        console.print("[yellow]  No records found.[/yellow]")
        return
    table = Table(show_header=True, header_style="bold magenta",
                  box=box.ROUNDED, border_style="dim", pad_edge=True)
    table.add_column("Name", style="bold white", no_wrap=True)
    table.add_column("Age",  style="cyan", justify="right")
    table.add_column("City", style="green")
    for r in records:
        table.add_row(str(r.get("name", "")), str(r.get("age", "")), str(r.get("city", "")))
    console.print(table)


def print_agent_response(text: str) -> None:
    """Render the agent's reply — table for JSON arrays, panel for text."""
    stripped = text.strip()
    # Try to detect a JSON array (list of people)
    start = stripped.find("[")
    if start != -1:
        try:
            records = json.loads(stripped[start:stripped.rfind("]") + 1])
            if isinstance(records, list) and all(isinstance(r, dict) for r in records):
                console.print()
                render_people_table(records)
                console.print()
                return
        except (json.JSONDecodeError, ValueError):
            pass
    console.print()
    console.print(Panel(Text(stripped, style="white"), border_style="green",
                        box=box.ROUNDED, expand=False))
    console.print()


# ---------------------------------------------------------------------------
# MCP tool schema → OpenAI function format
# ---------------------------------------------------------------------------

def mcp_tool_to_openai(tool) -> dict:
    """
    Convert an MCP Tool object into the OpenAI function-calling schema.

    This is the bridge between Tool Discovery (what MCP exposes) and what
    the OpenAI Chat Completions API understands.
    """
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description or "",
            "parameters": tool.inputSchema,  # MCP already uses JSON Schema format
        },
    }


# ---------------------------------------------------------------------------
# Core agent loop (async — required by the MCP SDK)
# ---------------------------------------------------------------------------

async def agent_loop(oai_client: OpenAI) -> None:
    """
    Main async loop: connects to the MCP server, discovers tools, and runs
    the interactive CLI with full tool-call round-trips.
    """
    # --- Connect to the MCP server via stdio ---
    server_params = StdioServerParameters(
        command=sys.executable,   # same Python interpreter as this script
        args=[SERVER_SCRIPT],
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            # --- MCP: initialize + Tool Discovery ---
            await session.initialize()
            tools_result = await session.list_tools()

            # Convert discovered MCP tools to OpenAI format
            openai_tools = [mcp_tool_to_openai(t) for t in tools_result.tools]

            console.print(
                f"[dim]MCP server ready — {len(openai_tools)} tool(s) discovered: "
                f"{', '.join(t.name for t in tools_result.tools)}[/dim]\n"
            )

            # Conversation history (grows through the session)
            messages: list[ChatCompletionMessageParam] = []

            # --- Interactive CLI loop ---
            while True:
                try:
                    user_input = console.input("[bold cyan]User >[/bold cyan] ").strip()
                except (EOFError, KeyboardInterrupt):
                    console.print("\n[dim]Goodbye! 👋[/dim]\n")
                    break

                if not user_input:
                    continue
                if user_input.lower() in {"exit", "quit", "q"}:
                    console.print("\n[dim]Goodbye! 👋[/dim]\n")
                    break

                messages.append({"role": "user", "content": user_input})

                # --- LLM reasoning + tool-call loop ---
                with console.status("[dim]Agent is thinking…[/dim]", spinner="dots"):
                    while True:
                        response = oai_client.chat.completions.create(
                            model=MODEL,
                            tools=openai_tools,
                            messages=[{"role": "system", "content": SYSTEM_PROMPT}]
                                     + messages,
                        )

                        msg = response.choices[0].message
                        # Append assistant turn (preserves tool_calls metadata)
                        messages.append(msg)  # type: ignore[arg-type]

                        # If no tool calls → we have the final answer
                        if not msg.tool_calls:
                            break

                        # --- MCP: Tool Invocation ---
                        # The LLM has decided to call one or more tools.
                        # We execute each via the MCP session and feed results back.
                        for tc in msg.tool_calls:
                            args = json.loads(tc.function.arguments)
                            tool_result = await session.call_tool(tc.function.name, args)

                            # Extract ALL text content from the MCP result.
                            # FastMCP splits list results into separate TextContent
                            # items, each containing one JSON object. We detect this
                            # pattern and wrap them into a proper JSON array so the
                            # LLM sees the full dataset.
                            parts = []
                            for item in (tool_result.content or []):
                                if hasattr(item, "text"):
                                    parts.append(item.text)
                                else:
                                    parts.append(str(item))

                            # If we have multiple parts that each look like JSON
                            # objects, wrap them into a JSON array.
                            if len(parts) > 1:
                                try:
                                    parsed = [json.loads(p) for p in parts]
                                    result_text = json.dumps(parsed)
                                except (json.JSONDecodeError, ValueError):
                                    result_text = "\n".join(parts)
                            else:
                                result_text = "\n".join(parts)

                            messages.append({
                                "role": "tool",
                                "tool_call_id": tc.id,
                                "content": result_text,
                            })
                        # Loop back → LLM sees tool results and produces next reply

                # Print the final assistant response
                final_text = msg.content or ""
                console.print("[bold green]Agent >[/bold green]", end="")
                print_agent_response(final_text)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    if not OPENAI_API_KEY:
        console.print(
            "[bold red]Error:[/bold red] OPENAI_API_KEY is not set.\n"
            "Add it to a [bold].env[/bold] file:\n\n"
            "    [bold green]OPENAI_API_KEY=sk-...[/bold green]\n"
        )
        sys.exit(1)

    oai_client = OpenAI(api_key=OPENAI_API_KEY)
    print_banner()

    try:
        asyncio.run(agent_loop(oai_client))
    except KeyboardInterrupt:
        console.print("\n[dim]Goodbye! 👋[/dim]\n")


if __name__ == "__main__":
    main()
