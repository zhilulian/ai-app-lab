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

from datetime import datetime
from typing import Any

from arkitect.core.component.checkpoint.base_checkpoint_service import (
    BaseCheckpointService,
)
from arkitect.core.component.checkpoint.checkpoint import Checkpoint
from arkitect.core.component.llm_event_stream.model import State
from arkitect.utils.common import Singleton


class InMemoryCheckpointService(BaseCheckpointService):
    def __init__(self) -> None:
        # A map from app name to a map from user ID to a map from session ID to session.
        self.checkpoints: dict[str, dict[str, Checkpoint]] = {}

    async def create_checkpoint(
        self,
        app_name: str,
        checkpoint_id: str,
        user_id: str,
        checkpoint: Checkpoint | None = None,
        **kwargs: Any,
    ) -> Checkpoint:
        checkpoint = (
            Checkpoint(
                id=checkpoint_id,
                app_name=app_name,
                user_id=user_id,
                state=State(),
                last_update_time=datetime.now().timestamp(),
                create_time=datetime.now().timestamp(),
            )
            if not checkpoint
            else checkpoint
        )
        if app_name not in self.checkpoints:
            self.checkpoints[app_name] = {}

        self.checkpoints[app_name][checkpoint_id] = checkpoint

        return checkpoint

    async def get_checkpoint(
        self, app_name: str, checkpoint_id: str
    ) -> Checkpoint | None:
        return self.checkpoints.get(app_name, {}).get(checkpoint_id, None)

    async def list_checkpoints(self, app_name: str, **kwargs: Any) -> list[Checkpoint]:
        return list(self.checkpoints.get(app_name, {}).values())

    async def update_checkpoint(
        self, app_name: str, checkpoint_id: str, checkpoint: Checkpoint
    ) -> None:
        checkpoint.last_update_time = datetime.now().timestamp()
        self.checkpoints[app_name][checkpoint_id] = checkpoint

    async def delete_checkpoint(self, app_name: str, checkpoint_id: str) -> None:
        if app_name in self.checkpoints and checkpoint_id in self.checkpoints[app_name]:
            del self.checkpoints[app_name][checkpoint_id]


class InMemoryCheckpointServiceSingleton(InMemoryCheckpointService, Singleton):
    pass
