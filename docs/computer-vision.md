# Computer Vision

The computer-vision layer uses local OpenCV template matching for stable visual
targets such as icons, image-only buttons, and deterministic fixture assets.

Install CV support:

```bash
uv sync --extra dev --extra cv
```

## When To Use Image Matching

Prefer UIA for native controls and OCR for visible text. Use image matching when
the target is a stable visual element that is not exposed by UIA and cannot be
reliably identified by text.

## Matching Behavior

- Templates can come from task-relative paths or `examples/assets/`.
- Matches return shared `ElementCandidate` objects with bounds and confidence.
- `region` restricts matching to a screenshot sub-rectangle.
- Grayscale matching is enabled by default to reduce theme sensitivity.
- Detection overlays are saved under `<trace_root>/overlays/`.
- Detection reports are saved under `<trace_root>/cv/`.

Scale-tolerant matching is recorded as disabled in v1 reports and remains a
later enhancement. Tasks should use templates captured at the same DPI and zoom
as the target environment.
