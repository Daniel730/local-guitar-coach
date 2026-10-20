# PENTE-FINO / AUDITORIA — Pontas Soltas do Projeto
**Data:** 2026-09-03. **Autor:** agent (Neo). **Método:** leitura de código
fonte + execução de self-tests + `pytest` no estado atual do disco.

> **CHANGE-02 (2026-09-03):** a CONTRAÇÃO CRÍTICA (#1) foi RESOLVIDA no
> contrato — `docs/PROJECT_STATE.md` e `HANDOFF_BRIEF.md` foram reescritos
> para a arquitetura **server-side** e o gate MVP-6 redefinido. Este arquivo
> agora é o registro da auditoria + backlog. Nada de runtime foi alterado.

---

## O que foi RESOLVIDO no CHANGE-02 (contrato, não código)

### R1 — Contração browser→PCM (era P0)
- **Antes:** `PROJECT_STATE.md §4`/`HANDOFF_BRIEF` exigiam provar
  `browser → AudioWorklet → WS PCM`, mas o código é **server-side**
  (`audio_service.py` header, `websocket.py` linha ~41, `app.js` header).
- **Depois:** contrato reescrito para captura server-side; gate redefinido;
  o caminho antigo marcado **HISTÓRICO/SUBSTITUÍDO**. §3.2 descreve a
  arquitetura real e §4 o gate. Browser é consumer de telemetria.
- **Código:** nenhuma alteração.

### R2 — Contração `cents` nunca emitido (era P2)
- Confirmado no código: `cents` existe no modelo, `_make_pitch_callback` não o
  emite. Mantido como **P2-A** no backlog (§10 do contrato). NÃO corrigido.

### R3 — Persistência Web App desconectada (era P1)
- Confirmado: `save_performance`/`save_skill_state` não são chamados no Web App.
  Mantido como **P1-B** no backlog. NÃO corrigido.

---

## Backlog corrente (NÃO resolvido, NÃO tocado) — [CURRENT backlog]

> Ver artefato completo em `docs/PROJECT_STATE.md §10`. Cada item vira um
> CHANGE separado com protocolo do dono.

| # | Classificação | Código | O que é | Local |
|---|---|---|---|---|
| P1-A | Hardcode | Frontend manda `device:1`/`channel:1` fixo, não consome `/api/devices` | `frontend/app.js:~364-365` |
| P1-B | Persistência | Web App nunca chama `save_performance`/`save_skill_state` → `/api/progress` vazio p/ Web App | `app/services/*`, `perception/persistence.py` |
| P2-A | `cents` | Campo existe, callback não emite → medidor de afinação inerte | `app/models/session.py`, `app/services/session_service.py` |
| P2-B | Meter | `channels_dbfs` (CH1/CH2) vs `meter` (mono rms/peak) — dupla semântica | `app/api/websocket.py`, `app/services/session_service.py` |
| P2-C | Duplicação | `EXERCISE_TEMPO`+`_estimate_bpm` em 3 fontes | `coach.py`, `app/models/session.py`, `app/services/teacher_service.py` |
| P2-D | CH1 | `audio_probe/stream.py` força `indata[:,0]` (CH1) | **ADIADO de propósito (condição física; owner-order: não tocar)** |

---

## Achados adicionais do audit CHANGE-02 (com evidência)

### A1 — `validation/README.md` afirma "72 passed" (obsoleto)
- **Evidência:** `validation/README.md:10` — `python -m pytest -q  # must be 72 passed`.
- **Realidade:** pytest atual = **81 passed, 1 skipped**.
- **Classificação:** P3 — doc interno defasado. Baixo impacto (validação, não
  prod), mas pode confundir. Ficou anotado; não editado (documental, low-risk →
  pode ser corrigido num CHANGE documental, mas não bloqueia nada).

### A2 — README.md ainda tem resquício de narrativa browser→percepção
- **Evidência:** `README.md:16` — "MVP-6 verifies the full browser→perception→
  teacher→telemetry path".
- Isso descreve o fluxo *visual* (browser recebe e mostra), não captura de áudio
  no browser — mas a notação "browser→perception" é ambígua e pode ser lida
  como "browser alimenta a percepção".
- **Classificação:** P3 — ambiguidade documental. Recomenda-se reescrever para
  "server-side capture → perception → teacher → telemetry → browser" no README
  também. NÃO tocado aqui para não expandir escopo; registrar como TODO de doc.

### A3 — `docs/` tinha referência a `ARCHITECTURE.md` inexistente (já resolvido antes)
- `README.md` apontava para `docs/ARCHITECTURE.md` que não existe; corrigido em
  data anterior para `docs/PROJECT_STATE.md`. Registro p/ rastro.

### A4 — Consistência de arquitetura confirmada no código (bom sinal)
- Nenhuma ocorrência de `getUserMedia`/`AudioWorklet`/`AudioContext`/captura em
  `frontend/` → o frontend é genuinamente consumer. ✅

---

## Validação executada no CHANGE-02 (estado real)

| Check | Resultado | Evidência |
|---|---|---|
| `node --check frontend/app.js` | PASS | `app.js OK` |
| `node --check frontend/neck.js` | PASS | `neck.js OK` |
| `pytest` | PASS | `81 passed, 1 skipped` |
| Self-test sintético | PASS | `python -m perception --self-test` produziu eventos A2/A4/coerentes |
| Runtime code alterado | NÃO | apenas `docs/` |
| CAPITAL GATE (§7) alterado | NÃO | só critério de aceitação §4 |

---

## NOTA — subagente de delegação indisponível nesta máquina

Durante a tentativa de rodar este CHANGE-02 como job noturno assíncrono, o
subagente falhou com `Connection error` (3 tentativas, ~34s cada, na primeira
chamada de modelo). Causa raiz: `config.yaml` → `delegation.base_url =
http://127.0.0.1:4000/v1`, e **nada escuta na porta 4000** (LiteLLM local
caído). O gateway do Hermes subiu (PID 24744, portas 8642/8644), mas o broker
de modelo dos subagentes (porta 4000) não está ativo.

Por isso CHANGE-02 foi executado **diretamente** por mim nesta sessão.
Config de infra do Hermes NÃO foi alterada (decisão do dono; mexer afetaria
outros jobs noturnos).

---

*Registro de auditoria. Backlog mantido como referência; runtime intacto.*