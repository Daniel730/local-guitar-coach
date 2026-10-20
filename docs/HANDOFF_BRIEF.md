# HANDOFF BRIEF — Local Guitar Coach (Riff)

**Entregue a este agente no início da sessão. Este é o pacote de entrada.**

> **CHANGE-02 (2026-09-03):** arquitetura de captura é **SERVER-SIDE**
> (sounddevice no backend), browser é **consumer** de telemetria. A antiga
> `browser → AudioWorklet → WS PCM` é **HISTÓRICA/SUBSTITUÍDA**. NÃO
> reimplementar. NÃO "corrigir" a arquitetura seguindo doc obsoleto.

---

## 1. Você está entrando num projeto MID-HANDOFF. Não interprete nada como "pronto".

Algumas coisas já parecem estar "no lugar": tem 81 testes passando, tem um
README, tem pastas por toda parte. **Isso NÃO significa que o trabalho está
feito.** Você chegou para executar um gate, não para "melhorar coisas".

**Duas regras de ouro, antes de qualquer código:**

1. **`docs/PROJECT_STATE.md` é o CONTRATO OPERACIONAL.** O README NÃO é
   autorização para implementar. Leia `docs/PROJECT_STATE.md` **integralmente**
   antes de tocar qualquer arquivo, e **confirme o estado real no disco**
   (o que existe, o que roda, quais testes passam) — não confie na narrativa
   de nenhum doc sozinho, incluindo este.
2. **MVP-6 NÃO está DONE.** Não avance para MVP-7 nem altere `perception/`
   até TODAS as evidências do §4 de `PROJECT_STATE.md` estarem satisfeitas.

## 2. ARQUITETURA REAL (leia a partir do CÓDIGO, não de narrativa)

```
Guitarra (Cuvave → M-Track CH2)
   ↓
sounddevice — app/services/audio_service.py (backend)   ← CAPTURA AQUI
   ↓  block 1024, canal escolhido por dBFS
Perception — perception/engine.py → events.py (EventTracker)
   ↓  MusicalEvent → NoteEvent
app/services/session_service.py — callbacks (pitch, note_event, meter)
   ↓  register_emitter → call_soon_threadsafe
app/api/websocket.py — WebSocket JSON
   ↓
Browser UI (frontend/app.js) — CONSUMER → plota telemetria no fretboard/UI
```

- **O browser NÃO captura áudio.** Captura é server-side (Python + sounddevice).
- **O browser NÃO envia PCM via WebSocket.** Ele recebe JSON de telemetria.
- Se algum pedaço do projeto te "pedir" para provar `browser → AudioWorklet →
  WS PCM`, é a arquitetura antiga — está marcada HISTÓRICA. Não persiga.

## 3. O que você DEVE fazer agora

Fechar o **gate do MVP-6** na ordem definida em `PROJECT_STATE.md §4`
(arquitetura server-side):

1. Backend de captura responde a `start_session` e emite telemetria
   (provar com fonte sintética interna à pipeline, ex. bloco A4 440 Hz);
2. pitch / meter / eventos chegando ao frontend via WS;
3. TeacherAction chegando ao frontend com `source` (`ollama` ou `fallback`);
4. fallback com Ollama morto (sessão NÃO derruba);
5. teste humano com guitarra (Cuvave → CH2 do M-Track);
6. `pytest` ≥ 81 passando;
7. smoke test final documentado.

Cada critério exige **evidência reproduzível** (output real capturado), não
inferência. Não declare DONE por aproximação.

## 4. O que você NÃO pode tocar

- **`perception/` — PROIBIDO durante o MVP-6**, salvo o raro caso do
  `PROJECT_STATE.md §5` (exigência comprovada + proposta por escrito + testes
  antes do código). O frontend/Web App se ADAPTA ao núcleo validado, nunca o
  contrário. Não "refatore" o YIN nem mexa em `pitch_threshold`.
- **Ollama é a ÚNICA fonte de LLM.** Proibido plugar OpenRouter ou qualquer
  infra do Hermes/orquestrador DENTRO deste projeto.
- **Não puxe features novas** (bends, vibrato, acordes, corda, palm mute,
  scoring, músicas) antes do gate. MVP-7 (UX/pedagogia) só depois.
- **Não hardcode device/channel** (M-Track muda de índice por backend:
  MME=1, WASAPI=25, WDM-KS=34; channel 0-based: `--channel 1` = CH2/Instrument).
  ⚠️ Nota: o frontend atual AINDA envia `device:1/channel:1` fixo — isso é um
  **P1 conhecido** (§7), não para "consertar" no gate, mas para registrar.

## 5. Armadilhas que já custaram sessões (resumo — detalhes em PROJECT_STATE.md §8)

- **Captura server-side:** se a UI não mostra nada, verifique se o backend
  está capturando (logs de `AudioService`) — NÃO assuma que o browser precisa
  "enviar áudio".
- **Telemetria via thread pool** → postar no event loop com
  `loop.call_soon_threadsafe(lambda: asyncio.create_task(send(...)))`. Nunca
  `send_text`/`create_task` direto de worker thread.
- **FastAPI mount:** servir frontend via `FileResponse` na `/` + rotas `/api/` +
  WS `/ws`. **NÃO usar `StaticFiles` mount** para a UI (engole o frontend).
- **Prove o path backend com fonte sintética ANTES de pedir humano pra tocar**
  — "wiring quebrado" vs "sem sinal real" são idênticos na UI. Na arquitetura
  server-side, a fonte sintética é injetada na pipeline interna, não via WS.
- **Nunca capturar áudio live por conta própria.** O modo live (`python -m
  perception --device N --seconds 10`) REQUER um humano tocando guitarra; você
  fornece o comando e interpreta o JSON, não roda a captura.
- **Testes sintéticos:** alimentar o engine real com blocos do TAMANHO do
  hardware (1024 @ 44100). Nunca um bloco gigante (janela deslizante colapsa
  pra um evento, tracker não vê duração).

## 6. Baseline factual (verificado em disco na data deste brief)

- Repo: `C:\Users\Danie\local-guitar-coach` (Windows, `.venv` presente).
- MVP-0..MVP-5 DONE com áudio real de guitarra; **MVP-6 ABERTO**.
- `pytest`: **81 passed, 1 skipped** (executado ao vivo; kernel Python do `.venv`).
- `node --check` frontend/app.js e neck.js: **OK** (verificado no CHANGE-02).
- Self-test sintético (`python -m perception --self-test`): roda.
- Contrato canônico: `docs/PROJECT_STATE.md`. Briefing: este arquivo.
- Backlog conhecido: `docs/PROJECT_STATE.md §10` e `docs/LOOSE_ENDS.md`.

## 7. Backlog conhecido (P1/P2) — problemas reais e DELIBERADAMENTE não resolvidos

> Estes NÃO são "não descobertos". São conhecidos e deixados de propósito como
> trabalho futuro. Não resolvê-los como melhoria oportunista; virarão CHANGEs.

- **P1-A — frontend hardcoda device/channel.** `frontend/app.js` envia
  `device: 1`/`channel: 1` em vez de consumir `/api/devices`.
- **P1-B — persistência do Web App desconectada.** `save_performance`/
  `save_skill_state` existem mas o Web App nunca os chama → `/api/progress`
  fica vazio para sessões do Web App (só a CLI grava).
- **P2-A — `cents` nunca emitido.** Medidor de afinação na UI é inerte.
- **P2-B — dupla semântica de meter** (CH1/CH2 no início vs mono no runtime).
- **P2-C — tempo/BPM duplicado em 3 fontes** (`coach.py`, `models/session.py`,
  `teacher_service.py`).
- **P2-D — `audio_probe/stream.py` força CH1.** ADIADO de propósito (bloqueado
  por condição física; owner-order: resolver o problema físico primeiro).

## 8. Quando terminar, reporte neste formato

Para cada item do §4: **PASS/FAIL** + a evidência (trecho de output, JSON,
captura). Liste explicitamente o que ficou bloqueado e o que precisa de
decisão do dono (Dan). Não marque MVP-6 = DONE até TODOS os itens passarem.
Não resolva itens do backlog (§7) nesta tarefa — documente-os se forem
relevantes.