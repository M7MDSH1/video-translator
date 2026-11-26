# Final-subtitle replacement rules

User chose replacements after translation. Preserve recognised source and audio. Support arbitrary literal replacement text (including invented words), English/Arabic and phrases. Default to case-insensitive whole-word matching; longest phrase wins, one pass, no cascading. Rules are per-project, saved with editable exports. No audio dubbing or arbitrary scene-text replacement.

1. Add `replacements.py`: validate settings, compile escaped literal patterns, apply to subtitles, remember pre-rule text so rule changes/removal can restore untouched outputs. Manual corrections become the new baseline. Reviewed cues skipped unless explicitly included. Tests cover boundaries, Arabic, punctuation, multiple rules, resume/idempotence, edits and restoration.
2. Add a native rules dialog reachable in Setup and Review: editable Find/Replace table, enabled/case/word settings, preview of affected cues, Save rules and Apply to current subtitles. Include reviewed is off by default. Applying changes invalidates approval through existing cue fingerprints and marks affected cues unreviewed.
3. Apply rules to each fresh model result before saving and to cached unreviewed translations on resume. Preserve original recognition and reviewed translations. Add project validation and backend/GUI tests.
4. Run the suite and a real-video preview on a QA copy, inspect Arabic rendering, document use. Keep production project edits and footage unchanged.
