"""MVP-4 — Performance Model tests (all required edge cases).

Guarantees: no overall_score, dimensions independent, uncertainty never
collapses to wrong, BPM not auto-penalized, stability robust to outliers,
trend needs multiple observations.
"""
from perception.events import NoteEvent
from perception.sequence import compare, CORRECT, WRONG, MISSING, EXTRA, UNCERTAIN
from perception.performance import PerformanceEvaluator, PerformanceResult
from perception.skill import SkillState, SkillStateTracker, Attempt


def _ev(note, uncertain=False, start=0.0, dur=0.15):
    return NoteEvent(
        note=note, midi=None, start=start, end=start + dur, duration=dur,
        confidence=0.9 if not uncertain else 0.3,
        attack_confidence=0.9, uncertain=uncertain, pitch_samples=[],
    )


def _comp(exp, played_events):
    return compare("ex1", exp, played_events)


# ---------- NOTE ACCURACY ----------
def test_note_accuracy_perfect():
    exp = ["E2"] * 10
    played = [_ev("E2", start=i * 0.1) for i in range(10)]
    c = _comp(exp, played)
    r = PerformanceEvaluator().evaluate(c)
    assert abs(r.note_accuracy - 1.0) < 1e-9
    assert r.counts[CORRECT] == 10


def test_note_accuracy_eight_of_ten():
    # 10 expected, 8 correct, 1 wrong, 1 missing
    exp = ["E2"] * 10
    played = [_ev("E2", start=i * 0.1) for i in range(8)] + [_ev("G2", start=0.8), _ev("A2", start=0.9)]
    c = _comp(exp, played)
    r = PerformanceEvaluator().evaluate(c)
    # 8 correct of 10 expected -> 0.8
    assert abs(r.note_accuracy - 0.8) < 1e-9
    assert r.counts[WRONG] >= 1 or r.counts[MISSING] >= 1


# ---------- UNCERTAINTY SEPARATE ----------
def test_uncertain_not_wrong():
    exp = ["E2"] * 10
    # 8 correct, 2 uncertain (flagged, not wrong)
    played = [_ev("E2", start=i * 0.1) for i in range(8)] + [
        _ev("E2", uncertain=True, start=0.8), _ev("E2", uncertain=True, start=0.9)
    ]
    c = _comp(exp, played)
    r = PerformanceEvaluator().evaluate(c)
    assert r.counts[UNCERTAIN] == 2
    assert r.counts[WRONG] == 0
    assert abs(r.uncertain_ratio - 0.2) < 1e-9
    assert "overall_score" not in r.to_dict()


# ---------- TIMING RAW MS ----------
def test_timing_exact_zero_error():
    exp = ["E2", "G2"]
    played = [_ev("E2", start=0.0), _ev("G2", start=0.75)]
    c = _comp(exp, played)
    r = PerformanceEvaluator().evaluate(c, target_bpm=80, subdivision="quarter")
    # expected times: 0.0, 0.75 -> exact -> 0 ms
    assert r.mean_timing_error_ms == 0.0
    assert len(r.timing_errors_ms) == 2


def test_timing_plus_minus_50ms():
    exp = ["E2", "G2"]
    # expected 0.0, 0.75; played +50ms, -50ms
    played = [_ev("E2", start=0.05), _ev("G2", start=0.70)]
    c = _comp(exp, played)
    r = PerformanceEvaluator().evaluate(c, target_bpm=80, subdivision="quarter")
    assert abs(r.timing_errors_ms[0] - 50.0) < 1e-6
    assert abs(r.timing_errors_ms[1] - 50.0) < 1e-6
    assert abs(r.mean_timing_error_ms - 50.0) < 1e-6


# ---------- BPM NOT AUTO-PENALIZED ----------
def test_bpm_reported_not_failed():
    exp = ["E2", "G2", "A2", "B2"]
    played = [_ev("E2", start=0.0), _ev("G2", start=0.75), _ev("A2", start=1.5), _ev("B2", start=2.25)]
    c = _comp(exp, played)
    # target 100, but played as if ~80 (spacing 0.75s = 80bpm quarter)
    r = PerformanceEvaluator().evaluate(c, target_bpm=100, subdivision="quarter", performed_bpm=80)
    assert r.target_bpm == 100
    assert r.performed_bpm == 80
    assert abs(r.tempo_ratio - 0.8) < 1e-9
    # No overall score that would "fail" the slower deliberate attempt.
    assert "overall_score" not in r.to_dict()
    assert "score" not in r.to_dict()


# ---------- STABILITY ROBUST TO OUTLIER ----------
def test_stability_median_not_max():
    # Attempts BPM: 100, 102, 98, 101 -> stable ~100, best 102
    tracker = SkillStateTracker("alt_pick")
    state = SkillState(skill="alt_pick")
    for bpm in [100, 102, 98, 101]:
        r = PerformanceResult(
            exercise_id="ex", note_accuracy=0.95, timing_accuracy=0.9,
            uncertain_ratio=0.0, target_bpm=100, performed_bpm=bpm,
            tempo_ratio=bpm / 100, mean_timing_error_ms=20.0, duration_seconds=5.0,
            counts={CORRECT: 10},
        )
        tracker.update(state, r, target_bpm=100)
    assert state.best_bpm == 102
    assert state.stable_bpm == 100.5 or state.stable_bpm == 100.0


def test_outlier_best_vs_stable():
    # 100,101,99,140 -> best 140, stable = median 100.5 (outlier excluded, NOT 140)
    tracker = SkillStateTracker("alt_pick")
    state = SkillState(skill="alt_pick")
    for bpm in [100, 101, 99, 140]:
        r = PerformanceResult(
            exercise_id="ex", note_accuracy=0.95, timing_accuracy=0.9,
            uncertain_ratio=0.0, target_bpm=100, performed_bpm=bpm,
            tempo_ratio=bpm / 100, mean_timing_error_ms=20.0, duration_seconds=5.0,
            counts={CORRECT: 10},
        )
        tracker.update(state, r, target_bpm=100)
    assert state.best_bpm == 140
    # median of [99,100,101,140] = 100.5; crucially NOT 140 (outlier)
    assert state.stable_bpm == 100.5
    assert state.stable_bpm < 110  # outlier must not redefine the student


# ---------- INSUFFICIENT DATA ----------
def test_insufficient_data_trend():
    tracker = SkillStateTracker("alt_pick")
    state = SkillState(skill="alt_pick")
    r = PerformanceResult(
        exercise_id="ex", note_accuracy=0.9, timing_accuracy=0.8,
        uncertain_ratio=0.0, target_bpm=100, performed_bpm=100,
        tempo_ratio=1.0, mean_timing_error_ms=20.0, duration_seconds=5.0,
        counts={CORRECT: 10},
    )
    tracker.update(state, r, target_bpm=100)
    assert state.trend == "insufficient_data"
    assert state.confidence < 1.0


# ---------- LEVEL FROM CRITERIA, NOT MEAN ----------
def test_level_from_criteria():
    tracker = SkillStateTracker("alt_pick")
    state = SkillState(skill="alt_pick")
    # 4 attempts at 0.93 note / 0.89 timing -> should reach level >= 2
    for _ in range(4):
        r = PerformanceResult(
            exercise_id="ex", note_accuracy=0.93, timing_accuracy=0.89,
            uncertain_ratio=0.0, target_bpm=100, performed_bpm=105,
            tempo_ratio=1.05, mean_timing_error_ms=20.0, duration_seconds=5.0,
            counts={CORRECT: 10},
        )
        tracker.update(state, r, target_bpm=100)
    assert state.level >= 2
    assert "note_accuracy" in state.level_reason  # explainable


def test_no_overall_score_in_result():
    c = _comp(["E2"], [_ev("E2")])
    r = PerformanceEvaluator().evaluate(c)
    d = r.to_dict()
    for banned in ("overall_score", "score", "grade"):
        assert banned not in d


# ---------- E2E: NoteEvents -> Alignment -> PerformanceResult ----------
def test_e2e_pipeline():
    exp = ["E2", "G2", "A2", "B2", "D3", "E3"]
    played = [
        _ev("E2", start=0.0, dur=0.2),
        _ev("G2", start=0.3, dur=0.2),
        _ev("A2", start=0.6, dur=0.2),
        _ev("A2", start=0.9, dur=0.2),  # wrong (should be B2)
        _ev("D3", start=1.2, dur=0.2),
        _ev("E3", start=1.5, dur=0.2),
    ]
    c = _comp(exp, played)
    r = PerformanceEvaluator().evaluate(c, target_bpm=80, subdivision="quarter", performed_bpm=80)
    assert r.counts[WRONG] == 1
    assert r.note_accuracy == 5 / 6
    assert "overall_score" not in r.to_dict()
    # timing errors present (raw ms preserved)
    assert len(r.timing_errors_ms) == 6
