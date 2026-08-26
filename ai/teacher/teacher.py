"""Teacher Brain (MVP-5) — orchestrator.

Flow (per Architecture §15/§16):
    context -> LLM -> raw JSON -> Schema Validation -> Policy Validation
    PASS  -> accepted action (ready for Session Controller)
    FAIL  -> deterministic fallback (system keeps working)

The LLM PROPOSES; the system DECIDES. The Teacher never executes anything.

Decision frequency: ONE decision per PerformanceResult / user request, NEVER
per frame/note/event. The real-time musical engine runs independently.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .provider import LLMProvider, FakeLLMProvider
from .context import TeacherContext
from .validator import validate_action, load_schema
from .policy import PolicyValidator, PolicyVerdict, REASON_BPM_TOO_HIGH, REASON_BPM_TOO_LOW

# Actions that imply a tempo parameter.
_TEMPO_ACTIONS = {"SLOW_DOWN", "SPEED_UP", "REPEAT", "START_EXERCISE"}


@dataclass
class TeacherDecision:
    accepted: bool
    action: Optional[str] = None
    exercise_id: Optional[str] = None
    tempo: Optional[float] = None
    reason: Optional[str] = None
    spoken_feedback: Optional[str] = None
    source: str = "llm"  # "llm" | "fallback" | "schema_fail" | "policy_fail"
    raw: Optional[str] = None


class Teacher:
    def __init__(
        self,
        provider: LLMProvider = None,
        policy: PolicyValidator = None,
        schema: dict = None,
        fallback_exercise_id: str = "alternate_picking_001",
        fallback_stable_bpm: float = 90.0,
    ) -> None:
        self.provider = provider or FakeLLMProvider()
        self.policy = policy or PolicyValidator()
        self.schema = schema or load_schema()
        self.fallback_exercise_id = fallback_exercise_id
        self.fallback_stable_bpm = fallback_stable_bpm

    def decide(self, context: TeacherContext, user_request: str = "") -> TeacherDecision:
        """Produce one pedagogical decision for a PerformanceResult/request."""
        system = self._system_prompt()
        user = self._decision_prompt(context, user_request)
        try:
            raw = self.provider.generate(system, user)
        except Exception:
            return self._fallback("llm unavailable / timeout")
        return self._validate(raw, context)

    def answer(self, context: TeacherContext, user_request: str) -> TeacherDecision:
        """Contextual conversation turn (ARCH §18)."""
        from ai.prompts import CONVERSATION
        user = (
            CONVERSATION
            .replace("{{teacher_context}}", context.rendered or _render(context))
            .replace("{{current_exercise}}", str(context.current_exercise))
            .replace("{{latest_performance}}", str(context.latest_performance))
            .replace("{{user_request}}", user_request)
        )
        try:
            raw = self.provider.generate(self._system_prompt(), user)
        except Exception:
            return self._fallback("llm unavailable / timeout")
        return self._validate(raw, context, allow_explain=True)

    # --- internal ---
    def _validate(self, raw: str, context: TeacherContext, allow_explain: bool = False) -> TeacherDecision:
        ok, data, err = validate_action(raw, self.schema)
        if not ok:
            # Schema violation -> do NOT invent; fall back deterministically.
            return self._fallback(f"schema invalid: {err}", raw=raw)
        action = data["action"]
        ex_id = data.get("exercise_id")
        tempo = data.get("tempo")

        verdict: PolicyVerdict = self.policy.validate(action, ex_id, tempo)
        if not verdict.allowed:
            # Policy rejection -> deterministic fallback, never execute.
            return TeacherDecision(
                accepted=False,
                action=action,
                reason=f"policy rejected: {verdict.reason}",
                spoken_feedback=None,
                source="policy_fail",
                raw=raw,
            )
        return TeacherDecision(
            accepted=True,
            action=verdict.action,
            exercise_id=verdict.exercise_id,
            tempo=verdict.tempo,
            reason=data.get("reason"),
            spoken_feedback=data.get("spoken_feedback"),
            source="llm",
            raw=raw,
        )

    def _fallback(self, why: str, raw: str = None) -> TeacherDecision:
        """Deterministic fallback. AI failure != application failure.

        Policy: if latest timing was weak, REPEAT at stable_bpm; otherwise
        REPEAT current exercise. Never invents measurements or new exercises.
        """
        return TeacherDecision(
            accepted=True,
            action="REPEAT",
            exercise_id=self.fallback_exercise_id,
            tempo=self.fallback_stable_bpm,
            reason=f"fallback ({why})",
            spoken_feedback="Vamos repetir no mesmo tempo para estabilizar.",
            source="fallback",
            raw=raw,
        )

    def _system_prompt(self) -> str:
        from ai.prompts import TEACHER_SYSTEM
        return TEACHER_SYSTEM

    def _decision_prompt(self, context: TeacherContext, user_request: str) -> str:
        from ai.prompts import TEACHER_DECISION
        ctx_txt = context.rendered or _render(context)
        return (
            TEACHER_DECISION
            .replace("{{teacher_context}}", ctx_txt)
            .replace("{{user_request}}", user_request or "")
        )


def _render(context: TeacherContext) -> str:
    """Render the bounded context as text for the prompt."""
    lines = []
    if context.student:
        lines.append(f"student: {context.student}")
    if context.current_skill:
        lines.append(f"current_skill: {context.current_skill}")
    if context.current_exercise:
        lines.append(f"current_exercise: {context.current_exercise}")
    if context.latest_performance:
        lines.append(f"latest_performance: {context.latest_performance}")
    lines.append(f"available_exercises: {context.available_exercises}")
    lines.append(f"voice_mode: {context.voice_mode}")
    return "\n".join(lines)
