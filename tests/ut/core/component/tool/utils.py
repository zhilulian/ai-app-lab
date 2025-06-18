# Copyright 2025 Bytedance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from arkitect.core.component.tool.mcp_client import MCPClient
from arkitect.core.component.tool.tool_pool import ToolPool
from arkitect.core.component.tool.utils import (
    convert_to_chat_completion_content_part_param,
)
from dummy_mcp_server import server
from dummy_mcp_server_http_streamable import server as http_streamable_server


async def check_server_working(
    client: MCPClient | ToolPool,
    expected_tools,
    use_cache=False,
):
    assert client.session is not None
    tools = await client.list_tools(use_cache=use_cache)
    assert len(tools) == len(expected_tools)
    for t in expected_tools:
        output = await client.execute_tool(t, expected_tools.get(t).get("input"))
        converted = convert_to_chat_completion_content_part_param(output)
        print(converted)
        assert converted == expected_tools.get(t).get("output")
    return True


def _start_server():
    """Function to run the server (executed in a separate process)."""
    server.run(transport="sse")


def _start_http_streamable_server():
    """Function to run the http streamable server (executed in a separate process)."""
    http_streamable_server.run(transport="streamable-http")
