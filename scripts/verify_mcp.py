import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

GITHUB_SOURCE = "git+https://github.com/1622352030/lab-equipment-mcp.git@main"


async def verify(use_github: bool = False) -> None:
    project_dir = Path(__file__).resolve().parents[1]
    executable = os.environ.get("UVX_EXECUTABLE", "uvx") if use_github else sys.executable
    args = (
        ["--from", GITHUB_SOURCE, "start-lab-equipment-mcp"]
        if use_github
        else ["-m", "lab_equipment_mcp.server"]
    )
    server = StdioServerParameters(
        command=executable,
        args=args,
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
            afg_result = await session.call_tool("afg2125_diagnose_setup", {})
            print(afg_result.content[0].text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--github", action="store_true", help="verify the GitHub package source")
    arguments = parser.parse_args()
    asyncio.run(verify(use_github=arguments.github))
