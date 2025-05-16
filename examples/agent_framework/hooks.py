from typing import Any, AsyncIterable, Optional

from arkitect.core.component.agent.base_agent import PostAgentCallHook, PreAgentCallHook
from arkitect.core.component.llm_event_stream.hooks import (
    PostLLMCallHook,
    PostToolCallHook,
    PreLLMCallHook,
    PreToolCallHook,
)
from arkitect.core.component.llm_event_stream.model import State
from arkitect.types.responses.event import BaseEvent


class CustomHook(
    PreToolCallHook,
    PreLLMCallHook,
    PostLLMCallHook,
    PostToolCallHook,
    PreAgentCallHook,
    PostAgentCallHook,
):
    async def pre_tool_call(
        self,
        name: str,
        arguments: str,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        print(f"Running Tool {name}\nInput {arguments}")
        return
        yield

    async def post_tool_call(
        self,
        name: str,
        arguments: str,
        response: Any,
        exception: Optional[Exception],
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        print(f"Done executing Tool {name}\nInput {arguments}\nOutput {response}")
        return
        yield

    async def pre_llm_call(
        self,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        print("About to call LLM")
        return
        yield

    async def post_llm_call(
        self,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        print("Done calling LLM")
        return
        yield

    async def pre_agent_call(
        self,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        print("About to call MyAgent Agent")
        return
        yield

    async def post_agent_call(
        self,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        print("Done calling MyAgent")
        return
        yield
