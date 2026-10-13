# CHANGE-05 RESULT — Single Source of Truth for Exercise Tempo/BPM

**Status: CLOSED**

## Estado anterior

O tempo/BPM do exercício estava **hardcoded em 3 lugares do código**, e o JSON do
exercício nem sequer o definia. Qualquer mudança de BPM exigia sincronizar 3
constantes independentes — com risco real de divergência.

## Evidências encontradas (EVIDENCE FIRST)

| Local | Símbolo | Papel | Fonte atual | Consumidores |
|---|---|---|---|---|
| `coach.py:54-56` | `EXERCISE_TEMPO` dict | define tempo | hardcoded no código | coach pipeline |
| `coach.py:121` | `EXERCISE_TEMPO.get(ex.id, default)` | lê tempo | hardcoded | coach |
| `app/models/session.py:138-144` | `EXERCISE_TEMPO` + `get_exercise_tempo()` | define tempo | hardcoded no código | session_service, routes |
| `app/services/teacher_service.py:59-62` | `_get_tempo()` | define tempo | hardcoded no código | teacher |
| `exercises/scale_e_minor_001.json` | *(nenhum)* | — | JSON NÃO tinha tempo | — |
| `exercises/exercise.py:29-30` | `start_bpm`/`target_bpm` opcionais | schema | loader aceitava mas JSON não definia | — |

## Root cause

O tempo era tratado como **configuração do código**, não como **propriedade do
conteúdo/exercício**. O `Exercise` dataclass já tinha `start_bpm`/`target_bpm`
opcionais, mas o JSON não os preenchia — logo o loader devolvia `None` e o
código caía no hardcode. Três fontes independentes podiam divergir.

## Design escolhido

**O exercício é a fonte de verdade.** O tempo passa a ser definido no JSON do
exercício, carregado pelo `Exercise` dataclass, e consumido por todos via
`exercise.start_bpm` / `exercise.target_bpm` / `exercise.subdivision`.

```
Exercise JSON
      ↓
Exercise Definition (dataclass)
      ↓
tempo/BPM (start_bpm, target_bpm, subdivision)
      ↓
Session / Coach / Teacher / Evaluation / UI
```

Sem constantes duplicadas. Se um exercício não tiver tempo no JSON, o runtime
**falha visivelmente** (não cai em fallback silencioso).

## Arquivos alterados

- `exercises/scale_e_minor_001.json` — adicionado `start_bpm: 60`, `target_bpm: 100`, `subdivision: "quarter"`
- `exercises/exercise.py` — adicionado campo `subdivision` ao dataclass + loader + `to_dict()`
- `coach.py` — removido `EXERCISE_TEMPO`; lê `ex.target_bpm`/`ex.subdivision`/`ex.start_bpm`; falha visível se faltar
- `app/models/session.py` — removido `EXERCISE_TEMPO`/`get_exercise_tempo`
- `app/services/session_service.py` — `create_session` carrega o exercício e deriva o tempo dele
- `app/services/teacher_service.py` — removido `_get_tempo`; usa `self.exercise.*`
- `app/api/routes.py` — `list_exercises`/`get_exercise`/`progress` usam `ex.target_bpm`; itera ficheiros JSON
- `tests/test_change05.py` — novo (8 testes)

## Testes RED → GREEN

Não houve RED (a suite existente já passava antes; a mudança foi refactor de
fonte de verdade, não correção de bug). Os 8 testes novos provam o contrato:

1. `test_exercise_tempo_loaded_from_json` — tempo carregado do JSON
2. `test_coach_no_hardcoded_tempo_dict` — coach sem `EXERCISE_TEMPO`, lê do exercício
3. `test_teacher_no_independent_tempo_copy` — teacher sem `_get_tempo`, usa `self.exercise`
4. `test_teacher_service_uses_exercise_tempo` — policy com bounds do exercício
5. `test_models_no_exercise_tempo_dict` — models/session sem segunda fonte
6. `test_session_service_loads_tempo_from_exercise` — session deriva do exercício
7. `test_divergence_impossible` — loader reflete o JSON; session == exercício
8. `test_no_hardcoded_bpm_100_in_runtime` — sem `target_bpm=100` hardcoded

## Suite completa

- **105 passed, 1 skipped** (97 anteriores + 8 novos)

## Re-audit das referências de tempo

- Antes: `EXERCISE_TEMPO` em 2 ficheiros + `_get_tempo` em 1 + `get_exercise_tempo` em 1 = **4 locais de duplicação**
- Depois: **0** referências antigas no código-fonte (grep limpo)
- As únicas ocorrências restantes são `.pyc` (bytecode compilado, irrelevante)

## Arquivos explicitamente NÃO alterados

- `perception/` (intocado)
- `audio_probe/stream.py` (P2-D intocado — `indata[:,0]` permanece)
- `frontend/` (intocado neste CHANGE)
- `ai/teacher/` (intocado)
- `tests/` existentes (só adicionado `test_change05.py`)

## Rollback

Reverter manualmente (sem depender de `git reset --hard`):

1. `exercises/scale_e_minor_001.json` — remover `start_bpm`/`target_bpm`/`subdivision`
2. `exercises/exercise.py` — remover campo `subdivision` do dataclass/loader/to_dict
3. `coach.py` — restaurar o dict `EXERCISE_TEMPO` e o uso `EXERCISE_TEMPO.get(ex.id, ...)`
4. `app/models/session.py` — restaurar `EXERCISE_TEMPO` + `get_exercise_tempo()`
5. `app/services/session_service.py` — restaurar `get_exercise_tempo(exercise_id)`
6. `app/services/teacher_service.py` — restaurar `_get_tempo()`
7. `app/api/routes.py` — restaurar `get_exercise_tempo`/`EXERCISE_TEMPO`
8. Apagar `tests/test_change05.py`

## Estado final

**CHANGE-05: CLOSED.**

O BPM/tempo de um exercício é definido pelo conteúdo do exercício, e todos os
consumidores relevantes (coach, session, teacher, routes) obtêm esse valor
através dessa definição — sem constantes duplicadas independentes.
