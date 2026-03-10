# STEMwerk-core

stemwerk-core is the AI stem separation engine for the flarkAUDIO ecosystem.
It provides a clean Python API around the audio-separator backend.

## Install

```bash
pip install stemwerk-core
```

## Quickstart

```python
from stemwerk_core import StemSeparator

sep = StemSeparator(model="htdemucs", device="auto")
sep.on_progress = lambda pct, msg: print(f"{pct:.0f}% - {msg}")
result = sep.separate("input.wav", output_dir="./stems", stems=["vocals", "drums"])

print(result.device_used)
print(result.elapsed)
print(result.stems)
```

## Ecosystem

STEMwerk ecosystem: https://github.com/flarkflarkflark/stemwerk
