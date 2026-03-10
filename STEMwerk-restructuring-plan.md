# STEMwerk Restructurering & Afsplitsingsplan

**Datum:** 2026-03-10
**Auteur:** flarkAUDIO + Claude
**Status:** Concept / Advies
**Bronnen:** [STEMwerk](https://github.com/flarkflarkflark/STEMwerk) · [AudioRestorationVST](https://github.com/flarkflarkflark/AudioRestorationVST)

---

## 1. Analyse huidige situatie

### STEMwerk (huidig)

STEMwerk is een REAPER-script (Lua + Python worker) voor AI-gestuurde stem separation via Demucs/audio-separator. De codebase bestaat uit:

- **STEMwerk.lua** — 18.310 regels Lua, bevat de volledige UI (gebouwd op REAPER gfx.*), thema-systeem (classic/ember/ice/mono), i18n (EN/NL/DE, 152 keys), KITT LED-effecten, MilkDrop-style waveform visualisatie, audio-reactive procedural art (8 patronen), keyboard shortcuts, ExtState persistence, en de complete REAPER-integratie (media items, time selections, track management).
- **audio_separator_process.py** — 881 regels Python, de separation engine. Bevat device detection (CUDA, ROCm, DirectML, MPS, CPU), model management (htdemucs, htdemucs_ft, htdemucs_6s, hdemucs_mmi), progress reporting, en de Separator wrapper. Communiceert met Lua via stdout markers (`PROGRESS:xx:message`) en file-based IPC (stdout.txt, done.txt).
- **tools/** — GPU check, benchmarking, stress tests, plotting, GUI installer prototype (PySimpleGUI).
- **i18n/** — Meertalig systeem met Lua wrapper en Python validation tests.
- **installer/** — Cross-platform installer scripts (Linux/macOS/Windows).

### AudioRestorationVST (VINYLwerk)

JUCE C++ project (VST3 + Standalone) voor vinyl restauratie. Relevante architectuurcomponenten:

- **StandaloneWindow** (6.590 regels) — Volledige standalone editor met menu bar, toolbar, drag & drop, transport controls, session management.
- **WaveformDisplay** (1.006 regels) — Zoombare waveform weergave met correctie-overlay.
- **BatchProcessor** — Offline batch processing pattern.
- **AudioFileManager** — File I/O en session save/load.
- **DSP modules** — ClickRemoval, NoiseReduction, FilterBank, SpectralProcessor, OnnxDenoiser.
- **GPU acceleration** — ROCm, CUDA, DirectML, OpenCL, Vulkan support.
- **Build systeem** — CMake met `juce_add_plugin` (VST3) en `juce_add_gui_app` (Standalone).

### Kernprobleem

De STEMwerk-workflow (audio laden → model/stems kiezen → separeren → beluisteren → exporteren) is volledig REAPER-gebonden. De UI zit in Lua/gfx.*, progress monitoring via ExtState, output via REAPER tracks. Niets is draagbaar buiten REAPER.

---

## 2. Doel: drie gespecialiseerde projecten

| Huidig | Nieuw | Beschrijving |
|--------|-------|-------------|
| STEMwerk (repo) | **STEMwerk-reascript** | REAPER Lua + Python worker (rename huidige repo) |
| — | **stemwerk-core** | Python package — de separation engine |
| — | **STEMwerk** | Standalone applicatie (PRIO) |
| — | **STEMwerk-plugin** | VST3 plugin (toekomst, lagere prio) |

### Filosofie

Afsplitsing én symbiose: elk project heeft een eigen doel, maar ze delen `stemwerk-core` als gemeenschappelijke engine. De projecten zijn deelverzamelingen met overlapping in de kern, maar gespecialiseerd in hun interface.

---

## 3. Architectuur: drielaags-model

```
┌─────────────────────┐  ┌──────────────┐  ┌──────────────────┐
│  STEMwerk-reascript  │  │   STEMwerk   │  │  STEMwerk-plugin │
│  (REAPER Lua + Py)   │  │ (Standalone) │  │     (VST3)       │
│                      │  │  PySide6/Qt  │  │   JUCE C++       │
└──────────┬───────────┘  └──────┬───────┘  └────────┬─────────┘
           │                     │                    │
           │    ┌────────────────┴────────────────┐   │
           └────┤         stemwerk-core            ├──┘
                │      (Python package)            │
                │                                  │
                │  • Device detection & selection  │
                │  • Model management              │
                │  • Separation pipeline           │
                │  • Progress callbacks            │
                │  • Output file management        │
                └──────────────────────────────────┘
```

---

## 4. Fase 1 — `stemwerk-core` extractie

**Doel:** De separation engine extraheren uit `audio_separator_process.py` naar een zelfstandig, installeerbaar Python-pakket.

### Wat eruit wordt geëxtraheerd

Uit `audio_separator_process.py` (881 regels):

- `get_available_devices()` (regel 121-330) → `stemwerk_core.devices`
- `select_device()` (regel 333-380) → `stemwerk_core.devices`
- `separate_stems()` (regel 382-880) → `stemwerk_core.separator`
- Model mapping logic → `stemwerk_core.models`
- Progress reporting → callback-gebaseerd (niet meer stdout markers)

### Wat REAPER-specifiek blijft

- `_setup_reaper_io()` — file-based IPC (stdout.txt, done.txt)
- `_TeeTextIO` — dual output stream
- REAPER ExtState communicatie
- De Lua-kant (STEMwerk.lua)

### Package structuur

```
stemwerk-core/
├── pyproject.toml
├── README.md
├── src/
│   └── stemwerk_core/
│       ├── __init__.py          # Public API exports
│       ├── separator.py         # StemSeparator class
│       ├── devices.py           # Device detection & selection
│       ├── models.py            # Model registry & mapping
│       └── progress.py          # Progress callback protocol
└── tests/
    ├── test_devices.py
    ├── test_separator.py
    └── test_models.py
```

### Gewenste API

```python
from stemwerk_core import StemSeparator, get_available_devices

# Device discovery
devices = get_available_devices()
# [{"id": "cuda:0", "name": "RX 9070 XT", "type": "rocm"}, ...]

# Separation met progress callback
sep = StemSeparator(model="htdemucs", device="auto")
sep.on_progress = lambda pct, stage: print(f"{pct}% - {stage}")

result = sep.separate(
    input_file="track.wav",
    output_dir="./stems",
    stems=["vocals", "drums", "bass", "other"]
)
# result.stems -> {"vocals": Path(...), "drums": Path(...), ...}
# result.device_used -> "cuda:0"
# result.elapsed -> 42.3
```

### Refactor van STEMwerk-reascript

Na extractie wordt `audio_separator_process.py` een dunne wrapper:

```python
# audio_separator_process.py (STEMwerk-reascript versie)
from stemwerk_core import StemSeparator, get_available_devices

def main():
    # ... argparse zoals nu ...
    sep = StemSeparator(model=args.model, device=args.device)

    # REAPER-specifieke progress: schrijf naar stdout.txt
    def reaper_progress(pct, stage):
        emit_progress(pct, stage)  # stdout markers voor Lua
    sep.on_progress = reaper_progress

    result = sep.separate(args.input, args.output_dir)
```

### Geschikt voor AI-assistenten

Deze fase is ideaal voor **Claude Code** of **Gemini CLI**: het is grotendeels refactoring van bestaande Python code met duidelijke in/out grenzen.

---

## 5. Fase 2 — `STEMwerk` standalone (PRIO)

### Framework-keuze: PySide6/Qt

**Waarom PySide6:**

- Demucs/audio-separator draait in-process (geen subprocess marshaling nodig)
- Qt is bewezen voor professionele audio-apps (Audacity gebruikt wxWidgets, maar Qt is superieur voor custom painting)
- Uitstekende cross-platform support (Linux, macOS, Windows)
- QAudioOutput voor stem playback
- QOpenGLWidget voor visualisaties (MilkDrop-style)
- Qt Stylesheets voor theming (classic/ember/ice/mono vertaalt direct)
- Distribueerbaar als PyInstaller/Nuitka bundle of AppImage
- AI coding assistants (Codex, Claude Code, Gemini) zijn uitstekend in Qt/Python

**Alternatieven overwogen:**

- JUCE C++ Standalone — meer aligned met AudioRestorationVST, maar separation draait als subprocess; langzamere iteratie.
- Electron/Tauri — te bloated voor een audio tool.

### Kernfeatures (MVP)

De standalone moet de "hele REAPER workflow als standalone" repliceren:

1. **Audio laden** — File open dialog + drag & drop (wav, mp3, flac, ogg)
2. **Waveform display** — Zoombare weergave van geladen audio
3. **Model selectie** — htdemucs, htdemucs_ft, htdemucs_6s (dropdown)
4. **Stem selectie** — Checkboxes: Vocals, Drums, Bass, Other, Guitar, Piano
5. **Quick presets** — Karaoke, Instrumental, Drums Only, Vocals Only, All Stems
6. **Device selectie** — Auto, CPU, CUDA:0, ROCm, DirectML (uit stemwerk-core)
7. **Separation met progress** — Progress bar + ETA + device indicator
8. **Resultaat beluisteren** — Per-stem playback met solo/mute, master mix
9. **Exporteren** — Stems opslaan als WAV/FLAC naar gekozen map
10. **Keyboard shortcuts** — 1-4 toggle stems, K/I/D presets, Enter start, Escape cancel

### UI layout concept

```
┌────────────────────────────────────────────────────────┐
│  ☰  STEMwerk                          🌙 🎨 🌐  ─ □ ✕ │
├────────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────────┐  │
│  │            Waveform Display                      │  │
│  │  ═══════════════════▼═══════════════════════     │  │
│  │  (zoom, scroll, stem-colored overlay na sep.)    │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  ┌─ Model ──────┐  ┌─ Stems ────────────────────────┐  │
│  │ htdemucs    ▼│  │ ☑ Vocals  ☑ Drums  ☑ Bass     │  │
│  └──────────────┘  │ ☑ Other   ☐ Guitar ☐ Piano    │  │
│  ┌─ Device ─────┐  └───────────────────────────────-┘  │
│  │ auto (RX9070)│  ┌─ Presets ──────────────────────┐  │
│  └──────────────┘  │ [Karaoke] [Instru] [Drums] [All]│ │
│                    └────────────────────────────────-┘  │
│  ┌─────────────────────────────────────────────────-┐  │
│  │  [▶]  [■]   ═══════════════  00:00 / 03:45      │  │
│  │  VOC [S][M]  DRM [S][M]  BAS [S][M]  OTH [S][M] │  │
│  └──────────────────────────────────────────────────┘  │
│                                                        │
│  [ 🔬 Separate ]                  [ 💾 Export Stems ]  │
│  ████████████████░░░░░  67%  ETA: 0:42  [cuda:0]      │
└────────────────────────────────────────────────────────┘
```

### Theming

Het bestaande theme-systeem vertalen naar Qt:

```python
THEMES = {
    "classic": {  # Donker, oranje accenten (flarkAUDIO signature)
        "bg": "#1a1a2e",
        "panel": "#16213e",
        "accent": "#e94560",
        "text": "#eaeaea",
        "stem_colors": ["#ff6b6b", "#4ecdc4", "#45b7d1", "#96ceb4", "#feca57", "#ff9ff3"]
    },
    "ember": { ... },
    "ice": { ... },
    "mono": { ... }
}
```

### i18n hergebruik

De 152 translation keys uit `i18n/languages.lua` converteren naar een Python dict of JSON. Veel keys zijn direct herbruikbaar (stems, UI labels, tooltips).

### Geschikt voor AI-assistenten

De PySide6 UI is perfect voor **Codex in VS Code** (interactieve UI-componenten genereren, signal/slot wiring). Layout en widget creatie zijn sterke punten van alle AI code assistants.

---

## 6. Fase 3 — Polish & Features

Na de MVP:

- **Visualisaties** — MilkDrop-style procedural art (8 patronen uit STEMwerk.lua porteerbaar naar QOpenGLWidget/QPainter)
- **KITT LED** — Status indicator animatie
- **Batch mode** — Meerdere bestanden in queue
- **Stem mixing** — Volume faders per stem, realtime mix preview
- **Waveform overlay** — Stem-gekleurde weergave bovenop origineel
- **Session management** — Projecten opslaan/laden
- **Drag & drop export** — Stems direct naar andere apps/DAWs slepen
- **Auto-update** — Check voor nieuwe versies

---

## 7. Fase 4 — `STEMwerk-plugin` (VST3, lagere prio)

### Haalbaarheid

Realtime stem separation is computationeel onhaalbaar met huidige Demucs-modellen (ze verwerken hele files, niet sample-voor-sample). De haalbare aanpak is **offline processing** binnen de DAW:

- Gebruiker selecteert audio regio in de DAW
- Plugin verwerkt offline (vergelijkbaar met iZotope RX, Zynaptiq UNMIX::DRUMS)
- Resultaat wordt teruggeschreven als nieuwe takes/tracks

### Technische aanpak

- **Framework:** JUCE (enige serieuze optie voor VST3)
- **Engine integratie:** `stemwerk-core` via embedded Python (pybind11) of subprocess
- **UI:** Hergebruik patronen uit AudioRestorationVST (BatchProcessor, WaveformDisplay)
- **Formaat:** VST3 + CLAP (conform flarkAUDIO standaard)

### Referentie-architectuur uit AudioRestorationVST

Herbruikbare componenten:
- `BatchProcessor.cpp/h` — Offline processing pattern
- `WaveformDisplay.cpp/h` — Waveform weergave
- `AudioFileManager.cpp/h` — File I/O
- `StandaloneWindow.cpp/h` — Als ook standalone variant gewenst
- CMake build systeem met `juce_add_plugin`

---

## 8. Repository-structuur

### Na restructurering

```
github.com/flarkflarkflark/
├── stemwerk-core/             # Python package (de engine)
│   ├── src/stemwerk_core/
│   ├── tests/
│   └── pyproject.toml
│
├── STEMwerk/                  # Standalone app (PySide6)
│   ├── src/stemwerk/
│   │   ├── ui/                # Qt widgets
│   │   ├── audio/             # Playback engine
│   │   └── main.py
│   ├── resources/
│   │   ├── themes/
│   │   ├── i18n/
│   │   └── icons/
│   └── pyproject.toml         # depends on stemwerk-core
│
├── STEMwerk-reascript/        # REAPER versie (rename van huidig)
│   ├── scripts/reaper/
│   │   ├── STEMwerk.lua       # 18k regels, ongewijzigd
│   │   └── audio_separator_process.py  # dunne wrapper rond stemwerk-core
│   ├── i18n/
│   ├── tools/
│   └── requirements.txt       # depends on stemwerk-core
│
└── STEMwerk-plugin/           # VST3 (toekomst)
    ├── Source/
    ├── JUCE/
    └── CMakeLists.txt
```

### Naming conventie (flarkAUDIO)

| Project | Binary/Package naam | Conventie |
|---------|-------------------|-----------|
| stemwerk-core | `stemwerk-core` (PyPI) | lowercase, engine |
| STEMwerk | `STEMwerk` | [FUNCTION]werk |
| STEMwerk-reascript | `STEMwerk-reascript` | suffix voor REAPER variant |
| STEMwerk-plugin | `STEMwerk-plugin` | suffix voor VST3 variant |

---

## 9. Taakverdeling AI-assistenten

| Taak | Beste tool | Reden |
|------|-----------|-------|
| `stemwerk-core` extractie | Claude Code / Gemini CLI | Python refactoring, duidelijke grenzen |
| PySide6 UI componenten | Codex (VS Code) | Interactieve widget generatie |
| Qt Stylesheet theming | Claude Code | CSS-achtig, goed te beschrijven |
| i18n Lua→Python conversie | Gemini CLI | Straightforward data transformatie |
| JUCE plugin (fase 4) | Claude Code | Complexe C++ build-context |
| CI/CD pipelines | Claude Code | GitHub Actions YAML |
| Testing & benchmarks | Elk | Pytest is universeel |

### Parallellisatie

Fase 1 (`stemwerk-core`) en de UI wireframes voor Fase 2 kunnen parallel door verschillende assistenten. Zodra `stemwerk-core` staat, kan de standalone UI er direct tegenaan bouwen.

---

## 10. Risico's & mitigatie

| Risico | Impact | Mitigatie |
|--------|--------|----------|
| PySide6 packaging (PyInstaller) problemen | Hoog | Vroeg testen op alle 3 platforms; Nuitka als fallback |
| Torch + Qt conflicten (beide claimen GPU) | Middel | Separation in aparte thread/process; Qt gebruikt geen GPU |
| audio-separator API changes | Laag | Pin versie in stemwerk-core; abstractie layer |
| STEMwerk.lua 18k regels moeilijk te onderhouden | Bestaand | Reascript-versie bevriest op feature-set; nieuwe features naar standalone |
| VST3 realtime stem sep onhaalbaar | Verwacht | Scope beperken tot offline processing |

---

## 11. Eerste concrete stappen

1. **Nu:** Review dit plan, beslissingen nemen over naming en framework-keuze
2. **Stap 1:** `stemwerk-core` repo aanmaken, `audio_separator_process.py` refactoren
3. **Stap 2:** Huidig STEMwerk repo renamen naar `STEMwerk-reascript`
4. **Stap 3:** `STEMwerk` repo aanmaken, PySide6 skeleton met file loading + stemwerk-core integratie
5. **Stap 4:** MVP iteratief uitbouwen (waveform → separation → playback → export)

---

*Dit plan is een levend document. Bijwerken naarmate beslissingen worden genomen en de implementatie vordert.*
