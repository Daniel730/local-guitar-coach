# CHANGE-06 RESULT — Exercise Schema v2 + Skills/Subskills

**Status: CLOSED**

## Estado anterior

O `Exercise` dataclass tinha apenas `id, name, skill, difficulty, target_notes`
+ tempo (adicionado no CHANGE-05). Não havia `subskill`, `technique`, `objective`,
`prerequisites`, `evaluation`, `success/failure_criteria`, `common_mistakes`,
`hints`. `skill` era uma string livre sem validação contra um domínio conhecido.
`subskill` não existia em lado nenhum.

## Design contract (tabela de campos)

| Campo | Tipo | Obrigatório? | Fonte atual | Consumidor atual | Motivo |
|---|---|---|---|---|---|
| `id` | str | ✅ | JSON | loader, session, teacher, routes | identidade |
| `name` | str | ✅ | JSON | UI, routes | display |
| `description` | str | ❌ (novo) | JSON | — | contrato de conteúdo |
| `skill` | str | ✅ | JSON | routes, session_service→SkillState, build_context | agrupa progresso |
| `subskill` | str | ❌ (novo) | JSON | — | contrato de conteúdo |
| `technique` | str | ❌ (novo) | JSON | — | contrato de conteúdo |
| `difficulty` | int | ✅ | JSON | routes, UI | nível |
| `target_notes` | list[str] | ✅ | JSON | loader→expected_sequence, sequence, performance | o que tocar |
| `start_bpm` | int | ✅ (CHANGE-05) | JSON | coach, session, teacher | tempo |
| `target_bpm` | int | ✅ (CHANGE-05) | JSON | coach, session, teacher, routes | tempo |
| `subdivision` | str | ✅ (CHANGE-05) | JSON | coach, session, teacher, performance | tempo |
| `objective` | str | ❌ (novo) | JSON | — | contrato de conteúdo |
| `prerequisites` | list[str] | ❌ (existia, sem consumidor) | JSON | — | contrato de conteúdo |
| `evaluation` | dict | ❌ (novo) | JSON | — | contrato de conteúdo |
| `success_criteria` | dict | ❌ (novo) | JSON | — | contrato de conteúdo |
| `failure_criteria` | dict | ❌ (novo) | JSON | — | contrato de conteúdo |
| `common_mistakes` | list[str] | ❌ (novo) | JSON | — | contrato de conteúdo |
| `hints` | list[str] | ❌ (novo) | JSON | — | contrato de conteúdo |
| `progression` | dict | ❌ (existia, sem consumidor) | JSON | — | contrato de conteúdo |

**Princípio:** campos novos são **contrato de conteúdo** — carregados, validados,
expostos, mas **sem motor que os execute** (como pedido). `skill`/`subskill`/
`technique` são entidades de domínio mínimas. Campos obrigatórios validados; sem
fallback silencioso para valores mágicos.

## Arquivos alterados

- `exercises/exercise.py` — Schema v2: campos novos no dataclass + `_from_dict` + `to_dict`; `REQUIRED_FIELDS`; `validate_exercise()`
- `exercises/skills.py` — **novo**: entidades `Skill`/`Subskill` + catálogo `KNOWN_SKILLS`/`KNOWN_SUBSKILLS` + `validate_exercise_skill()`
- `exercises/scale_e_minor_001.json` — migrado para Schema v2 (description, subskill, technique, objective, evaluation, success/failure, common_mistakes, hints, progression)
- `tests/test_exercise.py` — fixtures atualizadas com tempo (compatibilidade determinística)
- `tests/test_change06.py` — **novo** (9 testes)

## Testes

- **9 novos** (`tests/test_change06.py`): schema v2 carrega, roundtrip, required fields enforced, skill/subskill validation, catálogo de skills, session/teacher ainda funcionam
- **Suite completa: 114 passed, 1 skipped** (105 + 9)

## Re-audit

- `perception/` e `audio_probe/` **intocados** (git diff limpo)
- Servidor sobe (health 200); `/api/exercises` lista o exercício com schema v2
- `skill` continua consumido por routes/session_service/build_context (inalterado)
- `subskill`/`technique`/`objective`/etc. são contrato de conteúdo — **sem consumidor ainda** (por design, CHANGE-06)

## Arquivos explicitamente NÃO alterados

- `perception/` (intocado)
- `audio_probe/` (P2-D intocado)
- `frontend/` (intocado)
- `ai/teacher/` (intocado)
- `app/` (intocado — session/teacher continuam a funcionar com o loader v2)
- `coach.py` (intocado)

## Rollback

Reverter manualmente:
1. `exercises/exercise.py` — restaurar o dataclass v1 (sem campos novos) e `_from_dict` v1
2. `exercises/skills.py` — apagar
3. `exercises/scale_e_minor_001.json` — remover os campos novos (voltar ao schema v1 + tempo)
4. `tests/test_exercise.py` — reverter fixtures (remover tempo)
5. `tests/test_change06.py` — apagar

## Estado final

**CHANGE-06: CLOSED.**

O exercício é agora um contrato de conteúdo rico e extensível (Schema v2), com
entidades de domínio mínimas para skill/subskill. Os campos pedagógicos novos
estão definidos e validados, prontos para o futuro motor de aprendizagem — mas
**nenhum motor os executa ainda** (por design). A fundação para o sistema de
ensino está lançada sem quebrar nada do que existia.
