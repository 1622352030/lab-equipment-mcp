import asyncio
import json
import os
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify() -> None:
    project_dir = Path(__file__).resolve().parents[1]
    uv = os.environ.get("UV_EXECUTABLE", "uv")
    server = StdioServerParameters(
        command=uv,
        args=["--directory", str(project_dir), "run", "start-lab-equipment-mcp"],
        env={**os.environ, "UV_CACHE_DIR": str(project_dir / ".uv-cache")},
        cwd=project_dir,
    )
    async with stdio_client(server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = await session.list_tools()
            print(json.dumps([tool.name for tool in tools.tools], indent=2))
            result = await session.call_tool("dpo2012b_diagnose_setup", {})
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(verify())
