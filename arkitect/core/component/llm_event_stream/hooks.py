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
import abc
from typing import Any, AsyncIterable, Optional, Union

from arkitect.types.responses.event import (
    BaseEvent,
    HookInterruptEvent,
)

from .model import State


class PreToolCallHook(abc.ABC):
    @abc.abstractmethod
    async def pre_tool_call(
        self,
        name: str,
        arguments: str,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        return
        yield


class PostToolCallHook(abc.ABC):
    @abc.abstractmethod
    async def post_tool_call(
        self,
        name: str,
        arguments: str,
        response: Any,
        exception: Optional[Exception],
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        return
        yield


class PreLLMCallHook(abc.ABC):
    @abc.abstractmethod
    async def pre_llm_call(
        self,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        return
        yield


class PostLLMCallHook(abc.ABC):
    @abc.abstractmethod
    async def post_llm_call(
        self,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        return
        yield


Hook = Union[
    PreToolCallHook,
    PostToolCallHook,
    PreLLMCallHook,
    PostLLMCallHook,
]


class ApprovalHook(PreToolCallHook):
    async def pre_tool_call(
        self,
        name: str,
        arguments: str,
        state: State,
    ) -> AsyncIterable[BaseEvent]:
        if len(state.events) == 0:
            return
        last_message = state.events[-1].message_delta
        if not last_message or len(last_message) == 0:
            return
        if last_message[-1].tool_calls:
            return

        formated_output = []
        for tool_call in last_message.tool_calls:  # type: ignore
            tool_name = tool_call.function.name
            tool_call_param = tool_call.function.arguments
            formated_output.append(
                f"tool_name: {tool_name}\ntool_call_param: {tool_call_param}\n"
            )
        print("tool call parameters:")
        print("".join(formated_output))
        y_or_n = input("input Y to approve\n")
        if y_or_n == "Y":
            return
        else:
            yield HookInterruptEvent(
                life_cycle="tool_call",
                reason="approval failed",
                details={
                    "tool_name": tool_name,
                    "tool_call_param": tool_call_param,
                },
            )
