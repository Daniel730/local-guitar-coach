"""Event Tracker (MVP-2).

Interpretation layer ON TOP of raw pitch events from the Perception Engine.
It does NOT touch the pitch detector (YIN) — it groups, stabilizes, and
times the events the detector already produced.

Architecture (per project decision 2026-08-26):
    Audio -> YIN -> Raw Pitch Events -> Event Tracker -> Note Sequence

A NoteEvent is a single musical note with start/end/duration, aggregated
confidence, and an explicit flag for uncertain transitions (so we never
hide uncertainty or silently invent a wrong note).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np


@dataclass
class NoteEvent:
    note: str
    midi: Optional[int]
    start: float
    end: float
    duration: float
    confidence: float
    attack_confidence: float
    uncertain: bool = False
    # raw pitches observed during the event (for debugging / future scoring)
    pitch_samples: List[float] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "note": self.note,
            "midi": self.midi,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "confidence": round(self.confidence, 2),
            "attack_confidence": round(self.attack_confidence, 2),
            "uncertain": self.uncertain,
            "pitch_samples": [round(p, 2) for p in self.pitch_samples],
        }


class EventTracker:
    """Group consecutive raw pitch events into NoteEvents.

    State machine (explicit; each state has an invariant):
        IDLE    : self._open is None
                  invariant: no note in progress
        OPEN    : self._open is not None, self._open["pending"] is None
                  invariant: a single committed note is in progress
        PENDING : self._open is not None, self._open["pending"] is not None
                  invariant: OPEN note ongoing AND a candidate next note exists;
                             pending["midi"]/["since"] are valid (never None)

    Valid transitions:
        IDLE    --pitch-->  OPEN
        OPEN    --same note, small gap-->  OPEN   (refreshes last; cancels pending)
        OPEN    --diff note, small gap-->  PENDING  (creates/refreshes candidate)
        PENDING --candidate persists & matches-->  OPEN  (commit switch)
        PENDING --original returns / candidate dies-->  OPEN  (cancel candidate)
        *       --gap too large / silence-->  IDLE -> OPEN  (close, then open new)

    CRITICAL invariant: _close() sets self._open = None (-> IDLE). Any code that
    needs values from the note being closed MUST snapshot them BEFORE calling
    _close(). Reading self._open after _close() is a state-machine violation
    (this was the source of the historical 'NoneType' subscript crash).
    """

    def __init__(
        self,
        note_change_gap_s: float = 0.12,
        stabilization_s: float = 0.06,
        min_note_duration_s: float = 0.04,
        uncertain_confidence: float = 0.55,
        pitch_tolerance_semitones: float = 1.0,
    ) -> None:
        self.note_change_gap_s = note_change_gap_s
        self.stabilization_s = stabilization_s
        self.min_note_duration_s = min_note_duration_s
        self.uncertain_confidence = uncertain_confidence
        self.pitch_tolerance = pitch_tolerance_semitones
        self._reset()

    def _reset(self) -> None:
        self._events: List[NoteEvent] = []
        self._open: Optional[dict] = None

    def reset(self) -> None:
        self._reset()

    @staticmethod
    def _same_note(midi_a: Optional[int], midi_b: Optional[int]) -> bool:
        if midi_a is None or midi_b is None:
            return False
        return midi_a == midi_b

    def _new_open(self, event, t, conf, note, midi) -> dict:
        return {
            "note": note,
            "midi": midi,
            "start": t,
            "last": t,
            "attack_conf": conf,
            "confs": [conf],
            "pitches": [event.frequency] if hasattr(event, "frequency") else [],
            "onset": getattr(event, "onset", False),
            "pending": None,  # candidate next note during stabilization
            "pending_last": t,
        }

    def process(self, event) -> Optional[NoteEvent]:
        """Feed one raw pitch MusicalEvent. Returns a closed NoteEvent when the
        current note ends, else None.

        `event` must expose: timestamp, note, midi, confidence, onset.
        """
        t = event.timestamp
        note = event.note
        midi = event.midi
        conf = event.confidence
        onset = getattr(event, "onset", False)

        # Silence / no pitch -> close any open note (OPEN/PENDING -> IDLE).
        if note is None or midi is None:
            return self._close(t)

        # IDLE -> OPEN : open a new committed note.
        if self._open is None:
            self._open = self._new_open(event, t, conf, note, midi)
            return None

        open_midi = self._open["midi"]
        gap = t - self._open["last"]

        # OPEN (same note, within gap) : extend + cancel any pending candidate.
        if self._same_note(open_midi, midi) and gap <= self.note_change_gap_s:
            self._open["last"] = t
            self._open["confs"].append(conf)
            if hasattr(event, "frequency"):
                self._open["pitches"].append(event.frequency)
            self._open["pending"] = None  # returning stable note kills candidate
            return None

        # Different note, small gap -> enter/stay PENDING (stabilization).
        if gap <= self.note_change_gap_s:
            pend = self._open["pending"]
            if pend is None:
                # OPEN -> PENDING : create candidate. Invariant: pending valid.
                self._open["pending"] = {"midi": midi, "note": note, "since": t}
            elif midi == pend["midi"]:
                # Candidate still matches -> refresh last-seen.
                pass
            # (divergent frame: original note stays OPEN, pending unchanged;
            #  we do NOT silently swap candidates.)
            # Record the stray pitch for visibility.
            if hasattr(event, "frequency"):
                self._open["pitches"].append(event.frequency)
            # Commit the switch ONLY when the candidate persists long enough AND
            # the current frame still matches it.
            pend = self._open["pending"]
            if pend is not None and midi == pend["midi"]:
                pend_age = t - pend["since"]
                if pend_age >= self.stabilization_s:
                    # The commit instant is the authority for closing the OPEN note:
                    # its effective end is NOW (the transition was just determined),
                    # not the stale last frame. Set last to t so _close() sees the
                    # real duration (last - start) instead of duration 0.
                    self._open["last"] = t
                    # Snapshot pending BEFORE _close() (which sets _open=None).
                    pend_since = pend["since"]
                    closed = self._close(t)
                    # Re-open as the new committed note starting at pend_since.
                    self._open = self._new_open(event, pend_since, conf, note, midi)
                    return closed
            return None

        # Gap too large -> genuine new note. Close previous (-> IDLE), open new.
        closed = self._close(t)
        self._open = self._new_open(event, t, conf, note, midi)
        return closed

    def _close(self, t_end: float) -> Optional[NoteEvent]:
        if self._open is None:
            return None
        o = self._open
        self._open = None
        start, last = o["start"], o["last"]
        duration = last - start
        if duration < self.min_note_duration_s:
            return None
        confs = np.array(o["confs"])
        # Stable confidence: median is robust to transient outliers.
        stable_conf = float(np.median(confs))
        uncertain = stable_conf < self.uncertain_confidence
        ev = NoteEvent(
            note=o["note"],
            midi=o["midi"],
            start=start,
            end=last,
            duration=duration,
            confidence=stable_conf,
            attack_confidence=float(o["attack_conf"]),
            uncertain=uncertain,
            pitch_samples=o["pitches"],
        )
        self._events.append(ev)
        return ev

    def finalize(self) -> List[NoteEvent]:
        """Close any open note and return only that final NoteEvent (or [])."""
        if self._open is None:
            return []
        closed = self._close(self._open["last"])
        return [closed] if closed is not None else []

    @property
    def events(self) -> List[NoteEvent]:
        return self._events
