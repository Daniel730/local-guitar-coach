# Riff — professor de guitarra local

Tutor de guitarra local e adaptativo: ouve você tocar (M-Track Duo, CH2), compara com o
exercício, mede notas/timing/BPM/consistência (sem nota final) e um professor no Ollama
diz em voz alta (pt-BR) o que fazer a seguir. Contrato canônico: `docs/PROJECT_STATE.md`.

## Usar

1. Guitarra → Cuvave Cube Baby → **CH2** (Hi-Z/INST) da M-Track, ligada por USB.
2. Duplo clique em **`start.bat`**. Ele inicia o Ollama, escolhe o modelo, sobe o app e abre o navegador.
3. Escolha um exercício ou uma música → **Iniciar** → contagem 3-2-1 → toque.
4. Cada **tentativa** termina quando você toca todas as notas ou fica 2,5 s em silêncio.
   O professor responde (texto + voz) e o banner sugere o próximo exercício quando você domina o atual
   (2 de 3 tentativas dentro dos critérios).

Conteúdo: 12 exercícios (cordas soltas, pentatônicas, cromático, escalas maior/menor, colcheias, blues)
e 5 músicas de domínio público (Brilha Brilha Estrelinha, Ode à Alegria, Frère Jacques, Jingle Bells,
When the Saints), praticadas frase a frase e depois completas.

## Configuração

| Variável | Padrão | Para quê |
|---|---|---|
| `RIFF_OLLAMA_MODEL` | `qwen2.5:7b` (~1,5 s por tentativa), senão `llama3.1:8b`, senão `gpt-oss:20b`, senão o 1º instalado | modelo do professor |
| `RIFF_OLLAMA_THINK` | `low` para gpt-oss | modelos com raciocínio respondem em ~8 s |
| `PORT` | 8000 (ou a próxima livre) | porta do app |

Sem Ollama o app funciona igual: o professor usa o fallback determinístico (REPEAT).

## Desenvolvimento

```
python -m pip install -r requirements.txt
python -m pytest                       # sem hardware
python -m perception --self-test       # percepção com sinal sintético
python -m audio_probe --list           # dispositivos de áudio
```

Layout: `perception/` (núcleo congelado: YIN, EventTracker, matcher, avaliação), `ai/teacher/`
(Ollama → schema → policy), `exercises/` (JSONs + `curriculum.py`), `app/` (FastAPI + WS,
captura server-side), `frontend/` (HTML/JS puro, só plota telemetria).
