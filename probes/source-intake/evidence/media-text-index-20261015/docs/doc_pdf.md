---
record_type: probe_source_record
schema_note: Isolated prototype record for a media->text->index probe. NOT a LightGravity
  product schema.
id: doc-pdf-001
source_ref: fixtures/scanned_page-1.png
source_sha256: 04c3c4aa7019c6b94112d246b14d9f3c7f3483b7a93b86006ffe3bdba4838afd
media_type: image/png (raster page of fixtures/scanned.pdf)
extractor_model: qwen3.8-27b
extractor_method: /v1/chat/completions image_url
extraction_status: success
generated_at_utc: '2026-10-15T11:08:49Z'
http_status: 200
finish_reason: stop
usage:
  completion_tokens: 83
  prompt_tokens: 562
  total_tokens: 645
  prompt_tokens_details:
    cached_tokens: 0
locator:
  page: 1
  time_s: null
  image_ref: fixtures/scanned_page-1.png
ground_truth_ref: ground_truth/doc_pdf.txt
---
# Extracted text (OCR) — doc_pdf

电子发票
发票号码：25337000000098765432
开票日期：2026年10月14日
价税合计：人民币 1,234.56 元
项目：文本索引服务
校验码：4821 9037 5566
