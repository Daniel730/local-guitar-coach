# Teste Físico — Validação do Sinal (pré-MVP-1)

**Objetivo:** confirmar que a guitarra chega limpa e em nível adequado à
interface **antes** de colocar qualquer algoritmo de pitch em cima do sinal.

**Estado:** MVP-0 aprovado. Este teste é o portão de entrada para o MVP-1.

---

## Setup

```text
Guitarra
   ↓
M-Track Duo
   ↓ USB
Windows
   ↓
audio_probe
```

* Guitarra ligada **direta** à M-Track Duo (sem Cube Baby nesta fase).
* Cabo instrumento na entrada 1 (ou 2) da M-Track Duo.
* M-Track Duo já aparece como device index **1** (host MME) no `--list`.

### Confirmar dispositivo

```bash
python -m audio_probe --list
```

Esperado: `1* MME ... Line 1/2 (9- M-Audio M-Track ...`

---

## Como capturar

Ver ao vivo (meters em dBFS por bloco):

```bash
python -m audio_probe --device 1 --seconds 10
```

Guardar o output estruturado:

```bash
python -m audio_probe --device 1 --seconds 10 --json > capture.json
```

(`--json` grava o resultado completo: device, blocks, max peak, latência.)

---

## O que observar (alvos, não exigências exatas)

| Condição        | Alvo dBFS     | Nota                                  |
|-----------------|---------------|---------------------------------------|
| silêncio        | ≈ -60 ou abaixo | piso de ruído                         |
| nota fraca      | ≈ -30 / -20   | palhetada leve                        |
| nota normal     | ≈ -18 / -6    | toque comum                           |
| pico forte      | < 0 dBFS      | headroom: não clipar                  |

Objetivo: verificar **headroom** (pico forte nunca chega a 0 dBFS / clipping)
e **relação sinal-ruído** (nota normal bem acima do piso de silêncio).

---

## Três testes

1. **Cordas soltas** — toca E, A, D, G, B, e (mi grave a mi agudo).
   Observa se cada nota dá pico claro e estável.
2. **Notas no braço** — algumas notas isoladas em posições diferentes.
3. **Ataques diferentes** — palhetada fraca vs. palhetada forte no mesmo lugar.
   Observa a diferença de amplitude nos meters.

Guarda o output (`capture.json` ou anotação dos picos) de cada um.

---

## Critério de passagem → MVP-1

* sinal limpo (sem clipping: pico forte < 0 dBFS);
* boa SNR (nota normal muito acima de ~-60 dBFS de silêncio);
* stream estável durante os 10s;
* latência aceitável (MVP-0 mediu ~23 ms configurada em MME).

Se passar: implementa-se o MVP-1 (ver `MVP1_FUTURE_DESIGN.md`).
Se não: investiga ganho/cabos/ligacao da M-Track Duo **antes** do algoritmo.

---

## Depois (futuro, não agora)

```text
M-Track
   ├── guitarra direta
   └── Cube Baby (efeitos)
```

Comparar direto vs. Cube Baby para medir quanto os efeitos prejudicam ou
melhoram a deteção de pitch.
