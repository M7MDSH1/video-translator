# Local Video Translator — proposed desktop design

Design concept only. The working application is not changed by this proposal.

## Editing workspace

- Keep the video as the main visual focus. At 1440 px and wider, use a 150 px navigation rail, a flexible central player/review area, and a 300 px inspector. At narrower sizes, collapse the navigation rail; let the inspector open as a drawer without covering subtitle text.
- Top workflow: Video → Source → Languages → Review → Preview → Export. Completed stages remain accessible without clearing previous work. Show project name, saved/unsaved state, and local-processing status.
- Place Live edits / Original / Rendered preview above the player. Clearly label a rendered preview as outdated after edits. Display current time, total duration, play/pause, scrubber, volume and fullscreen beneath the player.
- Show a compact subtitle timeline beneath playback controls. Selecting a clip selects its review row; clicking a row seeks to its start. Manual scrubbing should not interrupt text input or change the selected editor unexpectedly.
- Put the review table below the player: start/end time, original text, translation, review status. Offer a Needs review filter, search, add/delete, and explicit mark-reviewed action. Original and translation cells respect their own language direction.

## Persistent inspector beside the player

Text tab: font, numeric size with stepper, bold, color picker plus hex input, line spacing, position controls, alignment, and Khaam Arabic preset. Label global settings “Applies to all subtitles.”

Covers tab: selected cue's individual rectangles, padding, charcoal color, visibility and drag editing. Label these settings “Selected subtitle.” Use handles for each rectangle, a clear selection outline, and undo/redo. Do not introduce a full-width bottom cover.

Keep speaker names and deliberate line breaks editable. Offer a larger editor for long translations. Use connected Arabic words, zero letter spacing, safe room for dots/diacritics, and proper bidirectional handling for punctuation and numbers. Show recognition/translation uncertainty with text labels, not color alone.

## Setup and export

Select video: file chooser, supported-media information, duration and dimensions. Translation source: two cards for spoken dialogue or visible-subtitle OCR, each with a short explanation. OCR reveals crop selection and sampling controls. Source Auto/manual and independent target selection remain visible together.

Model setup belongs in settings, with local availability, download size/source, hardware suitability and explicit download action. Avoid showing model configuration in the everyday review workspace.

Generate a short preview from the selected cue or current position. Watch it, then approve that exact revision. Enable full export only while approval matches current edits. Display output path and new filenames. Subsequent changes invalidate approval, while live editing itself never requires rendering.

For long operations, show the active stage, meaningful progress, elapsed time, cancellation and checkpoint/resume state. Do not present unsupported ETA estimates as precise. Failed work should retain completed checkpoints and offer a useful error with retry/resume.

## Visual and interaction system

- Graphite background #14171D; panel #1D222B; teal accent #57D6B5; white primary text and gray secondary text. Amber indicates review needed; red is reserved for errors or destructive actions.
- Segoe UI for controls; bundled Almarai Bold for default Arabic captions. Use readable labels, restrained borders, an 8 px spacing rhythm and clearly visible keyboard focus.
- Controls remain operable by keyboard. Space toggles playback only when focus is outside text/numeric inputs. Ctrl+S saves; Ctrl+Z/Ctrl+Y undo and redo editing changes. Add tooltips for icon-only buttons.
- Autosave after valid edits, retaining incomplete drafts without overwriting valid values. Show Saved / Saving / Save failed accurately. Confirm destructive cue deletion when recovery is unavailable.

## Implementation scope

Existing features such as local processing, live text/covers, review and preview approval carry over. The timeline, undo/redo, color picker, search/filter, responsive inspector and keyboard refinements are proposed enhancements, not claims about current functionality.

Validate the implemented design with the real video excerpt: edit Arabic text during playback, adjust typography without leaving the player, drag tight covers, review an uncertain cue, render a short preview, and confirm edits disable stale approval. Test a smaller window and Windows display scaling as well as the full desktop layout.
