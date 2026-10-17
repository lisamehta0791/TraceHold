"""A long-lived session with Exasol's open-source MCP server (exasol-mcp-server).

The server runs as a child process connected as the read-only user TH_ASK, which
can SELECT from the TH_RESULTS views and nothing else. Write tools are disabled
in the server settings as well, so there are two independent guards.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from pathlib import Path

from app import db

SERVER_PACKAGE = os.environ.get("TRACEHOLD_MCP_PACKAGE", "exasol-mcp-server@2.1.0")
READER = "TH_ASK"


MCP_VENV = db.ROOT / ".venv-mcp"   # project-local environment for the server (created by app.ai_setup)


def server_command() -> tuple[str, list[str]]:
    """The server installed in the project's own .venv-mcp; uvx only as a fallback."""
    exe = MCP_VENV / ("Scripts/exasol-mcp-server.exe" if os.name == "nt" else "bin/exasol-mcp-server")
    if exe.exists():
        return str(exe), []
    found = shutil.which("uvx") or str(Path.home() / ".local" / "bin" / ("uvx.exe" if os.name == "nt" else "uvx"))
    if Path(found).exists():
        return found, [SERVER_PACKAGE]
    raise RuntimeError("Exasol's MCP server is not installed. Run: python -m app.ai_setup (from the backend folder).")


class ExasolMCP:
    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session = None
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._error: str | None = None
        self._lock = threading.Lock()
        self.tools: list[str] = []

    # ------------------------------------------------------------ lifecycle
    def _start(self):
        pw = os.environ.get("TRACEHOLD_ASK_PASSWORD")
        if not pw:
            raise RuntimeError("The read-only user is not set up yet. Run: python -m app.ai_setup")
        self._ready.clear()
        self._error = None
        loop = asyncio.new_event_loop()
        self._loop = loop
        threading.Thread(target=loop.run_forever, daemon=True, name="exasol-mcp").start()
        asyncio.run_coroutine_threadsafe(self._run(pw), loop)
        if not self._ready.wait(90):
            raise RuntimeError("Exasol's MCP server did not start within 90 seconds.")
        if self._error:
            raise RuntimeError(f"Exasol's MCP server could not start: {self._error}")

    async def _run(self, pw: str):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        env = {**os.environ, "EXA_DSN": db.DSN, "EXA_USER": READER, "EXA_PASSWORD": pw,
               "EXA_SSL_CERT_VALIDATION": "no",
               "EXA_MCP_SETTINGS": json.dumps({"enable_read_query": True, "enable_write_query": False,
                                                "enable_write_bucketfs": False})}
        try:
            cmd, args = server_command()
            params = StdioServerParameters(command=cmd, args=args, env=env)
            self._errlog = open(os.devnull, "w")
            async with stdio_client(params, errlog=self._errlog) as (r, w):
                async with ClientSession(r, w) as session:
                    await session.initialize()
                    self.tools = [t.name for t in (await session.list_tools()).tools]
                    self._session = session
                    self._stop = asyncio.Event()
                    self._ready.set()
                    await self._stop.wait()
        except Exception as e:  # noqa: BLE001
            self._error = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
        finally:
            self._session = None
            self._ready.set()

    def _ensure(self):
        with self._lock:
            if self._session is None:
                self._start()

    # ------------------------------------------------------------ calls
    def call(self, tool: str, args: dict, timeout: float = 25.0) -> dict:
        self._ensure()
        fut = asyncio.run_coroutine_threadsafe(self._session.call_tool(tool, args), self._loop)
        try:
            res = fut.result(timeout)
        except TimeoutError:
            fut.cancel()
            raise RuntimeError(f"The query took longer than {timeout:.0f} seconds and was stopped.")
        text = "".join(getattr(c, "text", "") for c in (res.content or []))
        if getattr(res, "is_error", False) or getattr(res, "isError", False):
            raise RuntimeError(text.replace("Error calling tool 'execute_exasol_query': ", "")[:400])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"text": text}

    def query(self, sql: str, row_limit: int = 200) -> dict:
        out = self.call("execute_exasol_query", {"query": sql, "row_limit": row_limit})
        return {"columns": out.get("columns", []), "rows": out.get("rows", [])}

    def describe(self, schema: str, names: list[str]) -> dict:
        return self.call("describe_exasol_tables_and_views", {"schema_name": schema, "table_names": names})

    def status(self) -> dict:
        try:
            where = "project .venv-mcp" if server_command()[0].startswith(str(MCP_VENV)) else "uvx"
        except RuntimeError:
            where = "not installed"
        return {"running": self._session is not None, "package": SERVER_PACKAGE, "user": READER, "tools": len(self.tools),
                "installed_in": where, "error": self._error}


mcp = ExasolMCP()
