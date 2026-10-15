---
record_type: probe_source_record
schema_note: Isolated prototype record for a media->text->index probe. NOT a LightGravity
  product schema.
id: doc-image-001
source_ref: fixtures/screenshot.png
source_sha256: 74025921f66ef88a4105020848e6941cd6886512e7b44a69da29603d3194308d
media_type: image/png
extractor_model: qwen3.8-27b
extractor_method: /v1/chat/completions image_url
extraction_status: success
generated_at_utc: '2026-10-15T11:08:25Z'
http_status: 200
finish_reason: stop
usage:
  completion_tokens: 65
  prompt_tokens: 562
  total_tokens: 627
  prompt_tokens_details:
    cached_tokens: 0
locator:
  page: null
  time_s: null
  image_ref: fixtures/screenshot.png
ground_truth_ref: ground_truth/doc_image.txt
---
# Extracted text (OCR) — doc_image

收款通知
编号：LG-2026-1015-007
日期：2026年10月15日
金额：人民币 8,765.42 元
事由：资料整理服务费
备注：请在三个工作日内确认。
