"""Sequence Matcher (MVP-3).

Compares an EXPECTED note sequence (from an exercise) against the PLAYED
note sequence (NoteEvents from the MVP-2 Event Tracker) using a musical
sequence-alignment (Needleman-Wunsch style DP), NOT index-by-index compare.

Why alignment instead of zip():
A single inserted/extra note shifts every following note. Naive index compare
would mark all shifted notes wrong. Alignment finds the best global match and
classifies each position as:

    correct   - expected == played
    wrong     - both present, different note (substitution)
    missing   - expected note absent in played
    extra     - played note absent in expected
    uncertain - played note was flagged uncertain by the tracker

This layer NEVER scores (no accuracy %). Scoring is MVP-4. It only reports
WHAT happened. Timestamps from NoteEvents are preserved for MVP-4 rhythm work.

Interface is kept clean so the alignment cost model can be improved later.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Status vocabulary (explicit, shared).
CORRECT = "correct"
WRONG = "wrong"
MISSING = "missing"
EXTRA = "extra"
UNCERTAIN = "uncertain"

# Gap symbol for alignment (no note on this side).
GAP = None


@dataclass
class AlignedNote:
    expected: Optional[str]
    played: Optional[str]
    status: str
    # timestamps preserved from the played NoteEvent (None if missing/extra-side gap)
    played_start: Optional[float] = None
    played_end: Optional[float] = None
    played_duration: Optional[float] = None
    played_uncertain: Optional[bool] = None

    def to_dict(self) -> dict:
        d = {
            "expected": self.expected,
            "played": self.played,
            "status": self.status,
        }
        if self.played_start is not None:
            d["played_start"] = round(self.played_start, 3)
        if self.played_end is not None:
            d["played_end"] = round(self.played_end, 3)
        if self.played_duration is not None:
            d["played_duration"] = round(self.played_duration, 3)
        if self.played_uncertain is not None:
            d["played_uncertain"] = self.played_uncertain
        return d


@dataclass
class Comparison:
    exercise_id: str
    expected: List[str]
    played: List[str]
    alignment: List[AlignedNote] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "exercise_id": self.exercise_id,
            "expected": self.expected,
            "played": self.played,
            "alignment": [a.to_dict() for a in self.alignment],
        }


class SequenceMatcher:
    """Musical sequence alignment via Needleman-Wunsch DP.

    Cost model (kept simple, swappable later):
      match (expected == played, played not uncertain) : +2
      uncertain match (notes equal but played uncertain) : +1 (still aligned, flagged)
      substitution (both present, differ)                : -1
      gap (missing or extra)                             : -1
    We maximize; backtracking yields the alignment path.
    """

    def __init__(self, match=2, uncertain_match=1, mismatch=-1, gap=-1) -> None:
        self.match = match
        self.uncertain_match = uncertain_match
        self.mismatch = mismatch
        self.gap = gap

    def _score(self, exp: Optional[str], played: Optional[tuple], exp_idx: int, played_idx: int) -> int:
        if exp is GAP or played is None:
            return self.gap
        p_note, p_uncertain = played
        if p_note is None:
            return self.gap
        if exp == p_note:
            return self.uncertain_match if p_uncertain else self.match
        return self.mismatch

    def align(
        self,
        expected: List[str],
        played: List[tuple],  # list of (note, uncertain)
    ) -> List[AlignedNote]:
        n = len(expected)
        m = len(played)
        # DP table
        dp = [[0] * (m + 1) for _ in range(n + 1)]
        for i in range(1, n + 1):
            dp[i][0] = i * self.gap
        for j in range(1, m + 1):
            dp[0][j] = j * self.gap
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                diag = dp[i - 1][j - 1] + self._score(expected[i - 1], played[j - 1], i - 1, j - 1)
                up = dp[i - 1][j] + self.gap
                left = dp[i][j - 1] + self.gap
                dp[i][j] = max(diag, up, left)
        # Backtrack
        i, j = n, m
        out: List[AlignedNote] = []
        while i > 0 or j > 0:
            if i > 0 and j > 0:
                diag = dp[i - 1][j - 1] + self._score(expected[i - 1], played[j - 1], i - 1, j - 1)
                if diag == dp[i][j]:
                    exp = expected[i - 1]
                    p_note, p_unc = played[j - 1]
                    if p_note is None:
                        status = MISSING
                    elif exp == p_note:
                        status = UNCERTAIN if p_unc else CORRECT
                    else:
                        status = WRONG
                    out.append(self._mk(exp, p_note, p_unc, status))
                    i -= 1
                    j -= 1
                    continue
            if i > 0 and (j == 0 or dp[i - 1][j] + self.gap == dp[i][j]):
                out.append(self._mk(expected[i - 1], None, None, MISSING))
                i -= 1
                continue
            if j > 0 and (i == 0 or dp[i][j - 1] + self.gap == dp[i][j]):
                p_note, p_unc = played[j - 1]
                out.append(self._mk(None, p_note, p_unc, EXTRA))
                j -= 1
                continue
            # fallback (should not reach)
            if i > 0:
                out.append(self._mk(expected[i - 1], None, None, MISSING))
                i -= 1
            else:
                p_note, p_unc = played[j - 1]
                out.append(self._mk(None, p_note, p_unc, EXTRA))
                j -= 1
        out.reverse()
        return out

    def _mk(self, exp, p_note, p_unc, status) -> AlignedNote:
        # timestamps are attached by the caller (compare()) via indices; here we
        # only build the status shell. We pass None and let compare() fill them.
        return AlignedNote(
            expected=exp,
            played=p_note,
            status=status,
            played_uncertain=p_unc,
        )


def compare(exercise_id: str, expected: List[str], played_events) -> Comparison:
    """Build a Comparison from an expected note list and played NoteEvents.

    `played_events` is a list of perception.events.NoteEvent (or objects with
    .note, .uncertain, .start, .end, .duration). Alignment is by note name;
    timestamps are carried over from the matched played event.
    """
    played_tuples = [(e.note, getattr(e, "uncertain", False)) for e in played_events]
    matcher = SequenceMatcher()
    aligned = matcher.align(expected, played_tuples)

    # Re-attach timestamps: walk played_events in order, assign to the first
    # aligned slot that consumes a played note.
    pe_iter = iter(played_events)
    cur = None
    result: List[AlignedNote] = []
    for a in aligned:
        if a.expected is not None and a.played is not None:
            # matched: pull next played event
            if cur is None:
                cur = next(pe_iter, None)
            ev = cur
            cur = None
        elif a.played is not None and a.expected is None:
            # extra: pull next played event
            if cur is None:
                cur = next(pe_iter, None)
            ev = cur
            cur = None
        else:
            ev = None
        if ev is not None and a.played == ev.note:
            a.played_start = ev.start
            a.played_end = ev.end
            a.played_duration = ev.duration
        result.append(a)
    # (If ordering of played matches alignment side perfectly, timestamps align.
    #  Edge: substitutions pull the right event by iteration order, which matches
    #  the DP path since both consume one played slot.)

    return Comparison(
        exercise_id=exercise_id,
        expected=list(expected),
        played=[e.note for e in played_events],
        alignment=result,
    )
