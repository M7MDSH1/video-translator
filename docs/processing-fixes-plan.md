# Processing corrections

Pause visual redesign. Preserve original footage, reviewed projects and existing exports. Perform new model/integration runs in separate test projects; never bypass the user's export approval.

1. Use timed words to form bounded speech cues. Decode overlapping windows; commit only words in the central ownership interval, retaining absolute timings across resumable chunks. Flag inherently excessive reading speed rather than hiding words.
2. Replace repeated video seeking with one sequential FFmpeg stream sampled at the requested rate. Support rendering bitmap subtitle streams for OCR and additive output. Keep cancellation and checkpoint behavior.
3. Test CUDA OCR and CTranslate2 separately on the installed RTX 5070 Ti. Add explicit Auto/GPU/CPU selection, useful errors, and no silent performance claims. Record package versions/downloads.
4. Translate bounded batches with stable cue IDs, validated complete responses, preceding context and project terminology. Commit only complete validated batches; preserve reviewed edits on resume.
5. Align setup default with Turbo; report absent audio clearly; bundle FFmpeg; organize generated artifacts without breaking project paths; initialize local Git with generated/private files ignored.
6. Validate unit cases, real excerpt recognition/translation, chunk seams, cancellation/resume, text and bitmap subtitle modes, Arabic output and GUI playback. Record remaining limits and timing measurements.
