import os
from typing import AsyncIterable, Union

from hooks import CustomHook
from instructions import make_instruction

from arkitect.core.component.agent import DefaultAgent
from arkitect.core.component.runner import Runner

# from arkitect.core.component.tool.builder import build_mcp_clients_from_config
from arkitect.core.component.tool.builtin_tools import link_reader
from arkitect.launcher.local.serve import launch_serve
from arkitect.telemetry.trace import task
from arkitect.types.llm.model import (
    ArkChatCompletionChunk,
    ArkChatParameters,
    ArkChatRequest,
    ArkChatResponse,
)
from arkitect.types.responses.event import (
    MessageEvent,
    ToolCompletedEvent,
)

CONFIG_FILE_PATH = "./mcp_config.json"


@task()
async def main(
    request: ArkChatRequest,
) -> AsyncIterable[Union[ArkChatCompletionChunk, ArkChatResponse]]:
    parameters = ArkChatParameters(**request.__dict__)

    agent_hook = CustomHook()

    # Init mcp clients to your mcp servers if any
    # mcp_clients, cleanup = build_mcp_clients_from_config(CONFIG_FILE_PATH)

    agent = DefaultAgent(
        name="link reader agent",
        description="link reader agent",
        model="doubao-seed-1-6-250615",
        tools=[
            link_reader,
            # mcp_clients, # Connect to your MCPs if any
        ],
        instruction=make_instruction(request),
        parameters=parameters,
        # Add custom logic in the hook
        pre_agent_call_hook=agent_hook,
        post_agent_call_hook=agent_hook,
        pre_llm_call_hook=agent_hook,
        post_llm_call_hook=agent_hook,
        pre_tool_call_hook=agent_hook,
        post_tool_call_hook=agent_hook,
    )
    runner = Runner(
        app_name="link reader app",
        agent=agent,
    )

    usage_chunks = []
    cummulated_bot_usages = None
    async for resp in runner.run(messages=request.messages):
        if isinstance(resp, ToolCompletedEvent):
            ck = resp.to_chunk()
            if ck.bot_usage:
                if cummulated_bot_usages:
                    cummulated_bot_usages += ck.bot_usage
                else:
                    cummulated_bot_usages = ck.bot_usage
        elif isinstance(resp, MessageEvent):
            ck = resp.to_chunk()
            if ck.usage:
                usage_chunks.append(ck)
            else:
                yield ck
    if len(usage_chunks) > 0:
        final_usage_chunk = ArkChatCompletionChunk.merge(usage_chunks)
        if final_usage_chunk:
            final_usage_chunk.bot_usage = cummulated_bot_usages
            yield final_usage_chunk


if __name__ == "__main__":
    port = os.getenv("_FAAS_RUNTIME_PORT")
    launch_serve(
        package_path="main",
        port=int(port) if port else 8080,
        health_check_path="/v1/ping",
        endpoint_path="/api/v3/bots/chat/completions",
        clients={},
    )
