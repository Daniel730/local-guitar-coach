"""TeacherService — wraps existing Teacher + Policy + Context for WebSocket sessions."""
from __future__ import annotations
from typing import Optional, Dict, Any
import json

from ai.teacher import Teacher, TeacherContext, TeacherDecision, PolicyValidator, FakeLLMProvider
from ai.teacher.provider import OllamaProvider
from ai.teacher.build_context import build_context
from perception.performance import PerformanceResult, PerformanceEvaluator
from perception.sequence import compare
from perception.events import NoteEvent


class TeacherService:
    """Orchestrates Teacher decision for a session.

    CHANGE-05: tempo/BPM is a property of the exercise (the content). This
    service reads start_bpm/target_bpm/subdivision from the loaded Exercise
    definition — it does NOT keep an independent copy of the tempo.
    """

    def __init__(
        self,
        exercise_id: str,
        ollama_model: str = "llama3.1:8b",
        fail_ollama: bool = False,
    ) -> None:
        self.exercise_id = exercise_id

        # Load exercise details (single source of truth for tempo, CHANGE-05).
        from exercises.exercise import load_exercise
        ex_path = f"exercises/{exercise_id}.json"
        self.exercise = load_exercise(ex_path)
        if self.exercise.target_bpm is None or self.exercise.subdivision is None:
            raise ValueError(f"Exercise {exercise_id} missing tempo (target_bpm/subdivision)")

        # Provider
        if fail_ollama:
            self.provider = FakeLLMProvider(mode="unavailable")
        else:
            self.provider = OllamaProvider(model=ollama_model)

        # Policy — tempo bounds come from the exercise definition.
        self.policy = PolicyValidator(
            available_exercises={
                exercise_id: {
                    "start_bpm": self.exercise.start_bpm,
                    "target_bpm": self.exercise.target_bpm,
                    "enabled": True,
                    "prerequisites": [],
                }
            },
            session_active=True,
            time_remaining_s=600.0,
        )

        self.teacher = Teacher(provider=self.provider, policy=self.policy)

        self._note_events: list[NoteEvent] = []
        self._comparison = None
        self._performance: Optional[PerformanceResult] = None
        self._last_decision: Optional[TeacherDecision] = None

    def add_note_event(self, note_event: NoteEvent) -> None:
        self._note_events.append(note_event)

    def evaluate_and_decide(self) -> TeacherDecision:
        """Run the full pipeline: compare -> performance -> context -> teacher."""
        from perception.sequence import compare
        from perception.performance import PerformanceEvaluator
        from ai.teacher.build_context import build_context

        # Tempo from the exercise definition (CHANGE-05).
        target_bpm = self.exercise.target_bpm
        subdivision = self.exercise.subdivision
        start_bpm = self.exercise.start_bpm

        # Compare
        self._comparison = compare(
            self.exercise_id,
            self.exercise.expected_sequence,
            self._note_events,
        )

        # Estimate performed BPM from note events
        performed_bpm = self._estimate_bpm(
            self._note_events,
            subdivision,
            target_bpm,
        )

        # Evaluate performance
        evaluator = PerformanceEvaluator()
        self._performance = evaluator.evaluate(
            self._comparison,
            target_bpm=target_bpm,
            subdivision=subdivision,
            performed_bpm=performed_bpm,
        )

        # Build context
        ctx = build_context(
            student_profile={"experience": "beginner", "goals": ["rock"], "practice_minutes": 30},
            exercise={"id": self.exercise_id, "start_bpm": start_bpm, "target_bpm": target_bpm},
            performance=self._performance,
            available_exercises=[self.exercise_id],
            voice_mode="COACH",
        )
        ctx.rendered = json.dumps(ctx.to_dict(), ensure_ascii=False)

        # Teacher decision
        decision = self.teacher.decide(ctx)
        self._last_decision = decision
        return decision

    def get_teacher_telemetry(self) -> dict:
        if self._last_decision is None:
            return {}
        d = self._last_decision
        return {
            "type": "teacher",
            "action": d.action,
            "exercise_id": d.exercise_id,
            "tempo": d.tempo,
            "reason": d.reason,
            "spoken_feedback": d.spoken_feedback,
            "source": d.source,
        }

    def get_performance_telemetry(self) -> dict:
        if self._performance is None:
            return {}
        return self._performance.to_dict()

    @staticmethod
    def _estimate_bpm(note_events, subdivision: str, target_bpm: float) -> float | None:
        """Crude performed BPM from inter-onset distance."""
        if len(note_events) < 2:
            return None
        starts = sorted(e.start for e in note_events if hasattr(e, "start") and e.start is not None)
        if len(starts) < 2:
            return None
        import numpy as np
        diffs = np.diff(starts)
        diffs = diffs[diffs > 0.05]
        if len(diffs) == 0:
            return None
        median_gap = float(np.median(diffs))
        factor = {"quarter": 1.0, "eighth": 0.5, "half": 2.0, "sixteenth": 0.25}.get(subdivision, 1.0)
        beat = median_gap / factor if factor else median_gap
        if beat <= 0:
            return None
        return round(60.0 / beat, 1)

    def reset(self) -> None:
        self._note_events = []
        self._comparison = None
        self._performance = None
        self._last_decision = None
