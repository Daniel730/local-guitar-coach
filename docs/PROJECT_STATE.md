# Local Guitar Coach (Riff) — PROJECT STATE & ACCEPTANCE CONTRACT

**Status:** CANÔNICO. Este documento é o *contrato*. Qualquer agente/IA que
tocar este repo deve ler isto primeiro e aceitar seus critérios de aceitação
como a única definição de "pronto". Se conflitar com outros docs, este vence.

**Validado em campo (data de escrita):** MVP-0..MVP-5 DONE com áudio real de
guitarra. Suíte de testes: **81 passed, 1 skipped** (verificado ao vivo).

> **CHANGE-02 (2026-09-03):** arquitetura de captura de áudio do Web App (MVP-6)
> alinhada ao contrato. O código implementa **captura SERVER-SIDE** (sounddevice
> no backend); o browser é um **consumer de telemetria**, não produtor de áudio.
> A arquitetura antiga `browser → AudioWorklet → WS PCM` é **HISTÓRICA /
> SUBSTITUÍDA** e NÃO deve ser reimplantada.

---

## 1. Para que serve e stack

Tutor de guitarra **local e adaptativo**, sem nuvem no MVP. Stack:
Python + `sounddevice`/PortAudio + NumPy + FastAPI + SQLite + **Ollama**.

- **Ollama é a ÚNICA fonte de LLM.** Proibido plugar OpenRouter, o
  orquestrador Hermes ou qualquer infra de Hermes DENTRO deste projeto.
  `OllamaProvider` fala só com `localhost:11434`.
- Hardware alvo: **M-Audio M-Track Duo (USB)** no Windows.
- Cadeia de sinal: guitarra → pedal **Cuvave Cube Baby** → **CH2** do M-Track
  (Hi-Z/Instrument). Diagnóstico DEVE considerar o Cuvave na cadeia — nunca
  assumir guitarra plugada direto.

## 2. Estado atual (set/2026)

| MVP | Descrição | Estado |
|---|---|---|
| MVP-0 | Audio Probe (`audio_probe/`) | ✅ DONE |
| MVP-1 | YIN pitch detection (`perception/pitch.py`) | ✅ DONE (validado c/ guitarra) |
| MVP-2 | EventTracker → NoteEvent (`perception/events.py`) | ✅ DONE |
| MVP-3 | SequenceMatcher / alignment (`perception/sequence.py`) | ✅ DONE |
| MVP-4 | PerformanceEvaluator, 4 dims sem score (`perception/performance.py`, `skill.py`) | ✅ DONE |
| MVP-5 | Teacher brain: Ollama + Schema + Policy (`ai/teacher/*`) | ✅ DONE (portão full validation v2 PASS) |
| **MVP-6** | **Web App (FastAPI + WebSocket + frontend vanilla)** | 🟡 **passos 1-4, 6 PASS (2026-10-20); falta 5 (guitarra real) e 7** |
| MVP-7 v1 | Loop por tentativas, currículo, músicas, voz, launcher (ver §11) | 🟡 implementado; aguarda teste humano |

Núcleo de percepção (MVP-0..MVP-5) está **FROZEN**: validado, não mexer.

## 3. Arquitetura (núcleo determinístico → professor probabilístico)

### 3.1 Pipeline de percepção (invariável, MVP-0..MVP-5)

```
Áudio (MVP-0) → YIN pitch (MVP-1) → Raw Pitch Events ─┐
                                                       ├→ EventTracker (MVP-2) → NoteEvent[]
Onset (separado) ──────────────────────────────────────┘
NoteEvents → SequenceMatcher (MVP-3) → Alignment (correct/wrong/missing/extra/uncertain)
Alignment → PerformanceEvaluator (MVP-4) → PerformanceResult (4 dims INDEPENDENTES, SEM score)
PerformanceResult + SkillState → TeacherContext → Ollama → Schema → Policy → TeacherAction
```

### 3.2 Arquitetura do Web App (MVP-6) — CAPTURA SERVER-SIDE [CURRENT]

```
Guitarra (Cuvave → M-Track CH2)
        ↓
sounddevice — app/services/audio_service.py (AudioService, backend)
        ↓  block 1024, canal escolhido por medida de dBFS
Perception — perception/engine.py → perception/events.py (EventTracker)
        ↓  MusicalEvent → NoteEvent
app/services/session_service.py — Telemetry callbacks (pitch, note_event, meter)
        ↓  register_emitter → call_soon_threadsafe
app/api/websocket.py — WebSocket JSON
        ↓
Browser UI (frontend/app.js + neck.js) — CONSUMER de telemetria
        ↓  renderiza note/fretboard/live/teacher/session/meters
```

**O browser NÃO captura áudio.** A captura vive no backend (Python +
sounddevice), e o browser apenas **plota a telemetria** que recebe via
WebSocket. Isso é uma decisão do dono (Dan): "A UI é somente para plotar
dados"; captura no browser foi REMOVIDA de propósito.

> **[HISTÓRICO / SUBSTITUÍDO]** A arquitetura `Browser mic → AudioWorklet →
> PCM WebSocket → Backend` foi implementada e depois **revertida** para captura
> server-side. `frontend/app.js` descreve a versão atual como "server-side
> capture"; `app/api/websocket.py` ignora frames binários. NÃO reintroduzir o
> caminho browser→PCM no estado atual. Ele só voltaria se o dono decidir.

### Layout do repo (verificado)
```
perception/       # engine, pitch(YIN), notes, onset, events(EventTracker),
                  # sequence(matcher), performance(4 dims), skill(SkillState), persistence(JSON)
ai/               # teacher/ (context, provider, validator, policy, teacher, build_context)
                  # prompts/ (conversation, teacher_decision, teacher_system)
                  # schemas/teacher_action.json
app/              # Web App MVP-6: main.py, api/(routes,websocket),
                  # models/session, services/(audio, session, teacher)
frontend/         # vanilla HTML/CSS/JS: app.js, index.html, neck.js, style.css (sem React/Vite)
audio_probe/      # MVP-0: devices, stream, meters, waveform, probe, cli, config
exercises/        # scale_e_minor_001.json (+ exercise.py loader)
tests/            # unit + integration + hardware smoke (gated) + regressions
validation/       # session_001..006, notes.md, hardware_signal_test, parallel_diagnostic
docs/             # este contrato, HANDOFF_BRIEF.md, LOOSE_ENDS.md
coach.py          # harness de validação full-stack MVP-0..MVP-5 (NÃO é o shell de produção)
data/sessions/    # persistência JSON de sessões (SQLite rejeitado por decisão até aqui)
```

## 4. ⛔ GATE DO MVP-6 — critérios de aceitação objetivos (arquitetura server-side)

**MVP-6 = DONE SOMENTE se TODAS as caixas abaixo estiverem marcadas com
evidência (output real capturado, não inferência).** Não basta "funciona" —
cada critério exige prova reproduzível.

**MVP-6 valida o LOOP DE RUNTIME completo usando captura SERVER-SIDE:**
após `start_session`, o backend captura áudio do dispositivo configurado,
processa pela pipeline de percepção, produz pitch/note/event telemetry, e
entrega o estado ao browser via WebSocket. O browser renderiza a telemetria.

### A. Ciclo de vida da sessão
- [ ] `start_session` → `session_state: running` (com exercise, target_bpm corretos)
- [ ] `stop_session` → sessão limpa (estado `stopped`, recursos liberados)
- [ ] Estados (running/stopped/error) coerentes
- [ ] NENHUMA captura de áudio no browser é exigida

### B. Áudio server-side
- [ ] Backend inicia/mantém captura server-side do dispositivo configurado
      (sounddevice → `AudioService`)
- [ ] Áudio chega à pipeline de percepção (PerceptionEngine)
- [ ] **NÃO** exige AudioWorklet; **NÃO** exige browser enviar PCM

### C. Percepção
- [ ] Detecção de pitch funciona (self-test sintético cobre)
- [ ] NoteEvents são gerados (EventTracker) — comportamento intacto
- [ ] Self-test sintético (`python -m perception --self-test`) válido

### D. Telemetria via WebSocket (browser recebe)
- [ ] Mensagens esperadas pela UI, nas famílias existentes (não inventar):
      `pitch`, `note_event`, `meter`, `meter_message`/`channels_dbfs`,
      `teacher`, `session_state`, `error`
- [ ] `pitch` (note/frequency/confidence/onset) chega ao frontend
- [ ] `note_event` chega ao frontend
- [ ] `teacher` chega (action, tempo, reason, spoken, source)

### E. Renderização no browser (como CONSUMER)
- [ ] Nota atual/target atualizada
- [ ] Fretboard (neck.js) atualiza com as notas
- [ ] Live input (pitch/meter) atualiza
- [ ] Teacher feedback apresentado
- [ ] Estado da sessão apresentado

### Backend / API de suporte
- [ ] `GET /api/health` = `200` `{"status":"ok"}`
- [ ] `GET /api/exercises` = lista válida (target_notes, difficulty, target_bpm)
- [ ] `GET /api/devices` = lista válida (index, name, channels, sample_rate)

### Professor (TeacherAction)
- [ ] TeacherAction válido chega ao frontend (action, tempo, reason, spoken, source)
- [ ] `source=ollama` quando Ollama responde (Ollama REAL confirmado)
- [ ] `source=fallback` quando Ollama está indisponível
- [ ] Ollama indisponível **NÃO derruba a sessão** (fallback determinístico REPEAT)

### Higiene / regressão
- [ ] **81+ testes passam** (`pytest`) — incl. regressão do crash de state machine
- [ ] Smoke test final documentado (`docs/MANUAL_TEST.md` atualizado + session record)

> **Critérios EXPLICITAMENTE FORA do escopo do MVP-6 (não exigir):**
> browser capturar PCM; AudioWorklet; browser escolher dispositivo; browser
> transmitir áudio bruto. O gate deve ficar **mais preciso**, nunca mais fácil.

> **Ordem de execução obrigatória (prova a menor dependência antes da maior):**
> 1. Backend de captura server-side responde a `start_session` e emite
>    telemetria (provar com fonte sintética interna à pipeline, ex. bloco A4);
> 2. pitch/meter/eventos chegam ao frontend via WS;
> 3. TeacherAction chega com `source`;
> 4. fallback com Ollama morto;
> 5. teste humano com guitarra (Cuvave → CH2);
> 6. 81+ testes verdes;
> 7. smoke test final documentado.
>
> Só então MVP-6 = DONE. **NÃO pular ordem; não declarar DONE por aproximação.**

## 5. ⚠️ REGRA DE SUSPEIÇÃO — percepção durante MVP-6

**Qualquer alteração em `perception/` durante o MVP-6 é TRATADA COMO SUSPEITA.**

O frontend e o Web App DEVEM adaptar-se ao núcleo já validado (MVP-0..MVP-5),
não o contrário. Mudanças no núcleo de percepção só são aceitas se:

1. Comprovadamente necessárias (bug que bloqueia o caminho do MVP-6, não
   "melhoria" nem refactor oportunista);
2. Propostas por escrito, com justificativa + impacto, ANTES de tocar código;
3. Acompanhadas de testes que reproduzam o comportamento novo;
4. Sem desfazer YIN/pitch_threshold já congelados.

Se uma mudança em `perception/` não atender a isso: bloquear, não integrar.

## 6. Roadmap (depois do gate MVP-6)

**MVP-7 — UX / pedagogia.** Começa por UX/pedagogia (clareza do feedback,
ajuste do nível, curvas de exercícios), NÃO por features novas de técnica.

**Adiado — não agendar antes do gate:** bends, vibrato, reconhecimento de
acordes, identificação de corda, palm mute, scoring/performance model.
**Músicas: AGENDADAS pelo dono em 2026-10-20** (melodias de domínio público, nota única; ver §11).

## 7. Regras de engenharia do dono (Dan — vinculantes) [CAPITAL GATE]

1. **Interpretação sobre o detector — nunca corrigir o YIN.** Artefatos de
   ataque (harmônicos, 96/98 Hz num ataque de D#) são colapsados pelo
   EventTracker, não pelo YIN.
2. **Detector validado = não mexer.** "Não mexa no YIN", "deixa o
   pitch_threshold quieto".
3. **Plug-and-play.** Guitarra esperada FORA DE TOM. Não persistir afinação,
   não pedir pra afinar antes de praticar. O tutor identifica e comenta a
   afinação — não exige.
4. **Sem features prematuras** (bends, vibrato, acordes, corda, palm mute,
   scoring, músicas) até agendadas. Adicionar cedo = caminho rejeitado.
5. **Cada MVP = entrega real**: implementação + unit + integração + erro +
   docs + smoke manual. Não dar "done" em mock se o hardware está acessível.
6. **MVP-4 mantém dimensões SEPARADAS. Nunca um overall_score.** per
   note_accuracy, timing_accuracy (erro ms bruto), performed_bpm vs
   target_bpm (sem penalizar), consistency (mediana, robusta a outlier).
   SkillState.level vem de critérios pedagógicos explícitos, não de média.
   Tocar perfeito a 70 BPM NÃO é erro.
7. **O Teacher recomenda; o sistema decide.** LLM → Schema (contrato fechado
   TeacherAction) → Policy (determinística) → executa. Falha de AI
   (offline/JSON inválido/ação inválida/BPM) NUNCA derruba a sessão: fallback
   determinístico (REPEAT em stable_bpm). Campo `source` em toda decisão
   (ollama/fallback) — LLM e fallback ficam indistinguíveis-por-acidente.
   `FakeLLMProvider` dirige todos os testes de segurança sem Ollama.
8. **Ollama = único LLM. Riff = projeto INDEPENDENTE.** Vide §1.

> O CAPITAL GATE (§7) é FROZEN. CHANGE-02 redefiniu apenas o **critério de
> aceitação do MVP-6 (§4)** para refletir a arquitetura real — não tocou nestas
> regras de engenharia.

## 8. Notas técnicas críticas (MVP-6 / Web App)

- **Servir frontend:** FastAPI serve `index.html` na `/` (FileResponse) +
  rotas `/api/` + WS `/ws`. Ordem de mount importa. **NÃO usar `StaticFiles`
  mount** para a UI (faz `/api/` engolir o frontend).
- **Captura server-side:** `app/services/audio_service.py` abre o dispositivo
  (stereo), seleciona o canal no callback (`indata[:, chosen]`), aplica ganho
  digital e alimenta PerceptionEngine + EventTracker. `measure_channels`
  reporta dBFS por canal antes da captura (como `coach.py`).
- **Threading da telemetria:** callbacks de áudio rodam em thread pool
  (`loop.run_in_executor`). NÃO chamar `send_text`/`create_task` direto de
  worker thread. Postar com `loop.call_soon_threadsafe(lambda:
  asyncio.create_task(send(...)))` no emitter por sessão
  (`SessionService.register_emitter(session_id, emit)`).
- **Provar o path backend com fonte sintética ANTES de pedir humano pra tocar**
  — isola "wiring quebrado" de "sem sinal real", que parecem idênticos na UI.
  Com captura server-side, a fonte sintética é injetada na pipeline (bloco A4
  440 Hz), não enviada pelo browser.
- **Browser é consumer:** `frontend/app.js` faz WS → recebe telemetria → plota.
  Não há `AudioWorklet`/`getUserMedia`/envio de áudio no frontend.

## 9. Como rodar / validar

```bash
# testes (sem hardware)
./.venv/Scripts/python.exe -m pytest           # 81 passed, 1 skipped

# self-test sintético (prova o engine de percepção, sem device)
./.venv/Scripts/python.exe -m perception --self-test

# live (REQUER humano + guitarra; agente NÃO captura por conta própria)
python -m perception --device N --seconds 10 [--track]
python -m audio_probe --list                   # descobrir índice do device

# Web App MVP-6
# usar .venv; GET /api/health, /api/exercises, /api/devices; WS /ws
```

- **Testes NÃO hardcodam índices de device** (M-Track muda: MME=1, WASAPI=25,
  WDM-KS=34). Usar listas de device mock.
- Channel 0-based: `--channel 0`=CH1, `--channel 1`=CH2 (Instrument/Hi-Z).
  Sempre printar report dBFS por canal antes da captura.

## 10. Backlog conhecido (P1/P2) — estado atualizado [CURRENT backlog]

> **Atualizado 2026-09-03 (CHANGE-03..06):** os itens P1-A, P1-B, P2-A, P2-B,
> P2-C foram RESOLVIDOS e fechados. O único item ainda aberto é P2-D (USB
> routing), que está **READY / aguardando guitarra + M-Track** para validação
> física. Não reabrir itens já fechados sem evidência.

### ✅ RESOLVIDO — CHANGE-03 (P1-A + P1-B)
- **P1-A** — frontend consome `/api/devices`; `device`/`channel` derivados do device (não hardcoded). `frontend/app.js` usa `selectedDevice`/`selectedChannel`.
- **P1-B** — Web App persiste performance + skill state via `persist_session` → `/api/progress` tem dados reais.

### ✅ RESOLVIDO — CHANGE-04 (P2-A + P2-B)
- **P2-A** — `cents` emitido no pitch telemetry (tuner funcional).
- **P2-B** — semântica de meter documentada (channels_dbfs setup vs meter runtime).

### ✅ RESOLVIDO — CHANGE-05 (P2-C)
- **P2-C** — tempo/BPM é propriedade do exercício (JSON), single source of truth. Removidos `EXERCISE_TEMPO`/`_get_tempo`/`get_exercise_tempo`.

### ✅ RESOLVIDO — CHANGE-06 (Exercise Schema v2 + Skills/Subskills)
- Schema v2: description, subskill, technique, objective, prerequisites, evaluation, success/failure_criteria, common_mistakes, hints, progression (contrato de conteúdo, sem engine).
- `exercises/skills.py`: entidades Skill/Subskill + catálogo + validação.

### ⏸️ P2-D — `audio_probe/stream.py` força CH1 + sinal USB — READY / AGUARDANDO HARDWARE
- `audio_probe/stream.py` força `indata[:,0]` (CH1) mesmo aberto em stereo → nunca lê CH2.
- Problema físico: guitarra audível nas colunas da M-Track (cadeia analógica OK) mas PC vê ~-55 dBFS em ambos canais → sinal não atravessa o USB em amplitude útil.
- **CHANGE-07** = investigar empiricamente onde o sinal desaparece (guitarra → M-Track → USB → Windows device → sounddevice → stream → CH1/CH2 → RMS/peak → pitch → NoteEvent).
- **NÃO tocar até guitarra + M-Track disponíveis para validação física.** Não é um simples edit de `stream.py`.


> Backlog mantido em `docs/LOOSE_ENDS.md` (auditoria + CHANGE tickets).
> **P1-A, P1-B, P2-A, P2-B, P2-C foram implementados (CHANGE-03..06).**
> O único item aberto é P2-D (CHANGE-07), aguardando hardware. Reabrir um item
> fechado = CHANGE separado, com protocolo CHANGE do dono (diagnóstico → proposta → GO).

## 11. v1 utilizável (2026-10-20, branch `feat/v1-usable`)

Decisões do dono: escopo v1 = loop de prática completo + músicas; delegação de desenvolvimento
ao LiteLLM permitida (o runtime continua só-Ollama).

| Item | Onde | Evidência |
|---|---|---|
| Gate 1-2: fonte sintética → percepção → WS (pitch/meter/note_event) | `tests/test_e2e_synthetic.py` | PASS (pytest) |
| Gate 3: TeacherAction `source=llm` com Ollama real | gpt-oss:20b, think=low, 8,2 s, feedback pt-BR citando 83,3%/33,3% | PASS (manual) |
| Gate 4: Ollama indisponível → fallback, sessão viva | `test_e2e_synthetic.py`, `test_attempts.py` | PASS |
| Gate 6: suíte | `pytest` | **174 passed, 1 skipped** |
| Uma decisão do professor por tentativa (não mais a cada 3 s) | `app/services/teacher_service.py`, `websocket.py` | `tests/test_attempts.py` |
| Nota final de tentativa fechava só na próxima nota | `AudioService._track_silence` (app, não perception) | e2e |
| `ollama` faltava no `.venv`/requirements → web app sempre em fallback | `requirements.txt` | corrigido |
| Fallback com exercício inexistente e 90 BPM fixo | `TeacherService` | corrigido |
| Currículo determinístico + `GET /api/next` | `exercises/curriculum.py` | `tests/test_curriculum.py` |
| 12 exercícios + 5 músicas (frases + completa) | `exercises/*.json` | `tests/test_exercise_library.py` |
| Músicas: notas repetidas colapsadas (`rules.collapse_repeats`) porque o EventTracker funde re-ataque da mesma nota | `Exercise.expected_sequence` | teste |
| Voz (speechSynthesis pt-BR), metrônomo, contagem 3-2-1, banner de progressão | `frontend/` | `node --check` + preview |
| Launcher | `start.bat` / `start.ps1` | preview |

**Pendente (precisa do Dan + guitarra):** gate 5 (tocar `scale_e_minor_001` e uma frase de música
via CH2) e gate 7 (registrar em `validation/session_007/`). Roteiro em `docs/MANUAL_TEST.md` §v1.

---

*Contrato canônico. Atualizar por decisão explícita do dono, não por
interpretação de agente.*
