"""Conversation message-history state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Conversation:
    messages: list[dict] = field(default_factory=list)

    @classmethod
    def start(cls, system_prompt: str) -> "Conversation":
        return cls(messages=[{"role": "system", "content": system_prompt}])

    def add_user(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})
