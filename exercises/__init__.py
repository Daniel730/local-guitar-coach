"""Exercise package (MVP-3): load exercise schemas from JSON, no database."""
from .exercise import Exercise, load_exercise, exercise_from_dict

__all__ = ["Exercise", "load_exercise", "exercise_from_dict"]
