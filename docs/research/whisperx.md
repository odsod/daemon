# WhisperX

- Repo: https://github.com/m-bain/whisperX @ `8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365` (studied 2026-11-22)
- License: BSD-2-Clause ([LICENSE](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/LICENSE#L1-L24)) | Stars: 25,598 | Last release: [3.8.7rc1](https://github.com/m-bain/whisperX/releases/tag/3.8.7rc1) (2026-06-26; latest stable [v3.8.6](https://github.com/m-bain/whisperX/releases/tag/v3.8.6), 2026-05-25) | Stack: Python 3.10-3.13, PyTorch 2.8, CTranslate2, faster-whisper, Hugging Face transformers, pyannote-audio 4.x, optional Numba and torchaudio ([pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L8-L35))

## Scope

WhisperX is an offline CLI tool and Python library for batch speech-to-text transcription of audio files with word-level timestamps and speaker diarization ([README.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/README.md#L36-L43), [whisperx/__main__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__main__.py#L13-L26)). It has no live audio capture, daemon mode, GUI, hotkeys, or text injection.

## Architecture (processes, services, IPC, state)

WhisperX runs as a single synchronous Python process invoked via the `whisperx` CLI entry point ([pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L36-L37), [whisperx/__main__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__main__.py#L98-L100)) or imported as a lazy-loading Python package ([whisperx/__init__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__init__.py#L4-L32)). There are no background services, daemons, or IPC layers.

The CLI executes three sequential stages across all input files and explicitly frees GPU memory between stages ([whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L125-L240)):

1. Load Whisper + VAD model, transcribe every input file, then run `del model; gc.collect(); torch.cuda.empty_cache()` ([whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L125-L165)).
2. Load the language-specific wav2vec2 alignment model, run forced alignment on each result, then unload it with `del align_model; gc.collect(); torch.cuda.empty_cache()` ([whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L167-L208)).
3. Load `DiarizationPipeline` (if `--diarize`), run diarization per file, assign speakers to segments and words, and write output files ([whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L210-L240)).

## Audio capture (API, rate, buffering, system audio)

Live audio capture and system audio recording: Not found. Looked in `whisperx/audio.py`, `whisperx/__main__.py`, and `whisperx/transcribe.py`.

WhisperX decodes pre-recorded files by spawning `ffmpeg` as a subprocess and piping raw 16-bit signed little-endian mono PCM at 16 kHz (`SAMPLE_RATE = 16000`) into memory ([whisperx/audio.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/audio.py#L13-L65)):

```python
cmd = [
    "ffmpeg", "-nostdin", "-threads", "0", "-i", file,
    "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(sr), "-",
]
out = subprocess.run(cmd, capture_output=True, check=True).stdout
return np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0
```

It buffers the entire decoded file in RAM as a `float32` NumPy array ([whisperx/audio.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/audio.py#L61-L65)). When processing multiple files or running diarization, it calls `load_audio()` again per stage ([whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L176-L180), [whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L131-L132)). Log-Mel spectrograms use `N_FFT = 400`, `HOP_LENGTH = 160`, `CHUNK_LENGTH = 30`, and bundled `mel_filters.npz` for 80 or 128 mels ([whisperx/audio.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/audio.py#L14-L18), [whisperx/audio.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/audio.py#L94-L159)).

## VAD and segmentation

WhisperX runs VAD before ASR to cut long audio into speech chunks up to `chunk_size` seconds (default `30`), reducing hallucinations and enabling batched Whisper decoding ([whisperx/__main__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__main__.py#L40-L43), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L308-L314)). It supports two VAD backends:

- **Pyannote (default):** Loads a bundled checkpoint at `whisperx/assets/pytorch_model.bin` via `pyannote.audio.Model.from_pretrained` ([whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L21-L49)). `VoiceActivitySegmentation` returns raw frame probability scores (`SlidingWindowFeature`) instead of binarized intervals ([whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L228-L230)). A custom `Binarize` class applies hysteresis thresholding (`vad_onset = 0.500`, `vad_offset = 0.363`) and a min-cut split whenever an active region exceeds `max_duration` (`chunk_size`): it searches the second half of the active frames and cuts at the lowest speech-probability frame ([whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L139-L157)):

```python
if curr_duration > self.max_duration:
    search_after = len(curr_scores) // 2
    min_score_div_idx = search_after + np.argmin(curr_scores[search_after:])
    min_score_t = curr_timestamps[min_score_div_idx]
    region = Segment(start - self.pad_onset, min_score_t + self.pad_offset)
    active[region, k] = label
```

  Note that `load_vad_model()` sets `min_duration_on=0.1` and `min_duration_off=0.1` on the pipeline, but `Pyannote.merge_chunks()` creates `Binarize(max_duration=chunk_size, onset=onset, offset=offset)` with `min_duration_on=0.0` and `min_duration_off=0.0` because `Binarize` raises `NotImplementedError` if `min_duration_off > 0` with a finite `max_duration` ([whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L42-L45), [whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L174-L176), [whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L254)).

- **Silero (`--vad_method silero`):** Loads `snakers4/silero-vad` via `torch.hub.load(..., onnx=False, trust_repo=True)` and requires 16 kHz audio ([whisperx/vads/silero.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/silero.py#L26-L40)). It calls `get_speech_timestamps()` with `max_speech_duration_s=self.chunk_size` and `threshold=self.vad_onset`, leaving `min_silence_duration_ms`, `min_speech_duration_ms`, and `vad_offset` unused ([whisperx/vads/silero.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/silero.py#L42-L52)).

- **Chunk merging (`Vad.merge_chunks`):** Both VADs feed speech segments into a greedy forward merger that packs consecutive speech segments into one chunk while `seg.end - curr_start <= chunk_size` ([whisperx/vads/vad.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/vad.py#L20-L53)).

## ASR (backends, models, language handling, prompts, custom vocabulary)

- **Backend and device fallback:** Uses `faster-whisper` (`ctranslate2`) wrapped in `WhisperModel` and a Hugging Face `Pipeline` subclass `FasterWhisperPipeline` ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L33-L136)). Default device priority is `cuda > npu > cpu`; `mps` is not auto-selected because CTranslate2 lacks an Apple GPU backend ([whisperx/device_utils.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/device_utils.py#L4-L16)). If CTranslate2 does not support the chosen accelerator, Whisper ASR falls back to CPU while PyTorch stages stay on the accelerator ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L509-L515)). Default `compute_type` is `float16` on CUDA/NPU and `float32` on CPU ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L517-L520)).
- **Batched decoding:** `preprocess()` pads each merged VAD slice to 30 seconds (`N_SAMPLES = 480000`) and computes its log-Mel spectrogram ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L195-L203)). A PyTorch `DataLoader` stacks batches of size `batch_size` (CLI default `8`) ([whisperx/__main__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__main__.py#L22), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L254-L259)). `generate_segment_batched()` runs one `model.encode()` and one `model.generate()` call per batch with `without_timestamps=True`, `beam_size=5`, and `condition_on_previous_text=False` ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L80-L95), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L539-L556)). Note: `transcribe.py` hardcodes `"condition_on_previous_text": False` even though `--condition_on_previous_text` exists in the CLI parser ([whisperx/__main__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__main__.py#L63), [whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L108)).
- **Interleaved context (`--interleaved_context`):** Splits VAD segments into `batch_size` contiguous streams and interleaves them so batch slot `i` processes stream `i` in order, feeding up to `224 - len(initial_prompt_tokens)` rolling output tokens as prompt context for the next segment in that stream ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L56-L66), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L219-L234), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L363-L382)). After the main pass, it re-runs the first batch with wrap-around context from stream `i - 1`, then sorts all segments by `start` ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L411-L439)).
- **Language handling:** If `--language` is omitted, `detect_language()` runs the encoder on the first 30 seconds of audio ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L451-L463)). Models ending in `.en` force `"en"` ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L522-L523)).
- **Prompts and custom vocabulary:** Supports `--initial_prompt` (encoded and prepended to each batch prompt) and `--hotwords` (passed to `faster-whisper`'s `get_prompt()`) ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L51-L78)). Also supports `--suppress_numerals`, which scans the tokenizer and suppresses tokens containing `0123456789%$£` so spoken numbers spell out as words for wav2vec2 alignment ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L24-L31), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L335-L341)).

## Post-processing (LLM cleanup, prompts, glossary, replacements)

LLM cleanup, glossaries, and text replacements: Not found. Looked in `whisperx/transcribe.py`, `whisperx/alignment.py`, `whisperx/utils.py`, and `whisperx/SubtitlesProcessor.py`.

WhisperX performs three non-LLM post-processing steps:

- **Forced phoneme alignment (`whisperx/alignment.py`):** Loads a language-specific wav2vec2 CTC model from `torchaudio.pipelines` for `en, fr, de, es, it` (with automatic fallback to `facebook/wav2vec2-*` Hugging Face models when `torchaudio` is missing) or from `DEFAULT_ALIGN_MODELS_HF` for 36 other languages ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L52-L149)). It runs unbatched per-segment inference (`waveform_segment` padded to at least 400 samples) ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L286-L306)). Unknown characters (digits, symbols) map to a synthetic wildcard column equal to the max non-blank log-probability per frame ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L314-L324)). Trellis dynamic programming and backtracking run via Numba `@njit` when installed (`whisperx[fast]`), with a native PyTorch fallback ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L473-L607)).
- **Sentence splitting and timestamp interpolation:** Splits aligned segments into sentences using NLTK `punkt_tab` and fills missing word or sentence timestamps via `interpolate_nans()` (`nearest`, `linear`, or `ignore`) ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L182-L192), [whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L406-L438), [whisperx/utils.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/utils.py#L470-L476)).
- **Subtitle line wrapping:** `SubtitlesWriter` supports `max_line_width`, `max_line_count`, and `highlight_words` for SRT/VTT ([whisperx/utils.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/utils.py#L248-L368)). An additional standalone `SubtitlesProcessor` splits lines at commas and conjunctions ([whisperx/SubtitlesProcessor.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/SubtitlesProcessor.py#L33-L138)).

## Hotkeys on Wayland/KDE (mechanism, hold vs toggle)

Not found. Looked in `whisperx/__main__.py`, `whisperx/transcribe.py`, and `pyproject.toml`. WhisperX is a headless CLI and Python library.

## Text delivery (paste vs type, tools, clipboard restore, per-app, unicode)

Not found. Looked in `whisperx/__main__.py`, `whisperx/utils.py`, and `pyproject.toml`. WhisperX writes transcript files to disk instead of injecting text into applications.

## UI feedback (overlay, tray, notifications)

Not found. Looked in `whisperx/__main__.py`, `whisperx/transcribe.py`, and `whisperx/log_utils.py`. Feedback is limited to terminal logs, `--print_progress` percentages, and Python `progress_callback` hooks ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L385-L390), [whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L139-L165)).

## Meeting features (system audio, mic mute, diarization, speakers, summaries)

System audio capture, mic mute handling, and LLM meeting summaries: Not found. Looked in `whisperx/transcribe.py`, `whisperx/diarize.py`, and `whisperx/audio.py`.

Speaker diarization is implemented in `whisperx/diarize.py`:

- **Diarization model:** `DiarizationPipeline` wraps `pyannote.audio.Pipeline.from_pretrained`, defaulting to `pyannote/speaker-diarization-community-1` (requires a Hugging Face token via `--hf_token` and license acceptance) ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L91-L103), [README.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/README.md#L125)). It accepts `num_speakers`, `min_speakers`, `max_speakers`, and `return_embeddings` ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L105-L182)).
- **Speaker assignment (`assign_word_speakers`):** Builds a sorted-array `IntervalTree` using `np.searchsorted` over pyannote speaker turns for fast overlap queries ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L14-L89)). For each segment and each aligned word with a `start` timestamp, it sums intersection durations per speaker and assigns the speaker with the largest overlap ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L217-L258)):

```python
overlaps = tree.query(seg_start, seg_end)
if overlaps:
    speaker_intersections = {}
    for speaker, intersection in overlaps:
        speaker_intersections[speaker] = speaker_intersections.get(speaker, 0.0) + intersection
    seg['speaker'] = max(speaker_intersections.items(), key=lambda x: x[1])[0]
```

  An optional `fill_nearest=False` parameter falls back to the speaker whose segment midpoint is closest when there is no overlap ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L189), [whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L230-L235)).
- **Speaker embeddings:** `--speaker_embeddings` includes per-speaker embedding vectors in the JSON output (`result["speaker_embeddings"]`) ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L174-L176), [whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L260-L261)).

## Data and storage

WhisperX has no database or persistent session store. It writes UTF-8 output files next to `--output_dir` (default `.`) in `txt`, `vtt`, `srt`, `tsv`, `json`, or `aud` (Audacity labels), defaulting to `all` (`txt`, `vtt`, `srt`, `tsv`, `json`) ([whisperx/__main__.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/__main__.py#L25-L26), [whisperx/utils.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/utils.py#L221-L229), [whisperx/utils.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/utils.py#L443-L468)).

Models are cached in `--model_dir` (when set), Hugging Face cache, `torch.hub` cache (for Silero VAD and torchaudio pipelines), and NLTK's data directory (for `punkt_tab`), while the Pyannote VAD checkpoint ships inside the package at `whisperx/assets/pytorch_model.bin` ([whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L22-L30), [whisperx/vads/silero.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/silero.py#L26-L30), [whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L183-L192)).

## Packaging and install

Distributed on PyPI as `whisperx` (`pip install whisperx` or `uvx whisperx`) using `setuptools` ([pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L39-L48), [README.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/README.md#L74-L84)). Requires `ffmpeg` on `PATH` and CUDA 12.8 for GPU builds (`[tool.uv.index]` points to `https://download.pytorch.org/whl/cu128`) ([pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L74-L77), [README.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/README.md#L65-L70), [README.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/README.md#L110)). Optional extras are `whisperx[fast]` (`numba>=0.68.0`) and `whisperx[align-torch]` (`torchaudio~=2.8.0`) ([pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L28-L35)). `torchcodec` is excluded on Linux `aarch64` due to missing wheels ([pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L22), [pyproject.toml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/pyproject.toml#L49-L54)).

## Tests and benchmarks

CI runs `uv run pytest tests/ -v` on `ubuntu-latest` across Python 3.10 to 3.13 ([.github/workflows/tests.yml](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/.github/workflows/tests.yml#L12-L36)). The test suite contains two mocked unit test files with no audio fixtures or end-to-end ASR tests:

- `tests/test_align_model_fallback.py`: verifies `TORCHAUDIO_PIPELINE_TO_HF` fallback when `torchaudio` is unavailable ([tests/test_align_model_fallback.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/tests/test_align_model_fallback.py#L8-L48)).
- `tests/test_word_timestamp_interpolation.py`: tests wildcard CTC alignment and `interpolate_nans()` with synthetic emission matrices ([tests/test_word_timestamp_interpolation.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/tests/test_word_timestamp_interpolation.py#L54-L231)).

Benchmarks: Not found in the repo. `README.md` lists benchmarking code as an unchecked TODO ([README.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/README.md#L284)).

## Known pitfalls (top Linux/Wayland issues from the tracker)

Wayland/KDE issues: Not found (no desktop integration; the single search hit [#1382](https://github.com/m-bain/whisperX/issues/1382) is an unrelated Python environment error). Top Linux and pipeline pitfalls from the tracker:

- **cuDNN library loading and version conflicts on Linux:** PyTorch bundles cuDNN while `ctranslate2` or system `LD_LIBRARY_PATH` can resolve a mismatched `libcudnn_cnn.so.9`, causing crashes documented in [CUDNN_TROUBLESHOOTING.md](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/CUDNN_TROUBLESHOOTING.md#L5-L76).
- **No AMD ROCm GPU support:** CTranslate2 lacks ROCm support, so Linux AMD GPU users cannot accelerate Whisper ASR ([issue #566](https://github.com/m-bain/whisperX/issues/566), [issue #1231](https://github.com/m-bain/whisperX/issues/1231)).
- **`--device_index` ignored by alignment and diarization:** `transcribe.py` passes `device_index` to `load_model()` but passes only `device` to `load_align_model()` and `DiarizationPipeline`, pinning them to GPU 0 ([issue #547](https://github.com/m-bain/whisperX/issues/547), [whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L171-L173), [whisperx/transcribe.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/transcribe.py#L220)).
- **High RAM usage on long audio:** `load_audio()` holds the full `ffmpeg` stdout bytes and `float32` array in RAM simultaneously, risking OOM on 10+ hour recordings ([issue #1440](https://github.com/m-bain/whisperX/issues/1440), [whisperx/audio.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/audio.py#L61-L65)).
- **VAD boundary mismatch between Silero ASR and Pyannote diarization:** Selecting `--vad_method silero` only changes ASR chunking; pyannote diarization still runs its own internal segmentation, which can drift at speech boundaries ([issue #1288](https://github.com/m-bain/whisperX/issues/1288)).
- **Silero VAD options are hard to tune:** `whisperx/vads/silero.py` does not pass `min_silence_duration_ms`, `min_speech_duration_ms`, or `vad_offset` through to `get_speech_timestamps()` ([issue #1187](https://github.com/m-bain/whisperX/issues/1187), [whisperx/vads/silero.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/silero.py#L42-L51)).
- **Wildcard alignment regressions:** Reintroducing the CTC wildcard column for digits and punctuation in v3.8.3+ brought back alignment accuracy regressions reported in [issue #1449](https://github.com/m-bain/whisperX/issues/1449) ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L314-L322)).
- **Slow or noisy diarization:** Pyannote diarization does not expose batch size controls from the CLI and can be slow or misassign speakers on overlapping or noisy audio ([issue #274](https://github.com/m-bain/whisperX/issues/274), [issue #1208](https://github.com/m-bain/whisperX/issues/1208)).

## Ideas for the recorder

- **Copy: min-cut splitting for long continuous speech.** When a speaker talks past the 30-second Whisper window without a full pause, cut in the second half of the active region at the frame with the lowest VAD speech score (pyannote `Binarize`, used for both VAD backends) rather than at a hard 30-second boundary ([whisperx/vads/pyannote.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/pyannote.py#L140-L149)).
- **Copy: greedy chunk merging up to a target window.** Packing short adjacent VAD utterances into chunks up to `chunk_size` (for example 15-30s for always-on recording) gives Whisper fuller sentence context and fewer short-clip hallucinations ([whisperx/vads/vad.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/vad.py#L20-L53)).
- **Copy: `condition_on_previous_text=False` by default, with bounded prompt tokens.** Disabling cross-window conditioning prevents Whisper repetition loops during always-on transcription; if you pass a glossary or rolling context to `whisper.cpp`, cap it within the 224-token prompt budget ([whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L62-L65), [whisperx/asr.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/asr.py#L550)).
- **Copy: sorted-array `IntervalTree` for speaker assignment.** If the recorder adds optional post-hoc pyannote diarization for meetings, assigning speakers by maximum time-overlap with `np.searchsorted` (plus optional `fill_nearest`) is simple and fast ([whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L14-L89), [whisperx/diarize.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/diarize.py#L217-L258)).
- **Avoid: loading whole recordings into RAM via `ffmpeg` stdout.** Always-on recording needs streaming ring buffers and incremental disk writes, not full-file buffering ([whisperx/audio.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/audio.py#L61-L65), [issue #1440](https://github.com/m-bain/whisperX/issues/1440)).
- **Avoid: dropping Silero VAD tuning parameters.** Expose Silero's `min_silence_duration_ms`, `min_speech_duration_ms`, and `neg_threshold` (offset) so dictation and always-on modes can use different endpointing latency ([whisperx/vads/silero.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/vads/silero.py#L42-L51), [issue #1187](https://github.com/m-bain/whisperX/issues/1187)).
- **Avoid: running wav2vec2 forced alignment in the dictation path.** Forced alignment adds a second language-specific model, extra VRAM, and per-segment latency that hold-Alt dictation does not need; keep alignment optional for offline meeting post-processing only ([whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L111-L149), [whisperx/alignment.py](https://github.com/m-bain/whisperX/blob/8d8e43bf3698dd1df4b011c0f1a8dd1d468ae365/whisperx/alignment.py#L286-L306)).
