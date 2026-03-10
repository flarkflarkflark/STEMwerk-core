from __future__ import annotations

import os
import threading
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple, Union

from .devices import select_device
from .models import resolve_model_name
from .progress import ProgressCallback


def _pkg_version(dist_name: str) -> Optional[str]:
    """Return installed version for a distribution name (best-effort)."""
    try:
        try:
            from importlib.metadata import version  # py3.8+
        except Exception:
            from importlib_metadata import version  # type: ignore
        return version(dist_name)
    except Exception:
        return None


def _resolve_directml_device(device_id: str) -> Tuple[str, bool, int]:
    dml_index = 0
    if ":" in device_id:
        try:
            dml_index = int(device_id.split(":")[1])
        except Exception:
            dml_index = 0

    try:
        import torch_directml  # noqa: F401
        return f"privateuseone:{dml_index}", True, dml_index
    except Exception:
        ort_dml = (
            _pkg_version("onnxruntime-directml")
            or _pkg_version("onnxruntime-gpu")
            or _pkg_version("onnxruntime")
        )
        if ort_dml:
            warnings.warn(
                "DirectML requested but torch-directml not installed; using ONNX Runtime DirectML."
            )
            return f"privateuseone:{dml_index}", True, dml_index
        warnings.warn(
            "DirectML requested but neither torch-directml nor onnxruntime-directml are installed; using CPU."
        )
        return "cpu", False, dml_index


@dataclass(frozen=True)
class SeparationResult:
    """Result of a stem separation run."""

    stems: Dict[str, Path]
    device_used: str
    elapsed: float


class StemSeparator:
    """High-level wrapper around audio-separator for stem separation."""

    def __init__(self, model: str = "htdemucs", device: str = "auto") -> None:
        self.model = model
        self.device = device
        self.on_progress: Optional[ProgressCallback] = None

    def _emit_progress(self, percent: float, message: str) -> None:
        callback = self.on_progress
        if callback is None:
            return
        try:
            callback(percent, message)
        except Exception:
            pass

    def separate(
        self,
        input_file: Union[str, Path],
        output_dir: Union[str, Path],
        stems: Optional[Sequence[str]] = None,
    ) -> SeparationResult:
        """Separate an audio file into stems.

        Args:
            input_file: Path to input audio file.
            output_dir: Directory to write output stems.
            stems: Optional list of stem names to return (e.g., ["vocals", "drums"]).

        Returns:
            SeparationResult with stem paths, device used, and elapsed time.
        """
        start_time = time.time()
        input_path = Path(input_file)
        output_path = Path(output_dir)

        if not input_path.exists():
            raise FileNotFoundError(f"Input file not found: {input_path}")

        output_path.mkdir(parents=True, exist_ok=True)
        model_name = resolve_model_name(self.model)

        self._emit_progress(0.0, "Initializing")

        if str(self.device).lower() == "cpu":
            for key in ("CUDA_VISIBLE_DEVICES", "HIP_VISIBLE_DEVICES", "ROCR_VISIBLE_DEVICES"):
                os.environ[key] = ""

        from audio_separator.separator import Separator
        import torch

        device_id, device_name = select_device(self.device)

        if isinstance(device_id, str) and device_id.startswith("cuda:"):
            try:
                idx = int(device_id.split(":")[1])
                torch.cuda.set_device(idx)
            except Exception as exc:
                warnings.warn(f"Failed to set CUDA device '{device_id}': {exc}")

        if device_id == "cpu":
            separator_device = "cpu"
            use_directml = False
            dml_index = 0
        elif device_id == "mps":
            separator_device = "mps"
            use_directml = False
            dml_index = 0
        elif device_id == "directml" or (
            isinstance(device_id, str) and device_id.startswith("directml:")
        ):
            separator_device, use_directml, dml_index = _resolve_directml_device(device_id)
        else:
            separator_device = device_id
            use_directml = False
            dml_index = 0

        if use_directml:
            os.environ["ORT_DML_DEFAULT_DEVICE_ID"] = str(dml_index)

        separator = Separator(
            output_dir=str(output_path),
            output_format="WAV",
            normalization_threshold=0.9,
            log_level=10,
            use_directml=use_directml,
            mdx_params={"device": separator_device},
            demucs_params={"device": separator_device},
        )

        if use_directml:
            try:
                import torch_directml

                separator.torch_device = torch_directml.device(dml_index)
                separator.torch_device_dml = separator.torch_device
            except Exception as exc:
                warnings.warn(f"Failed to force DirectML device: {exc}")

        self._emit_progress(1.0, f"Initializing [{device_name}]")

        loading_done = threading.Event()

        def loading_progress_thread() -> None:
            start = time.time()
            while not loading_done.is_set():
                elapsed = time.time() - start
                progress_ratio = 1 - (0.5 ** (elapsed / 15))
                percent = int(1 + progress_ratio * 9)
                percent = min(10, percent)

                if elapsed < 60:
                    self._emit_progress(percent, f"Loading model ({elapsed:.0f}s) [{device_name}]")
                else:
                    mins = int(elapsed) // 60
                    secs = int(elapsed) % 60
                    self._emit_progress(percent, f"Loading model ({mins}:{secs:02d}) [{device_name}]")

                loading_done.wait(0.4)

        loading_worker = threading.Thread(target=loading_progress_thread, daemon=True)
        loading_worker.start()

        self._emit_progress(3.0, f"Loading AI model [{device_name}]")

        separator.load_model(model_name)

        loading_done.set()
        loading_worker.join(timeout=1.0)

        self._emit_progress(11.0, f"Starting separation [{device_name}]")

        duration_seconds = 0.0
        try:
            import soundfile as sf

            info = sf.info(str(input_path))
            duration_seconds = float(info.duration)
        except Exception:
            duration_seconds = 180.0

        if device_id == "cpu":
            estimated_time = duration_seconds * 4.0
        else:
            estimated_time = duration_seconds * 0.5

        processing_done = threading.Event()

        def progress_thread() -> None:
            start = time.time()
            last_percent = 11
            while not processing_done.is_set():
                elapsed = time.time() - start
                if estimated_time > 0:
                    progress_ratio = 1 - (0.5 ** (elapsed / estimated_time))
                    percent = int(12 + progress_ratio * 76)
                else:
                    percent = min(88, int(12 + elapsed * 2))

                percent = min(88, max(last_percent, percent))
                last_percent = percent

                mins_elapsed = int(elapsed) // 60
                secs_elapsed = int(elapsed) % 60

                if percent > 15:
                    progress_fraction = (percent - 12) / 78.0
                    if progress_fraction > 0.05:
                        total_est = elapsed / progress_fraction
                        remaining = max(0.0, total_est - elapsed)
                        mins_remaining = int(remaining) // 60
                        secs_remaining = int(remaining) % 60
                        eta_str = f" | ETA {mins_remaining}:{secs_remaining:02d}"
                    else:
                        eta_str = ""
                else:
                    eta_str = ""

                self._emit_progress(
                    percent,
                    f"Processing ({mins_elapsed}:{secs_elapsed:02d}{eta_str}) [{device_name}]",
                )
                processing_done.wait(0.3)

        progress_worker = threading.Thread(target=progress_thread, daemon=True)
        progress_worker.start()

        try:
            output_files = separator.separate(str(input_path))
        finally:
            processing_done.set()
            progress_worker.join(timeout=1.0)

        self._emit_progress(92.0, "Writing stems")

        result: Dict[str, Path] = {}
        stem_mapping = {
            "vocals": ["vocals", "vocal", "Vocals"],
            "drums": ["drums", "drum", "Drums"],
            "bass": ["bass", "Bass"],
            "other": ["other", "Other", "no_vocals", "instrumental", "Instrumental"],
            "guitar": ["guitar", "Guitar"],
            "piano": ["piano", "Piano", "keys", "Keys"],
        }

        for output_file in output_files:
            output_file = Path(output_file)
            if not output_file.is_absolute():
                output_file = output_path / output_file

            filename = output_file.stem.lower()
            matched = False
            for stem_name, patterns in stem_mapping.items():
                for pattern in patterns:
                    if pattern.lower() in filename:
                        new_path = output_path / f"{stem_name}.wav"
                        if output_file != new_path:
                            if new_path.exists():
                                new_path.unlink()
                            import shutil

                            shutil.move(str(output_file), str(new_path))
                        result[stem_name] = new_path
                        matched = True
                        break
                if matched:
                    break

        if stems:
            allowed = {stem.lower() for stem in stems}
            result = {name: path for name, path in result.items() if name.lower() in allowed}

        self._emit_progress(100.0, "Complete")

        elapsed = time.time() - start_time
        return SeparationResult(stems=result, device_used=device_id, elapsed=elapsed)
