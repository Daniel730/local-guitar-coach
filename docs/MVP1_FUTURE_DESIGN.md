# MVP-1 — Perception Engine (Design Note)

**Status:** DESIGN ONLY — não implementado.
**Bloqueado por:** validação física do sinal (ver `docs/MANUAL_TEST.md`).
**Decisão de design:** 2026-08-25, pelo dono do projeto.

---

## Princípio (do ARCHITECTURE.md)

> O LLM não deve substituir o processamento musical determinístico.

O Perception Engine é determinístico. O LLM (MVP-5+) só consome o resultado.

---

## Decisão: não começar com autocorrelação + YIN como duas coisas independentes

A abordagem inicial do documento original sugeria avaliar implementações/libs de
pitch em paralelo. Revisão: **não** fazemos as duas à cega. Começamos por uma
única via sólida e adicionamos o resto só quando necessário.

### Ordem de implementação

```
1. YIN  ──►  frequency
2. frequency ──► MIDI
3. MIDI ──► note + octave
4. (separado) Onset detector ──► "uma nova nota começou aqui"
5. pitch + onset + amplitude ──► Musical Event
```

### Porquê separar pitch de onset

São problemas diferentes:

```
Audio
 │
 ├──► Pitch detector
 │       └── frequency / confidence
 │
 └──► Onset detector
         └── "uma nova nota começou aqui"
```

Tentar resolver os dois num só passo (ex.: autocorrelação que também tenta
detetar ataque) embaralha as métricas. Onset é um evento temporal; pitch é uma
estimação de frequência. Mantê-los separados torna cada um testável isoladamente.

---

## Componentes

### Pitch (YIN)

Entrada: bloco de áudio do `AudioStream` (MVP-0).
Saída:

```json
{
  "frequency": 82.41,
  "confidence": 0.97
}
```

### Conversão frequency → MIDI → note

```text
frequency ──► midi = 69 + 12 * log2(f / 440)
midi       ──► note + octave (ex.: 40 -> "E2")
```

### Onset detector (componente separado)

Corre em paralelo ao pitch. Critério inicial: energia/derivada de amplitude
cruza um limiar após período de silêncio.
Saída: `onset: true` num dado timestamp.

### Musical Event (saída combinada)

Só no fim se juntam os três:

```json
{
  "timestamp": 1.247,
  "frequency": 82.41,
  "note": "E2",
  "midi": 40,
  "confidence": 0.97,
  "amplitude": 0.73,
  "onset": true
}
```

Esquema exato em ARCHITECTURE.md §5.

---

## Critérios de aceitação (MVP-1, quando desbloqueado)

* frequência estável numa nota sustentada;
* nota + oitava corretas;
* confidence coerente (alta em sinal limpo, baixa em ruído);
* onset detetado no ataque, não durante a sustentação;
* resposta em tempo real (usa os blocos do MVP-0).

## Não implementar ainda

* chord detection, string estimation, bend, vibrato, slide, hammer-on,
  pull-off, palm-muting (ARCH §5 — posteriormente).
* Qualquer uso de LLM para determinar nota (proibido por design).

## Razão de validar o sinal físico antes

Guitarra elétrica em sinal direto é muito mais fácil de analisar do que microfone
a captar amplificador/caixa. Se o sinal direto estiver limpo, temos uma base
excelente para o Perception Engine. Só depois testamos M-Track + Cube Baby
(efeitos) para medir o impacto na deteção.
