"""Deterministic fake provider for tests and keyless development. Never calls a network."""
from dataclasses import dataclass, field


@dataclass
class ProviderReply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


@dataclass
class FakeProvider:
    reply: str = "fake reply"
    cost_usd: float = 0.001
    failing: set[str] = field(default_factory=set)  # model names that raise
    calls: list[str] = field(default_factory=list)

    async def __call__(self, model: str, messages: list[dict], timeout: float) -> ProviderReply:
        self.calls.append(model)
        if model in self.failing:
            raise ConnectionError(f"{model} is disabled")
        words = sum(len(m.get("content", "").split()) for m in messages)
        return ProviderReply(self.reply, input_tokens=words, output_tokens=len(self.reply.split()), cost_usd=self.cost_usd)
