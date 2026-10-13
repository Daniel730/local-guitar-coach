"""Skill / Subskill domain entities (CHANGE-06).

Minimal domain contract for skills and subskills. This is the FOUNDATION for
the future learning system — it defines the vocabulary (what a skill is, what
a subskill is) and validates that exercises reference known skills. It does
NOT implement progression, adaptive learning, or a curriculum engine (those are
later CHANGEs).

A skill is a broad capability (e.g. "pentatonic", "alternate_picking"). A
subskill is a narrower facet of a skill (e.g. "minor_pentatonic"). An exercise
develops one skill and optionally one subskill.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class Skill:
    """A broad guitar capability."""
    id: str
    name: str
    description: str = ""
    subskills: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class Subskill:
    """A narrower facet of a skill."""
    id: str
    skill_id: str
    name: str
    description: str = ""


# Known skills (content contract). Extensible — add entries, no code change.
KNOWN_SKILLS: dict[str, Skill] = {
    "pentatonic": Skill(
        id="pentatonic",
        name="Pentatonic Scales",
        description="Pentatonic scale patterns and positions.",
        subskills=["minor_pentatonic", "major_pentatonic"],
    ),
    "alternate_picking": Skill(
        id="alternate_picking",
        name="Alternate Picking",
        description="Down-up picking technique for clean single-note lines.",
        subskills=["string_crossing", "economy"],
    ),
    "chords": Skill(
        id="chords",
        name="Chords",
        description="Open, barre, and movable chord shapes and transitions.",
        subskills=["open_chords", "barre_chords", "power_chords"],
    ),
    "rhythm": Skill(
        id="rhythm",
        name="Rhythm & Timing",
        description="Subdivisions, strumming patterns, and steady time.",
        subskills=["eighth_notes", "sixteenth_notes", "syncopation"],
    ),
    "technique": Skill(
        id="technique",
        name="Left-Hand Technique",
        description="Hammer-ons, pull-offs, slides, bends, vibrato, legato.",
        subskills=["hammer_on", "pull_off", "bends", "vibrato", "legato"],
    ),
}

# Known subskills (content contract).
KNOWN_SUBSKILLS: dict[str, Subskill] = {
    "minor_pentatonic": Subskill("minor_pentatonic", "pentatonic", "Minor Pentatonic", "Minor pentatonic scale patterns."),
    "major_pentatonic": Subskill("major_pentatonic", "pentatonic", "Major Pentatonic", "Major pentatonic scale patterns."),
    "string_crossing": Subskill("string_crossing", "alternate_picking", "String Crossing", "Alternate picking across strings."),
    "economy": Subskill("economy", "alternate_picking", "Economy Picking", "Economy picking technique."),
    "open_chords": Subskill("open_chords", "chords", "Open Chords", "Open-position chord shapes."),
    "barre_chords": Subskill("barre_chords", "chords", "Barre Chords", "Movable barre chord shapes."),
    "power_chords": Subskill("power_chords", "chords", "Power Chords", "Two/three-note power chords."),
    "eighth_notes": Subskill("eighth_notes", "rhythm", "Eighth Notes", "Eighth-note subdivision."),
    "sixteenth_notes": Subskill("sixteenth_notes", "rhythm", "Sixteenth Notes", "Sixteenth-note subdivision."),
    "syncopation": Subskill("syncopation", "rhythm", "Syncopation", "Off-beat accents."),
    "hammer_on": Subskill("hammer_on", "technique", "Hammer-On", "Hammer-on articulation."),
    "pull_off": Subskill("pull_off", "technique", "Pull-Off", "Pull-off articulation."),
    "bends": Subskill("bends", "technique", "Bends", "String bends."),
    "vibrato": Subskill("vibrato", "technique", "Vibrato", "Vibrato technique."),
    "legato": Subskill("legato", "technique", "Legato", "Legato phrasing."),
}


def get_skill(skill_id: str) -> Optional[Skill]:
    return KNOWN_SKILLS.get(skill_id)


def get_subskill(subskill_id: str) -> Optional[Subskill]:
    return KNOWN_SUBSKILLS.get(subskill_id)


def validate_exercise_skill(skill_id: str, subskill_id: Optional[str] = None) -> List[str]:
    """Return a list of validation problems for an exercise's skill reference.

    Empty list = valid. Unknown skill/subskill -> problem (no silent fallback).
    """
    problems: List[str] = []
    skill = get_skill(skill_id)
    if skill is None:
        problems.append(f"unknown skill: {skill_id}")
        return problems
    if subskill_id is not None:
        sub = get_subskill(subskill_id)
        if sub is None:
            problems.append(f"unknown subskill: {subskill_id}")
        elif sub.skill_id != skill_id:
            problems.append(f"subskill {subskill_id} does not belong to skill {skill_id}")
    return problems
