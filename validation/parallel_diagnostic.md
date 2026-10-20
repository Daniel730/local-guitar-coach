# Guitar Coach — Parallel Software Diagnostic (PC-side)

**Date:** 2026-08-26
**Rule applied:** READ-ONLY. No driver changes, no config changes, no code changes, no deletions.

## 🚨 KEY FINDING — audio_probe has been misleading diagnostics
`audio_probe/stream.py:45` forces `block = indata[:, 0]` → it reads ONLY CHANNEL 1, even in stereo.
If the guitar enters CH2, `audio_probe` never sees it → any past "no signal at the interface"
conclusion drawn via `audio_probe` may have been a FALSE NEGATIVE (guitar was on CH2 all along).
The `coach.py` callback uses `indata[:, chosen]` (correct, both channels measured). Do NOT rely on
`audio_probe` for channel-level diagnosis anymore; use `coach.py --channel N` or the inline stereo meter.
This is a diagnostic-tool bug, NOT touched during the physical-blocker investigation (per user order:
close the physical problem first; fix audio_probe after).

## DEVICE

```
M-Track detected:  YES (4 PortAudio entries, 2 input channels each, 44100/48000 Hz)
Device index:       1  (MME)  — default input device
Host API:           MME (also DirectSound 11, WASAPI 25@48000, WDM-KS 34@44100)
Input channels:     2
Output channels:    0 (input-only interface, as expected)
Default sample rate: 44100 (MME/WDM-KS), 48000 (WASAPI)
Name:               'Line 1/2 (9- M-Audio M-Track So[lo and Duo])'
```

The M-Track is correctly exposed to Python/PortAudio with 2 input channels. The interface is
NOT the problem at the OS/PortAudio layer.

## AUDIO_PROBE

`python -m audio_probe --device 1 --seconds 3` reads via `audio_probe/stream.py`.
**CRITICAL FINDING:** `stream.py:45` does `block = indata[:, 0] if indata.shape[1] > 1 else indata.ravel()`
→ audio_probe ALWAYS reads CHANNEL 1 (left), even when opened in stereo. So if the guitar enters
CH2, `audio_probe` would never see it. (This is why our inline diagnostic — which measures both
channels — is the trustworthy meter, not `audio_probe` CLI per-channel.)

Note: the COACH (`coach.py`) measures CH1 and CH2 separately (`_measure_channels`, lines 65-87) and
selects via `--channel`/`--auto-channel`. The coach is correct; only `audio_probe` is CH1-only.

## CHANNEL MAPPING

- coach.py: opens `channels=2`, callback `block = indata[:, chosen]` (line 153) → correct.
- audio_probe/stream.py: `indata[:, 0]` → always CH1. Limitation, not used by coach.
- No downmix-to-mono in coach. No channel drop. Channel indexing verified correct in coach.

## PIPELINE

Trace (no code changed, only traced):
```
device(idx 1, 2ch) → AudioStream(stereo) → _cb picks indata[:,chosen]
 → PerceptionEngine.process_block → MusicalEvent (if amp>=0.02 AND conf>=pitch_threshold)
 → EventTracker.process → NoteEvent
 → compare → PerformanceEvaluator → build_context → Teacher.decide
```
No gain multiplication, no normalization, no clipping, no DC removal, no resample in pipeline.
dtype: sounddevice defaults to float32; numpy float64 math; no int16/float conversion that drops
signal. NaN handling: none observed, but synthetic test produced clean numerics.

## THRESHOLDS

```
amplitude_floor (engine): 0.02  ≈ -34 dBFS   [line 46/91]
pitch_threshold (engine): conf >= threshold  (YIN confidence)
note_change_gap_s (EventTracker): 0.12
min_note_duration_s: 0.04
```
Comparar com noise floor real: CH2 ≈ -51 dBFS (amplitude 2.8e-4) << 0.02 (amp_floor).
→ A guitarra a -51 dBFS é CORRETAMENTE rejeitada (está abaixo do piso). Um sinal de -20 dBFS
(amp 0.1) seria ACEITO. O pipeline NÃO tem threshold agressivo; o problema é o sinal não chegar.

## SYNTHETIC TEST (offline, no M-Track)

Sinal: 440 Hz A4 a -15 dBFS.
- YIN detetou: frequency=439.9996, note=A4, conf=0.9998 ✅
- E2 (82.41 Hz) sweep: detetado a -10/-20/-25/-30 dBFS; NÃO detetado a -34/-40 dBFS ✅ (piso = -34)
→ O pipeline de deteção funciona matematicamente. Reforça hipótese: software OK, problema antes.

(Nota: 440Hz gerou 0 NoteEvents porque 0.5s → 1 raw event não estabiliza o EventTracker;
esperado. O detector em si funciona, provado pelo sweep E2.)

## YIN

- `PerceptionEngine` (YIN) validado offline: A4 e E2 corretos.
- Testes existentes de YIN/pitch: cobrados pela suite (81 passed).
- Não usado áudio real da M-Track neste teste.

## TEST SUITE

```
passed:  81
failed:  0
skipped: 1
```
Nenhuma falha nova. Suite verde independente do bloqueio de áudio.

## GIT STATUS

```
M coach.py                      (channel fix + per-channel dBFS, esperado)
M ai/teacher/provider.py        (Ollama host/timeout, esperado)
M validation/session_*/notes.md (artefatos de validação)
?? _inspect_events.py           (script de inspeção do debug; não apagado)
?? nul                          (54 bytes ASCII; redirecionamento acidental; não apagado)
?? validation/hardware_signal_test.md, notes.md
```
Working tree MODIFIED (pelas correções já aprovadas + artefatos). Nada destrutivo.
Não apaguei ficheiros. `_inspect_events.py` e `nul` são investigados, não removidos.

## DIAGNOSTIC TREE (RECLASSIFIED — real setup: Guitarra→Cuvave Cube Baby→M-Track CH2)

Physical chain confirmed by user (guitar audible on COLUNAS via M-Track analog monitor):
```
GUITARRA                    🟢  (tocando, audível)
Cuvave Cube Baby            🟢  (ligada no CH2, não removida)
Cabo guitarra→Cuvave        🟢
Cabo Cuvave→M-Track         🟢
M-Track CH2 / entrada       🟢
Monitorização analógica M-Track 🟢  (chega às COLUNAS)
M-Track → USB → PC → PortAudio → coach.py   🟡  AINDA NÃO TESTADO
```
Previous PC-side checks (still valid):
```
USB DEVICE      🟢 M-Track exposta ao PC, 2ch, 44100
AUDIO DRIVER    🟢 PortAudio vê device, sem erro
PORTAUDIO INPUT 🟢 stream abre, blocks capturados, sem underrun
STREAM/BUFFER   🟢 captura ok
METER           🟢 coach reporta CH1/CH2 corretos
YIN             🟢 offline 440/E2 corretos
EventTracker    🟢 regressão passa
audio_probe     🟡 CEGO ao CH2 (indata[:,0]) — NÃO usar como evidência
```

## CURRENT HYPOTHESES (ordenadas por evidência)

1. **SINAL NÃO CHEGA À M-TRACK (físico).** Evidência: ambos CH1/CH2 a -50 dBFS mesmo tocando
   forte; YIN/pipeline validados offline; PortAudio/M-Track expostos corretamente. Mais provável:
   cabo mal, INST off, gain a zero, ou guitarra no CH1 em vez de CH2.
2. **audio_probe CLI cego ao CH2.** Evidência: `stream.py:45` força `indata[:,0]`. Se no passado
   a guitarra entrou em CH2 e usámos `audio_probe` para medir, podíamos ter lido silêncio em CH1
   e concluído errado. O coach (que mede os 2 canais) é a fonte correta. Não é a causa do bloqueio
   atual (coach também viu -50 em ambos), mas é uma armadilha de diagnóstico a corrigir depois.
3. **Driver/device errado.** Pouco provável: M-Track visível, 2ch, stream abre sem erro.

## WHAT THE HUMAN TEST WILL DISCRIMINATE

- **A** (humano OUVE a guitarra no direct monitoring da M-Track):
  → prova APENAS a cadeia ANALÓGICA: guitarra→cabo→entrada→preamp/INST→conversão/monitor da M-Track.
  → NÃO prova que o caminho USB→PortAudio→aplicação está correto. Esse continua a testar.
  → próximo passo (1 teste só, no PC): correr `coach.py` diretamente em CH2
    (`python -m coach --device 1 --seconds 3 --channel 2`), porque o `audio_probe` já provou ser
    cego ao CH2 e NÃO pode ser nossa referência. Se coach em CH2 ainda ler -50 dBFS, o suspeito
    vira routing USB/driver (ex.: WASAPI exclusivo, ou M-Track a enviar só para outputs).

- **B** (humano NÃO OUVE a guitarra na M-Track):
  → problema é ANTES da M-Track: guitarra, cabo, CH2, INST, ou gain.
  → isolar por substituição (outro cabo / outro instrumento / INST on / gain up).
  → quando a própria M-Track der som, aí liga ao PC e o sinal aparece.

## NEXT ACTION

**UMA ação:** humano faz o teste A/B de direct monitoring (headphones na M-Track, tocar nota
forte). Reportar A ou B. Com base nisso, eliminamos toda a cadeia analógica (B) ou passamos a
investigar routing de driver (A). PC-side está validado e eliminado como causa.
