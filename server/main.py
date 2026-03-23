from __future__ import annotations

from fastmcp import FastMCP

from server.config import load_settings
from server.logger import get_logger, setup_logging
from server.tools.chatgpt_web import chatgpt_web_research as execute_chatgpt_web_research

_settings = load_settings()
setup_logging(_settings.log_level)
log = get_logger(__name__)

mcp = FastMCP(
    "MCP ChatGPT Web",
    instructions=(
        "ChatGPT Web research via Playwright. Use chatgpt_web_research with a clear prompt. "
        "Requires a valid saved browser session on the host running this server."
    ),
)


@mcp.tool
async def chatgpt_web_research(prompt: str, timeout: int | None = None) -> dict:
    """Send a prompt to ChatGPT Web and return summary, full_response, status, and execution_time."""
    return await execute_chatgpt_web_research(prompt, timeout, _settings=_settings)


def main() -> None:
    log.info("Starting MCP ChatGPT Web (FastMCP, stdio)")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
