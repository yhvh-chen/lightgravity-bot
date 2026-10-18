# Optional English ASR runtime (operator provisioning)

This directory implements the 1.20 English audio machine-transcription capability
from `docs/08-interface-contract.md` §21. It is **default off**. The default
application does not install or import `torch`/`transformers`; without the
optional runtime and explicit local model files the capability reports `false`
and audio remains available as an original/direct-audio embedding source.

## Public assembly seams (integration owner 162)

```python
from lightgravity.asr import (
    build_english_asr_service,
    build_english_asr_router,
    english_asr_capability,
)

# connection_service is the existing ConnectionService; its repository is the
# controlled data root owner.
service = build_english_asr_service(connection_service.repository)
connection_service.configure_english_asr(service)   # GET /settings view
source_service.configure_english_asr(service)       # intake text branch
app.include_router(
    build_english_asr_router(
        service,
        require_admin=optional_admin_guard,
        safe_origin=existing_safe_origin_check,
    ),
    prefix=API_PREFIX,
)
# health: english_asr_capability(service)["available"] is PROCESSING availability,
# not permission to configure. The GET /settings.english_asr view is present
# even when processing is false, so an admin can configure it.
```

`GET /settings` exposes `english_asr.revision`/`content_hash` from the
capability's own canonical `settings/ENGLISH_ASR.md` document. The first create
uses `expected_revision: 0`; later writes use that view revision. The PUT returns
`{revision, content_hash, english_asr}`. Model paths are write-only and never
returned by the view. Saving validates files/hashes and performs **zero**
inference.

## Install the optional dependencies

Use an isolated Python 3.12 environment (do not install into the global
environment):

```bash
uv sync --extra english-asr
# or, for an explicit CPU-only PyTorch wheel:
uv pip install torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu
uv sync --extra english-asr --no-install-package torch
```

Pinned Python/model dependencies: `numpy==2.5.4`, `safetensors==0.8.0`,
`transformers==5.19.0`, `torch==2.14.0` (CPU-compatible). The verified prototype
runtime additionally used `torch==2.14.0+cpu` with Python 3.12.13.

`ffmpeg` is used only for non-WAV uploads when present on the local `PATH`; WAV
is decoded by the Python standard library. There is no runtime download,
installation, training or remote ASR.

## Prepare the pinned local assets

The operator provisions these public files outside the repository and passes
their absolute directories in the protected settings PUT:

Encoder directory (`model_dir`) — `google/embeddinggemma-2`, revision
`914f7f89142e33e77833254d9c9b90c3cef7303b`, Apache-2.0, gated=false:

| file | SHA-256 |
|---|---|
| `model.safetensors` | `197a32965d4b1105faf060417baa899e193fb73cd401f42ec9295234d5553d79` |
| `config.json` | `b8f1e9931b57fbc054acdb445c41765d55b0074c58d145fa82839941ad1b5bb3` |
| `preprocessor_config.json` | `ea2ae257e901064abdd98dceb19f2b0da06af600bed15e0f99f5c85c37ee9d78` |

Reader directory (`reader_dir`) — `mlboydaisuke/EmbeddingGemma-2-Transcribe-Reader`
v2, revision `de224fd8fa4ed4519fdddd9aa4154432d46a1bd3`, Apache-2.0:

| file | SHA-256 |
|---|---|
| `reader.pt` | `d605f6fba8687497be6b5fd717ea6c51beaee5d5f69c30a64225da96ebe0d8c2` |
| `reader_config.json` | `3aede371f7fc1b69bd948a3fce6f861e44eedb237d7b6dce360063ea007a90ed` |
| `word_table.npy` | `b2d0b13cc70c492f1444b8a42deab437d25254eac47d752d777d27b65377faa8` |
| `vocab.txt` | `bb3b3c70379082333e1bbd90d07ca69fe5c0096bd1c3b2b3f83edd65f1062a68` |

The LG-159 handoff preserved these assets under
`/var/tmp/lg159-english-asr/hf/models/{google__embeddinggemma-2,eg2-reader-v2}`
and its CPU venv under `/var/tmp/lg159-english-asr/venv` **for operator reuse
only**. Those paths are not product defaults and are never hardcoded in the
application. Copy/provision them into an operator-controlled location and use
that absolute path in the settings PUT.

Licences/attribution: see `NOTICE` and `LICENSE.reader` in this directory and the
upstream reader `SHA256SUMS`. The reader NOTICE requires keeping its LICENSE and
NOTICE with redistributed reader files; the EmbeddingGemma 2 Gemma Prohibited
Use Policy also applies to encoder deployments.

## Settings PUT example (admin/protected)

```json
{
  "expected_revision": 0,
  "enabled": true,
  "runtime": "inprocess",
  "model_dir": "<absolute encoder directory>",
  "reader_dir": "<absolute reader directory>",
  "device": "cpu",
  "threads": 4,
  "timeout_seconds": 180,
  "max_audio_seconds": 30,
  "max_audio_bytes": 10000000
}
```

Omit `model_dir`/`reader_dir` to retain stored paths. Explicit `null`/empty is a
422 and never clears a path. A supplied path is always hash-validated. Disabling
may omit now-missing paths (safe disable) but the view then reports
`available=false` with `model_missing`/`model_hash_mismatch`.

## Runtime behaviour and limits

- One lazily loaded model instance per process, `lowmem` audio tower only; the
  vision/text tower is never instantiated and no full+lowmem pair is loaded.
- Inference serialized (max concurrency 1), no warm-up, no automatic retry.
- `max_audio_seconds` 30, `max_audio_bytes` 10,000,000, timeout 180 s.
- Measured prototype RSS ~2.0-2.3 GB. Memory/runtime failure is reported as a
  failed text branch (`resource_exhausted`/`asr_unavailable`); the intake worker
  stays alive and the original/direct-audio branches are preserved.
- Timeout/cancel are terminal only after the real CPU call returns/stops.
  Otherwise the job is `recovery_required`, cancellation stays unconfirmed, the
  receipt remains `text.status=extracting`/`asr_stop_unconfirmed`, late output is
  discarded and nothing is replayed.
- Output is lower-case English words with punctuation removed; `timestamps` is
  always `null` (the released reader/CTC has no alignment output).
- The transcript is a machine derivative at
  `derivative/machine.v<source_version>.md`; the existing content/download JSON
  envelope is preserved and the human `formal` version is never touched.

## Smoke check (real assets, one bounded call)

Use the milestone inference ledger before any real encoder/Reader attempt. A
direct product-runtime smoke (no probe import) can be run with the operator
runtime environment:

```bash
PYTHONPATH=backend /path/to/operator-venv/bin/python - <<'PY'
from pathlib import Path
from lightgravity.asr.config import EnglishAsrConfig
from lightgravity.asr.runtime import Eg2ReaderRuntime

cfg = EnglishAsrConfig(
    enabled=True,
    model_dir="<absolute encoder directory>",
    reader_dir="<absolute reader directory>",
    threads=4,
)
runtime = Eg2ReaderRuntime(cfg)
result = runtime.transcribe(Path("<audio.wav>").read_bytes(), filename="<audio.wav>")
print(result.text)
PY
```

This calls the real model. Reserve/complete the call in the LG-159 ledger with
the root helper **before** running it; do not consume the independent-QA reserve
for development.
