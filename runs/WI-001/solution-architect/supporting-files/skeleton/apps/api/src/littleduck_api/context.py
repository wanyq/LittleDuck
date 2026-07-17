from collections.abc import Callable
from dataclasses import dataclass

TokenCounter = Callable[[list[dict[str, str]]], int]


@dataclass(frozen=True)
class TokenBudget:
    context_window_tokens: int
    max_output_tokens: int
    prompt_overhead_tokens: int

    @property
    def available_input_tokens(self) -> int:
        return max(
            1,
            self.context_window_tokens
            - self.max_output_tokens
            - self.prompt_overhead_tokens,
        )


def conservative_token_estimate(messages: list[dict[str, str]]) -> int:
    """Provider-independent upper-bound estimate; provider adapters may replace it."""
    return sum(4 + len(item["role"].encode()) + len(item["content"].encode()) for item in messages)


def select_complete_turns(
    turns: list[tuple[str, str]],
    current_user_content: str,
    budget: TokenBudget,
    count_tokens: TokenCounter = conservative_token_estimate,
) -> tuple[list[dict[str, str]], int]:
    """Drop the earliest whole user/assistant turns until the model input fits."""
    selected = list(turns)
    while True:
        prompt = [
            item
            for user_content, assistant_content in selected
            for item in (
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content},
            )
        ]
        prompt.append({"role": "user", "content": current_user_content})
        estimate = count_tokens(prompt)
        if estimate <= budget.available_input_tokens or not selected:
            return prompt, estimate
        selected.pop(0)
