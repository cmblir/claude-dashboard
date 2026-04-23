#!/usr/bin/env python3
"""LazyClaude MCP server entrypoint (stdio).

Register with Claude Code:
    claude mcp add lazyclaude -- python3 /path/to/LazyClaude/scripts/lazyclaude_mcp.py

Then invoke any tool in a session:
    /mcp call lazyclaude lazyclaude_tabs
    /mcp call lazyclaude lazyclaude_cost_summary
    /mcp call lazyclaude lazyclaude_security_scan
    ...

No network. No auth. Runs entirely on the local machine against ~/.claude/.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.mcp_server import run

if __name__ == "__main__":
    run()
