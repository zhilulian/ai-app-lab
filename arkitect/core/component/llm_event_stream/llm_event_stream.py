# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
from typing import Any, AsyncIterable, Callable, Dict, List, Optional

from volcenginesdkarkruntime import AsyncArk
from volcenginesdkarkruntime.types.chat import ChatCompletionMessageParam

from arkitect.core.client import default_ark_client
from arkitect.core.component.agent.base_agent import BaseAgent
from arkitect.core.component.tool.mcp_client import MCPClient
from arkitect.core.component.tool.tool_pool import build_tool_pool
from arkitect.core.component.tool.utils import (
    convert_to_chat_completion_content_part_param,
)
from arkitect.telemetry.trace import task
from arkitect.types.llm.model import ArkChatParameters, Message
from arkitect.types.responses.event import (
    BaseEvent,
    StateUpdateEvent,
    ToolCallEvent,
    ToolCompletedEvent,
)

from .chat_completion import _AsyncChat
from .hooks import (
    PostLLMCallHook,
    PostToolCallHook,
    PreLLMCallHook,
    PreToolCallHook,
)
from .model import State


class _AsyncCompletionsEventStream:
    def __init__(self, ctx: "LLMEventStream"):
        self._ctx = ctx
        self.model = ctx.model

    async def create(
        self,
        messages: List[ChatCompletionMessageParam],
        **kwargs: Dict[str, Any],
    ) -> AsyncIterable[BaseEvent]:
        async def iterator(
            messages: List[ChatCompletionMessageParam],
        ) -> AsyncIterable[BaseEvent]:
            yield StateUpdateEvent(message_delta=[Message(**m) for m in messages])
            if self.need_tool_call():
                async for event in self.tool_call_stream():
                    yield event

            while True:
                if self._ctx.pre_llm_call_hook:
                    async for event in self._ctx.pre_llm_call_hook.pre_llm_call(
                        self._ctx.state
                    ):
                        yield event
                resp = await self._ctx.chat_service.completions.create_event_stream(
                    model=self.model,
                    messages=self._ctx.build_chat_message(),
                    tool_pool=self._ctx.tool_pool,
                    **kwargs,
                )
                assert isinstance(resp, AsyncIterable)
                async for chunk in resp:
                    yield chunk
                messages = []

                if self._ctx.post_llm_call_hook:
                    async for event in self._ctx.post_llm_call_hook.post_llm_call(
                        self._ctx.state
                    ):
                        yield event

                if self.need_agent_call():
                    async for event in self.agent_call_stream():
                        yield event
                elif self.need_tool_call():
                    async for event in self.tool_call_stream():
                        yield event
                else:
                    break

        return iterator(messages)

    async def execute_tool(
        self, tool_name: str, parameters: str
    ) -> tuple[Any | None, Exception | None]:
        tool_resp, tool_exception = None, None
        try:
            tool_resp = await self._ctx.tool_pool.execute_tool(  # type: ignore
                tool_name=tool_name, parameters=json.loads(parameters)
            )
            tool_resp = convert_to_chat_completion_content_part_param(tool_resp)
        except Exception as e:
            tool_exception = e
        return tool_resp, tool_exception

    @task()
    def need_tool_call(self) -> bool:
        last_message = self._ctx.get_latest_message(role=None)
        if (
            last_message is not None
            and last_message.tool_calls
            and self._ctx.tool_pool is not None
        ):
            return True
        return False

    async def tool_call_stream(self) -> AsyncIterable[BaseEvent]:
        tool_calls = self._ctx.get_latest_message(role=None).tool_calls  # type: ignore
        for tool_call in tool_calls:  # type: ignore
            tool_name = tool_call.function.name
            if self._ctx.pre_tool_call_hook:
                async for event in self._ctx.pre_tool_call_hook.pre_tool_call(
                    name=tool_name,
                    arguments=tool_call.function.arguments,
                    state=self._ctx.state,
                ):
                    yield event
            updated_arguments = tool_call.function.arguments

            yield ToolCallEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_name,
                tool_arguments=updated_arguments,
            )
            resp, exceptions = await self.execute_tool(tool_name, updated_arguments)
            yield ToolCompletedEvent(
                tool_call_id=tool_call.id,
                tool_name=tool_name,
                tool_arguments=updated_arguments,
                tool_exception=exceptions,
                tool_response=resp,
            )
            yield StateUpdateEvent(
                message_delta=[
                    Message(
                        **{  # type: ignore
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": resp,
                        }
                    )
                ]
            )
            if self._ctx.post_tool_call_hook:
                async for event in self._ctx.post_tool_call_hook.post_tool_call(
                    name=tool_name,
                    arguments=updated_arguments,
                    response=resp,
                    exception=exceptions,
                    state=self._ctx.state,
                ):
                    yield event

    @task()
    def need_agent_call(self) -> bool:
        last_message = self._ctx.get_latest_message(role=None)
        if last_message is not None and last_message.tool_calls:
            if "handoff" in last_message.tool_calls[0].function.name:
                return True
            # TODO: Hack due to model performance
            elif self.get_agent(last_message.tool_calls[0].function.name):
                return True
        return False

    async def agent_call_stream(self) -> AsyncIterable[BaseEvent]:
        tool_calls = self._ctx.get_latest_message(role=None).tool_calls  # type: ignore
        agent_call = tool_calls[0]  # type: ignore
        tool_name = agent_call.function.name
        arguments = agent_call.function.arguments
        # TODO hack due to model performance
        agent_name = json.loads(arguments).get("agent_name")
        if agent_name is None:
            agent_name = tool_name
        agent = self.get_agent(agent_name)
        if agent is None:
            raise Exception(f"Agent {agent_name} not found")
        yield StateUpdateEvent(
            message_delta=[
                Message(
                    **{  # type: ignore
                        "role": "tool",
                        "tool_call_id": agent_call.id,
                        "content": f"切换到{agent_name}",
                    }
                )
            ]
        )
        async for event in agent(self._ctx.state):
            yield event

    @task()
    def get_agent(self, agent_name: str) -> BaseAgent | None:
        if self._ctx.sub_agents is None:
            return None
        for agent in self._ctx.sub_agents:
            if agent.name == agent_name:
                return agent
        return None


def build_handoff(agents: list[BaseAgent]) -> Callable:
    def handoff(agent_name: str) -> str:
        return agent_name

    agents_desc = ""

    for agent in agents:
        agents_desc += f"{agent.name}: {agent.description}\n"

    handoff.__doc__ = f"""你可以通过调用此函数 handoff 将任务切换给其他Agent。
    
    agent_name列表及其功能如下所述：
    {agents_desc}
    
    请你根据上面这些agent的描述和目前所在的任务，调用handoff 这个方法
    来决定要切换到哪个Agent。不要输出任何其他内容。

    参数说明：
        •	agent_name(str)：要切换到的Agent名称。
    """

    return handoff


class LLMEventStream:
    def __init__(
        self,
        *,
        model: str,
        agent_name: str,
        state: State | None = None,
        tools: list[MCPClient | Callable] | None = None,
        sub_agents: list[BaseAgent] | None = None,  # noqa: F821
        parameters: Optional[ArkChatParameters] = None,
        client: Optional[AsyncArk] = None,
        pre_tool_call_hook: PreToolCallHook | None = None,
        post_tool_call_hook: PostToolCallHook | None = None,
        pre_llm_call_hook: PreLLMCallHook | None = None,
        post_llm_call_hook: PostLLMCallHook | None = None,
        instruction: str | None = None,
    ):
        self.model = model
        self.agent_name = agent_name
        self.state = state if state else State()
        self.parameters = parameters
        self.client = default_ark_client() if client is None else client
        self.chat_service = _AsyncChat(
            client=self.client, state=self.state, parameters=self.parameters
        )
        self.sub_agents = sub_agents
        full_tools: list[MCPClient | Callable] = []
        if self.sub_agents and len(self.sub_agents) > 0:
            full_tools = [build_handoff(self.sub_agents)]
        if tools and len(tools) > 0:
            full_tools.extend(tools)
        self.tool_pool = build_tool_pool(full_tools)
        self.pre_tool_call_hook: PreToolCallHook | None = pre_tool_call_hook
        self.post_tool_call_hook: PostToolCallHook | None = post_tool_call_hook
        self.pre_llm_call_hook: PreLLMCallHook | None = pre_llm_call_hook
        self.post_llm_call_hook: PostLLMCallHook | None = post_llm_call_hook
        self.instruction = instruction

    async def init(self) -> None:
        if self.tool_pool:
            await self.tool_pool.refresh_tool_list()
        return

    def get_latest_message(self, role: str | None = "assistant") -> Optional[Message]:
        for evt in reversed(self.state.events):
            if evt.message_delta:
                for m in evt.message_delta:
                    if role is None:
                        return m
                    if m.role == role:
                        return m
        return None

    @task()
    def build_chat_message(self) -> list[ChatCompletionMessageParam]:
        if self.instruction:
            messages = [
                {
                    "role": "system",
                    "content": self.instruction,
                }
            ]
        else:
            messages = []
        for e in self.state.events:
            if m := build_messages(e, self.agent_name):
                messages.extend(m)
        return messages

    @property
    def completions(self) -> _AsyncCompletionsEventStream:
        return _AsyncCompletionsEventStream(self)

    def set_pre_tool_call_hook(self, hook: PreToolCallHook) -> None:
        self.pre_tool_call_hook = hook

    def set_post_tool_call_hook(self, hook: PostToolCallHook) -> None:
        self.post_tool_call_hook = hook

    def set_pre_llm_call_hook(self, hook: PreLLMCallHook) -> None:
        self.pre_llm_call_hook = hook

    def set_post_llm_call_hook(self, hook: PostLLMCallHook) -> None:
        self.post_llm_call_hook = hook


def get_role(role: str, agent_name: str, author_name: str) -> str:
    if role != "assistant":
        return role
    if author_name == agent_name:
        return "assistant"
    return "user"


def get_message(message: Message, agent_name: str, author_name: str) -> dict:
    msg = message.model_dump()
    if message.role == "assistant":
        role = get_role(message.role, agent_name, author_name)
        msg["role"] = role
    return msg


def build_messages(
    event: BaseEvent, agent_name: str
) -> list[ChatCompletionMessageParam] | None:
    if not isinstance(event, StateUpdateEvent):
        return None
    if not event.message_delta:
        return None
    return [get_message(m, agent_name, event.author) for m in event.message_delta]
