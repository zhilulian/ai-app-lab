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

from typing import Any, AsyncIterable, Dict, List

from volcenginesdkarkruntime import AsyncArk
from volcenginesdkarkruntime.resources.chat import AsyncChat
from volcenginesdkarkruntime.resources.chat.completions import AsyncCompletions
from volcenginesdkarkruntime.types.chat import ChatCompletionMessageParam
from volcenginesdkarkruntime.types.chat.chat_completion_message import (
    ChatCompletionMessage,
)

from arkitect.core.component.tool.tool_pool import ToolPool
from arkitect.types.llm.model import ArkChatParameters, Message
from arkitect.types.responses.event import BaseEvent, MessageEvent, StateUpdateEvent

from .model import State


class _AsyncCompletions(AsyncCompletions):
    def __init__(
        self, client: AsyncArk, state: State, parameters: ArkChatParameters | None
    ):
        self._state = state
        self.parameters = parameters
        super().__init__(client)

    async def create_event_stream(
        self,
        model: str,
        messages: List[ChatCompletionMessageParam],
        tool_pool: ToolPool | None = None,
        **kwargs: Dict[str, Any],
    ) -> AsyncIterable[BaseEvent]:
        parameters = self.parameters.__dict__ if self.parameters is not None else {}
        if tool_pool:
            tools = await tool_pool.list_tools()
            parameters["tools"] = [t.model_dump() for t in tools]
        resp = await super().create(
            model=model,
            messages=messages,
            stream=True,
            **parameters,
            **kwargs,
        )

        async def iterator() -> AsyncIterable[BaseEvent]:
            final_tool_calls = {}
            chat_completion_messages = ChatCompletionMessage(
                role="assistant",
                content="",
                reasoning_content="",
                tool_calls=[],
            )
            async for chunk in resp:
                if len(chunk.choices) > 0:
                    if chunk.choices[0].delta.content:
                        chat_completion_messages.content += chunk.choices[
                            0
                        ].delta.content
                    if chunk.choices[0].delta.reasoning_content:
                        chat_completion_messages.reasoning_content += chunk.choices[
                            0
                        ].delta.reasoning_content
                    if chunk.choices[0].delta.tool_calls:
                        for tool_call in chunk.choices[0].delta.tool_calls:
                            index = tool_call.index
                            if index not in final_tool_calls:
                                final_tool_calls[index] = tool_call
                            else:
                                final_tool_calls[
                                    index
                                ].function.arguments += tool_call.function.arguments
                yield MessageEvent(**chunk.model_dump())
            chat_completion_messages.tool_calls = [
                v.model_dump() for v in final_tool_calls.values()
            ]
            yield StateUpdateEvent(
                message_delta=[
                    Message(
                        content=chat_completion_messages.content,
                        reasoning_content=chat_completion_messages.reasoning_content,
                        role=chat_completion_messages.role,
                        tool_calls=chat_completion_messages.tool_calls,
                    )
                ]
            )

        return iterator()


class _AsyncChat(AsyncChat):
    def __init__(
        self,
        client: AsyncArk,
        state: State,
        parameters: ArkChatParameters | None,
    ):
        self._state = state
        self.parameters = parameters
        super().__init__(client)

    @property
    def completions(self) -> _AsyncCompletions:
        return _AsyncCompletions(self._client, self._state, self.parameters)
