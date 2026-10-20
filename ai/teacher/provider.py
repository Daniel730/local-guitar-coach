"""Model adapter layer (MVP-5).

The Teacher talks to an LLM only through LLMProvider. OllamaProvider is the
real backend; FakeLLMProvider is deterministic and lets us test the safety
of the whole pipeline WITHOUT depending on Ollama being installed/online.

Providers NEVER execute actions — they only return text (ideally JSON). The
Teacher parses and the Policy engine decides. This keeps the LLM fully
decoupled from application side effects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LLMProvider(ABC):
    @abstractmethod
    def generate(self, system_prompt: str, user_prompt: str, timeout_s: float = 30.0) -> str:
        """Return the model's raw text response. Must raise on failure
        (offline, timeout, unavailable) so the Teacher can fall back."""
        ...


class FakeLLMProvider(LLMProvider):
    """Deterministic provider for tests and offline use.

    mode selects behavior:
      "slow_down_95"  -> valid SLOW_DOWN at 95 (uses self.exercise_id)
      "speed_up_300"  -> valid action but BPM 300 (policy must reject)
      "teleport"      -> invalid action enum (policy must reject)
      "garbage"       -> not JSON (schema must reject -> fallback)
      "made_up_ex"    -> valid action but unknown exercise_id (policy must reject)
      "explain"       -> EXPLAIN asking for clarification (missing data case)
      "unavailable"   -> raises (simulates Ollama down -> fallback)
    """

    def __init__(self, mode: str = "slow_down_95", exercise_id: str = "alternate_picking_001") -> None:
        self.mode = mode
        self.exercise_id = exercise_id

    def generate(self, system_prompt: str, user_prompt: str, timeout_s: float = 30.0) -> str:
        ex = self.exercise_id
        if self.mode == "unavailable":
            raise RuntimeError("FakeLLM: simulated Ollama unavailable")
        if self.mode == "garbage":
            return "bro let's just slow it down a bit ok?"
        if self.mode == "teleport":
            return '{"action": "TELEPORT_PLAYER", "reason": "why not"}'
        if self.mode == "speed_up_300":
            return f'{{"action": "SPEED_UP", "exercise_id": "{ex}", "tempo": 300, "reason": "go fast", "spoken_feedback": "vai"}}'
        if self.mode == "made_up_ex":
            return '{"action": "CHANGE_EXERCISE", "exercise_id": "made_up_exercise", "reason": "new", "spoken_feedback": "ok"}'
        if self.mode == "explain":
            return '{"action": "EXPLAIN", "reason": "insufficient data", "spoken_feedback": "Preciso saber o seu timing mais recente."}'
        if self.mode == "slow_down_95":
            return f'{{"action": "SLOW_DOWN", "exercise_id": "{ex}", "tempo": 95, "reason": "Timing dropped while notes stayed accurate.", "spoken_feedback": "As notas estão boas, mas o timing caiu. Vamos baixar para 95 BPM."}}'
        # default: REPEAT at stable tempo
        return f'{{"action": "REPEAT", "exercise_id": "{ex}", "tempo": 90, "reason": "stabilize", "spoken_feedback": "Mais uma."}}'


class OllamaProvider(LLMProvider):
    """Real Ollama backend. Lazy import so the package works without ollama SDK."""

    DEFAULT_HOST = "http://localhost:11434"
    # Ollama can be slow on cold start (model load). 60s avoids false fallback.
    DEFAULT_TIMEOUT_S = 60.0

    def __init__(self, model: str = "llama3.1:8b", host: Optional[str] = None,
                 think: Optional[str] = None) -> None:
        self.model = model
        self.host = host or self.DEFAULT_HOST
        # Reasoning models (e.g. gpt-oss) need think="low" to answer within the timeout;
        # None = don't send the flag (non-thinking models reject it).
        self.think = think
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import ollama
            except ImportError:
                raise RuntimeError("ollama package not installed")
            # ollama 0.6.x takes timeout at the Client level, not in chat().
            self._client = ollama.Client(host=self.host, timeout=self.DEFAULT_TIMEOUT_S)

    def generate(self, system_prompt: str, user_prompt: str, timeout_s: float = None) -> str:
        self._ensure_client()
        try:
            resp = self._client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                options={"temperature": 0.2},
                **({"think": self.think} if self.think else {}),
            )
            return resp["message"]["content"]
        except Exception as e:  # noqa: BLE001 — any failure -> let Teacher fall back
            raise RuntimeError(f"Ollama failure: {e}")
