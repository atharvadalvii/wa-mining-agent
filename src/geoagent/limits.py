"""Per-visitor usage limits, so a public deployment can't run up the OpenAI bill."""

from __future__ import annotations


def check_message(
    messages_sent: int, text: str, max_messages: int, max_chars: int
) -> str | None:
    """Returns a user-facing refusal if this message should not be processed, else None.

    A limit of 0 disables that check.
    """
    if max_chars and len(text) > max_chars:
        return f"That message is too long ({len(text)} characters). Please keep it under {max_chars}."
    if max_messages and messages_sent >= max_messages:
        return (
            f"This session has reached its limit of {max_messages} questions. "
            "Use 'Clear conversation' to start a new one."
        )
    return None
