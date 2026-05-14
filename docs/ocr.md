# OCR

The OCR layer is local-only. It exposes an optional Tesseract-backed provider
and keeps the core planner independent of OCR backend details.

Install OCR support on machines that need real OCR:

```bash
uv sync --extra dev --extra ocr
```

The Python package expects a local Tesseract installation to be available on the
host path. No cloud OCR service is used.

## Matching

OCR output is normalized into `ElementCandidate` objects with screenshot-space
bounds and `0..1` confidence. Text matching supports:

- Case-insensitive exact matching.
- Case-insensitive contains matching.
- Simple fuzzy matching for small OCR mistakes.

Candidates below `confidence_threshold` are filtered before selection.

## Trace Output

When `save_ocr_text` is enabled, the engine writes JSON under
`<trace_root>/ocr/<step-id>.json` containing raw OCR blocks and candidates.

## Limitations

OCR reliability depends on fonts, DPI scaling, visual theme, contrast,
anti-aliasing, partial visibility, and screen capture quality. Prefer UIA for
native controls when available, use OCR for visible text that UIA cannot expose,
and use image matching for stable icons or visual-only targets.
