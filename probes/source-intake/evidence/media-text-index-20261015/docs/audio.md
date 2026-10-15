---
record_type: probe_source_record
schema_note: Isolated prototype record for a media->text->index probe. NOT a LightGravity
  product schema.
id: audio-001
source_ref: fixtures/audio.wav
source_sha256: 580761a61c33ffa68cb5d33bb684cc9a9af1b592dd4070bc4e2d7e91e628d343
media_type: audio/wav (Mandarin, synthetic espeak-ng, 11.875 s, 22050 Hz mono)
extractor_model: qwen3.8-27b (attempted)
extractor_method: /v1/audio/transcriptions AND /v1/chat/completions input_audio
extraction_status: failed
failure_reason: 'No ASR-capable model / audio mmproj installed on server. /v1/audio/transcriptions
  -> 501 ''The current model does not support audio input.''; /v1/chat/completions
  input_audio -> 500 ''audio input is not supported - hint: ... provide the mmproj''.'
generated_at_utc: 2026-10-15T11:09Z
http_status:
  transcriptions: 501
  chat_input_audio: 500
locator:
  page: null
  time_s: 0.000-11.875
  image_ref: null
ground_truth_ref: ground_truth/audio.txt (frozen reference; deliberately NOT embedded
  here to avoid passing ground truth off as extracted text)
---
# Audio transcription — NOT EXTRACTED (failure record)

No transcription text was produced. This is an explicit failure record; the frozen ground-truth transcript is intentionally **not** copied here, so it cannot be mistaken for an extraction result.

- `POST /v1/audio/transcriptions` (multipart, model=qwen3.8-27b) → HTTP 501: `The current model does not support audio input.`
- `POST /v1/chat/completions` with `input_audio` part → HTTP 500: `audio input is not supported - hint: if this is unexpected, you may need to provide the mmproj`

Original media retained at `fixtures/audio.wav`; ground truth retained at `ground_truth/audio.txt`.
