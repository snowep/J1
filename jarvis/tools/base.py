"""
Tool base — common interface for all tools.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from ..agent.state import ActionResult


class BaseTool(ABC):
    """Abstract base class for all tools.

    Tools receive validated Action objects and return ActionResult.
    Tools NEVER receive raw LLM output — only validated actions
    that have passed the policy engine.
    """

    #: capability name required to use this tool (e.g. "filesystem.read")
    required_capability: str = ""

    @abstractmethod
    def execute(self, **kwargs: Any) -> ActionResult:
        """Execute the tool with validated arguments."""
        raise NotImplementedError