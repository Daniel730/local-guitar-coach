"""Teacher latency/validity benchmark: same attempts, one row per Ollama model.

Usage: .venv\\Scripts\\python validation\\bench_teacher.py qwen2.5:7b llama3.1:8b
Runs the real TeacherService path (compare -> performance -> context -> LLM -> schema -> policy).
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.teacher_service import TeacherService
from perception.events import NoteEvent
from perception.notes import note_to_midi

EXERCISE = "scale_e_minor_001"   # E2 G2 A2 B2 D3 E3 at 100 BPM, quarter = 0.6 s
SCENARIOS = {
    "bom": (["E2", "G2", "A2", "B2", "D3", "E3"], 0.6),
    "notas erradas": (["E2", "F2", "A2", "C3", "D3", "E3"], 0.6),
    "lento": (["E2", "G2", "A2", "B2", "D3", "E3"], 1.0),
}
RUNS = 2


def notes(names, step):
    return [NoteEvent(note=n, midi=note_to_midi(n), start=i * step, end=i * step + step * 0.8,
                      duration=step * 0.8, confidence=0.95, attack_confidence=0.9)
            for i, n in enumerate(names)]


def bench(model):
    os.environ.pop("RIFF_OLLAMA_THINK", None)
    if model.startswith("gpt-oss"):
        os.environ["RIFF_OLLAMA_THINK"] = "low"
    svc = TeacherService(EXERCISE, ollama_model=model)
    svc.evaluate_and_decide(notes(*SCENARIOS["bom"]))   # warm-up: model load is not per-attempt latency
    times, sources, samples = [], [], []
    for name, (seq, step) in SCENARIOS.items():
        for _ in range(RUNS):
            t0 = time.perf_counter()
            d = svc.evaluate_and_decide(notes(seq, step))
            times.append(time.perf_counter() - t0)
            sources.append(d.source)
        samples.append(f"  [{name}] {d.action} {d.tempo} | {d.spoken_feedback}")
    ok = sources.count("llm")
    print(f"{model}: mediana {statistics.median(times):.1f}s  max {max(times):.1f}s  "
          f"llm {ok}/{len(sources)}  ({', '.join(sorted(set(sources)))})")
    print("\n".join(samples), flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")   # Windows console: feedback has pt-BR / unicode spaces
    for m in sys.argv[1:]:
        bench(m)
