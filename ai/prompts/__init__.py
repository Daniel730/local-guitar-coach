"""Prompts for the MVP-5 Teacher Brain.

Kept as files (not inline strings) so different Ollama models can be A/B'd
without touching code. The system prompt is strict: the LLM may reason ONLY
from supplied student data and MUST NOT invent measurements, skills, exercises,
BPM, or history.
"""
import os

_PROMPT_DIR = os.path.dirname(__file__)


def _read(name: str) -> str:
    with open(os.path.join(_PROMPT_DIR, name), encoding="utf-8") as f:
        return f.read()


TEACHER_SYSTEM = _read("teacher_system.txt")
TEACHER_DECISION = _read("teacher_decision.txt")
CONVERSATION = _read("conversation.txt")
