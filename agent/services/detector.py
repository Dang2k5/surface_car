from __future__ import annotations

from typing import Any, Protocol

from agent.graph.state import QCState


class DetectorService(Protocol):
    def detect(self, state: QCState) -> dict[str, Any]: ...
