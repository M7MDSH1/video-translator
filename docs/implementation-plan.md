# Local Video Translator

Build a native PySide6 Windows app with local recognition, loopback-only Ollama translation, FFmpeg/libass rendering and JSON projects. User's supplied workflow and requirements are the design specification. Implementation choices: CPU Whisper small and CPU EasyOCR to reserve GPU memory for the installed Gemma 4 12B; adjustable recognition sampling; native video playback with a frame editor for precise crop/cover selection. No dubbing or remote inference.

1. Project model, validation, atomic checkpoints, OCR temporal merging, SRT/ASS and per-line cover rendering. Test timing, escaping, Arabic, approval invalidation and source protection.
2. Cancellable worker process: chunked speech recognition, ROI OCR, local translation, cached steps and render progress. Real-model tests on a short sample video excerpt.
3. Desktop UI: source/language/output choices, video and crop editor, editable cue table, cover editor, styles, project save/open, progress/cancel/resume and preview approval.
4. Real video previews of both modes; inspect Arabic shaping and cover placement, decode outputs, compare preserved audio. Do not approve a preview on the user's behalf or export their full recording.

Constraints: original media read-only; outputs new paths; no network inference; model downloads setup-only; translation uncertainty is heuristic and every machine translation remains flagged until reviewed. OCR boundaries are limited by sampling interval, exposed to the user. Translation and OCR accuracy cannot be guaranteed. Subtitle-track replacement omits original tracks; burned-in replacement requires per-line boxes, never a generic bottom banner. Speech replacement also needs OCR for original boxes.

Files: `videotranslator/project.py` (persistence/validation), `subtitles.py` (merging and render scripts), `engine.py` (workers), `app.py` (desktop UI); `tests/` for logic and integration evidence; `Start Video Translator.bat` launcher.

Verification: unit tests; actual ASR, OCR, translation; application smoke test; FFmpeg decode, audio comparison, visual Arabic review; cancellation/checkpoint resume and preview approval gate. Render interruption restarts the render; completed recognition/translation resumes from saved checkpoints.
