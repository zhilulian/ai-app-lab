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

# Copyright 2025 Bytedance Ltd. and/or its affiliates

# Licensed under the 【火山方舟】原型应用软件自用许可协议
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     https://www.volcengine.com/docs/82379/1433703
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import Any, AsyncIterable

from arkitect.core.component.agent import BaseAgent
from arkitect.core.component.checkpoint import BaseCheckpointService
from arkitect.core.component.checkpoint.checkpoint import Checkpoint
from arkitect.core.component.llm_event_stream.model import State
from arkitect.core.component.runner.config import RunnerConfig
from arkitect.telemetry.logger import ERROR
from arkitect.telemetry.trace import task
from arkitect.types.llm.model import Message
from arkitect.types.responses.event import (
    BaseEvent,
    HookInterruptEvent,
    StateUpdateEvent,
)


class Runner:
    def __init__(
        self,
        app_name: str,
        agent: BaseAgent,
        checkpoint_service: BaseCheckpointService | None = None,
        config: RunnerConfig = RunnerConfig(),
    ):
        self.app_name = app_name
        self.agent = agent
        self.checkpoint_service = checkpoint_service
        self.config = config

    async def run(
        self,
        messages: list[Message] | None = None,
        checkpoint_id: str | None = None,
        state: State | None = None,
        user_id: str = "",
        **kwargs: Any,
    ) -> AsyncIterable[BaseEvent]:
        checkpoint: Checkpoint = await self.get_or_create_checkpoint(
            checkpoint_id=checkpoint_id, user_id=user_id
        )
        if state is not None:
            checkpoint.state = state
        async for chunk in self.__run(checkpoint.state, checkpoint, messages, **kwargs):
            if isinstance(chunk, BaseEvent):
                yield chunk

    @task()
    async def process_event(
        self, event: BaseEvent, state: State, checkpoint: Checkpoint
    ) -> AsyncIterable[BaseEvent]:
        if isinstance(event, StateUpdateEvent):
            if event.details_delta is not None:
                state.details.update(event.details_delta)
            if event.message_delta is not None and len(event.message_delta) > 0:
                state.events.append(event)
            if self.checkpoint_service:
                await self.checkpoint_service.update_checkpoint(
                    self.app_name, checkpoint.id, checkpoint
                )
            return
        yield event

    async def __run(
        self,
        state: State,
        checkpoint: Checkpoint,
        messages: list[Message] | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[BaseEvent]:
        if messages is not None:
            append_messages = StateUpdateEvent(
                author="user",
                message_delta=messages,
            )
            async for event in self.process_event(append_messages, state, checkpoint):
                continue
        try:
            async for event in self.agent(state, **kwargs):
                async for event in self.process_event(event, state, checkpoint):
                    yield event
                if isinstance(event, HookInterruptEvent):
                    # stop further execution
                    break
        except Exception as e:
            ERROR(f"I have error: {e}")
        finally:
            if self.checkpoint_service:
                await self.checkpoint_service.update_checkpoint(
                    self.app_name, checkpoint.id, checkpoint
                )

    async def get_or_create_checkpoint(
        self, checkpoint_id: str | None, user_id: str = ""
    ) -> Checkpoint:
        if not self.checkpoint_service:
            if checkpoint_id:
                return Checkpoint(
                    id=checkpoint_id, app_name=self.app_name, user_id=user_id
                )
            return Checkpoint(app_name=self.app_name, user_id=user_id)
        if checkpoint_id is not None:
            checkpoint = await self.checkpoint_service.get_checkpoint(
                app_name=self.app_name, checkpoint_id=checkpoint_id
            )
        if checkpoint is None or checkpoint_id is None:
            checkpoint_id = ""
            checkpoint = await self.checkpoint_service.create_checkpoint(
                app_name=self.app_name,
                checkpoint_id=checkpoint_id,
                user_id=user_id,
            )
        return checkpoint
