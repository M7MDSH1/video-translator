# Local Video Translator for Windows

Translates a video's spoken dialogue (Whisper) or its burned-in subtitles (OCR) into another language and adds the translation as subtitles, optionally covering the original ones. Everything runs on your PC: recognition, translation (through a local Ollama model) and rendering. No video or text is uploaded.

## Install

### System requirements

**Always needed:** Windows 10 or 11 (64-bit), about 20 GB of free disk space, and an internet connection for setup only.

| | Minimum | Recommended |
|---|---|---|
| **RAM** | 16 GB | 32 GB if the translation model runs on the CPU |
| **NVIDIA GPU** | RTX 20-series or newer with 8 GB VRAM (GTX 16-series may work); driver supporting CUDA 12.8 | 12–16 GB VRAM, for example RTX 3060 12 GB, RTX 4070, RTX 5070 Ti |
| **Older NVIDIA (GTX 10-series and earlier)** | Speech and subtitle reading run on the CPU; the installed CUDA 12.8 PyTorch no longer supports these cards | — |
| **AMD or Intel GPU** | Speech and subtitle reading run on the CPU (slow on long videos). Ollama can still use supported AMD cards for translation | — |
| **No GPU** | Works when installed with `-Cpu`; a two-hour video can take many hours | — |

With 12–16 GB of VRAM the default `gemma4:12b` translation model (about 8 GB) and Whisper or OCR fit together. With 8 GB, choose a smaller model such as `qwen3.5:9b` in Setup. In **Auto** mode the app falls back to the CPU if the GPU cannot start.

Tested on: Intel i7-13700KF, 16 GB RAM, NVIDIA RTX 5070 Ti 16 GB, Windows 11. The other rows are estimates from the requirements of PyTorch, faster-whisper and Ollama, not tested hardware.

1. Download the app: on its GitHub page choose **Code → Download ZIP** and unzip it anywhere (or `git clone https://github.com/M7MDSH1/video-translator.git`).

2. Double-click **Install.bat** in the app's folder and wait. Nothing needs to be installed beforehand.

   The installer adds whatever is missing with winget: Python 3.12, FFmpeg, and Ollama (the program that runs the translation model on your PC). It then creates a private Python environment in `.venv`, installs the packages (PyTorch alone is about 3 GB), downloads the offline Whisper Turbo and EasyOCR models into `models\`, starts Ollama, downloads the `gemma4:12b` translation model (about 8 GB), and creates a **Video Translator** shortcut. Expect roughly 15 GB of downloads in total.

   Options go after the file name in a terminal, for example `.\Install.bat -Cpu`:

   | Option | Use it when |
   |---|---|
   | `-Cpu` | there is no NVIDIA GPU (installs the smaller CPU-only PyTorch) |
   | `-Model qwen3.5:9b` | you want a different Ollama model; any installed one can also be picked in the app later |
   | `-SkipModels` | you will download models yourself later (`.venv\Scripts\python setup_models.py`) |
   | `-CheckOnly` | you only want a report of what is installed or missing |
   | `-OllamaOnly` | you only want to install or start Ollama and download the translation model |

3. Start **Video Translator.lnk** (or **Start Video Translator.bat**). If Ollama is not running or the chosen model is not installed, Setup shows a **Set up translation (Ollama)…** button that installs, starts and downloads what is missing.

If FFmpeg was just installed, open a new terminal or sign out and back in first so Windows finds it. You can also place `ffmpeg.exe` and `ffprobe.exe` (a build with libass, such as the gyan.dev full build) in `runtime\ffmpeg\bin`; the app uses that folder first.

**Check this PC:** `.venv\Scripts\python tools\self_check.py` reports FFmpeg, Python packages, models, the NVIDIA encoder, free graphics memory and Ollama. It changes nothing.

**Tests:** `.venv\Scripts\python -m unittest discover -s tests`. The same tests run on GitHub for every push (`.github/workflows/tests.yml`). A few interface tests need a local sample project (`projects\test-ocr`) that is not in the repository; they are reported as skipped.

Projects are created in `projects\` and finished videos in `exports\`; both stay on your PC and are excluded from git.

## Desktop workspace

The approved native design has four screens: **Setup → Review → Preview → Export**. Review keeps the video above a resizable bilingual table, with independently scrolling **Text style** and **Text & timing** tabs beside it. The same player moves between screens, retaining its video sink and playback state. All recognition and rendering continue locally.

Setup lists real installed Ollama models and reports offline/missing-model states. Speech mode has a local model and audio-track selector; OCR mode has alphabet, sampling interval and area selection. Device and time range are under Advanced. Original subtitle type/track and output appearance are in Export and apply to both translation modes. Dialogue-only filtering still uses **Keep dialogue matching selected layout** in Review; it needs an actual recognised dialogue cue, not a guessed universal filter.

**Resume saved processing** reuses completed recognition and translation batches. **Translate again** retains reviewed translations and recognised originals, and deliberately refreshes unreviewed translations. Changed recognition settings require **Recognise again…**, which warns that every cue is replaced and saves a backup before proceeding. **Start over…** also backs up before clearing checkpoints and cues. Keeping reviewed cues by timestamp during re-recognition remains deferred. Settings changes persist across reopen and block preview/export until processed.

The export screen shows the next readable folder name and the files included. Subtitle-only output lists no video. The current rendered preview must be approved; editing text, style, appearance, or manually changing the preview range invalidates that approval.

## Workflow

1. **Start screen.** The app opens on a start screen. For a new project, choose what to make (**Translated video** or **YouTube captions**), then **Choose video…** or drop a video file anywhere on the window. A project is created in `projects`; the video is referenced, never overwritten. To continue an earlier translation, pick it under **Open a project** or use **Browse for a project…**. Inside a project, **Home** saves it and returns to the start screen.
2. **Choose translation source:** spoken dialogue (Whisper), or visible subtitles (EasyOCR). OCR supplies the actual translation source in OCR mode; it never substitutes the audio transcript.
3. **Choose source and target languages independently.** Source Auto detects the spoken language or lets the translation model identify recognized subtitle text. For speech, the first 30-second chunk with words detected at 80% confidence or more fixes the language for the rest of the run (music/noise chunks cannot switch it); for videos that change language, process each part with an explicit source language. For OCR, also choose the appropriate alphabet. Auto OCR covers Arabic and Latin; other alphabets must be selected explicitly and downloaded with the adjacent button.
4. **Select subtitle area** on the current frame for OCR. Include complete lines and speaker names, but exclude HUD/menu text. Text touching the selection boundary is discarded. Choose a processing range; test short ranges before a long recording. Default OCR sampling is 0.25 seconds. Use 0.04–0.1 seconds for brief subtitles at greater processing cost.
5. **Process / Resume.** Recognition and translation checkpoints are saved automatically. Ollama must be running with the selected model installed (`gemma4:12b` by default). Internet is not needed after model setup. Cloud-backed Ollama models are rejected before transcript text is sent.
6. **Review with live edits.** Select a cue, then open **Text & timing** on the right and type into the translation field. Translation, line breaks, start/end times, font, size, color, position, and padding update instantly over the original video; no encoding is needed. Turn on **Drag covers in video**: drag inside a rectangle to move it, its bottom-right corner to resize it, or empty space to add a rectangle. Pixel coordinates are editable below the text. Valid inline edits save automatically after a short pause. **Original video** hides overlays; **Live edits** restores them. Double-clicking a cue still opens the full original/translation editor; draft changes appear live and Cancel restores the saved edit. After fixing original recognition errors, use **Translate again** in Setup. Translation flags are heuristic, not calibrated probabilities. Every machine translation starts unreviewed. A manual cover edit replaces automatic changing rectangles for that cue; split long/changing cues if needed. Timing edits preserve and clip detected cover spans.
7. **Choose appearance** independently: add translation, replace originals, subtitle files only, or YouTube captions (see below). Add defaults above the original subtitles. Replacement of burned-in subtitles uses only detected per-line charcoal rectangles. Speech-mode replacement needs **Detect covers from video**, or manually drawn rectangles. Separate subtitle tracks are omitted in replacement. Add mode renders the selected original text track together with the translation. Font, bold, color, X/Y position, and cover padding are adjustable. When replacing burned-in originals, translation lines fit inside their corresponding cover rectangles. Small OCR edge changes are stabilized while genuine position/text-area changes remain timed. Nested punctuation detections do not become extra caption lines. Each line is centred using its rendered glyph bounds, including Arabic dots and descenders, and shrinks only as needed to fit. Fonts without Arabic glyphs use Almarai for Arabic replacement text. Very small fits need review; adjust wording or covers if needed. X/Y applies to subtitles without cover-based placement. Covers remain separate, tight rectangles rather than a full-width bar.
8. **Generate preview**, watch it, then **Approve this preview** when ready to export. Editing opens the live view automatically. **Rendered preview** below the player shows the last encoded preview; selecting a cue inside it keeps that view. Live editing uses Qt's Arabic shaping and font layout, while export uses libass: exact font metrics, wrapping, and original text-track styling can differ. A rendered preview remains the final output check, but is not needed after each edit. Edits invalidate export approval. Approval authorizes the current edit; it is not a claim that every cue in a long video was reviewed.
9. **Export.** Full exports appear in `D:\VideoTranslation\exports` (the app's `exports` directory), each in a folder named `Video name - Target language`. The MKV video, UTF-8 SRT, ASS, and editable JSON project share that readable name. Repeated exports get separate folders ending in `(2)`, `(3)`, etc.; earlier files are never overwritten. **Open outputs** opens the latest completed export's folder. Preview clips remain in the project's `exports` directory. MKV preserves original audio streams by copying their compressed packets; voices are not dubbed or replaced. Preview uses MP4 for compatible audio and MKV otherwise. Subtitle-only mode produces a named folder with sidecars and project without a new video.

## YouTube captions

Choose **YouTube captions** on the start screen (or as the appearance in Export) to get a captions file instead of a new video. Viewers of your YouTube video can then turn the translation on or off with the CC button, like any other subtitles.

- Export writes `Video name - Target language.<code>.srt` (for example `... - Arabic.ar.srt`) and the editable project. No video is rendered, so a rendered preview is optional; empty translations are still refused.
- Speaker names shown above the dialogue (game subtitles) are left out of the captions file. A name is removed only when the project has a dialogue layout that places it at the speaker position and the translated line is exactly that name; any other first line is kept.
- Upload it in YouTube Studio: **Subtitles** › your video › **Add language** › **Add** under subtitles › **Upload file** › **With timing**, then publish. YouTube's menus can change; the Export page shows these steps too.
- Timing is the same readable timing as Review: short lines stay up long enough to read. Text style settings do not apply; YouTube uses its own caption style. Arabic, Persian, Urdu and Hebrew lines start with an invisible right-to-left mark so lines beginning with "..." or a number stay right-aligned. How YouTube draws them has not been tested from this app.
- Best with **Spoken dialogue**. If the video has subtitles burned into the picture, they stay visible and YouTube's captions appear on top of them.

## Translate from your phone

The Android app in `android/` sends a video to this PC over Wi-Fi, the PC translates it, and the phone downloads the result. The phone does none of the AI work, so the quality is the same as on the desktop.

1. On the PC, open Video Translator and choose **Translate from your phone...** on the start screen. It shows a PC address and a six-digit code. If Windows asks, allow access on private networks.
2. Install the app on the phone: open [VideoTranslator.apk](https://github.com/M7MDSH1/video-translator/releases/download/android-latest/VideoTranslator.apk) on the phone and allow the install. (To build it yourself, run `gradlew assembleDebug` in `android/`; that needs the Android SDK and JDK 21.)
3. In the app, type the address and the code once. Choose a video, or share one to the app from the gallery, say whether the dialogue is spoken or shown on screen, pick the video's language, the language to translate to and the translation model, and press **Translate**.
4. The translated video is saved on the phone in `Movies/Video Translator`.

What to expect:

- **Same Wi-Fi only.** The phone and the PC must be on the same network, and the PC must stay on with Video Translator open.
- **No review step.** The video is translated and exported without anyone checking the lines. The project is kept on the PC in `projects/phone-<date>`, so you can open it there, fix lines, and export again.
- **Phone-sized result.** The export is a 720p MP4 of at most about 1.4 GB per hour, not the full-size file the desktop makes.
- **Subtitles are added, not replaced.** Replacing burned-in subtitles needs a region set by hand, so it is desktop only.
- **On-screen subtitles need their language.** Left on Auto they are read as English. For a language other than English or Arabic, the PC downloads that language's text reader once.
- **Plain HTTP on your own network.** The six-digit code keeps other devices on the Wi-Fi from using the PC, but the video is not encrypted in transit. Do not use it on public Wi-Fi.

## Updates

When a newer version is on GitHub, the desktop app shows a popup and an **Update available** button at the top right. **Update now** closes the app, installs the new version and opens it again; your projects, exports and models are not touched. **Later** keeps the button. The phone app does the same with its own popup and an **Update** button; it downloads the new APK in the browser.

The check is one anonymous request to GitHub each time an app starts. It names only the version you have. Nothing about you or your videos is sent, and without internet the apps just skip it.

## Review shortcuts, faster export, and model comparison

- **Review keys** (while the video or the subtitle table has focus): **Space** play/pause, **Enter** edit the selected line, **Ctrl+Enter** mark it reviewed and go to the next line that needs review. **Ctrl+Z** undoes and **Ctrl+Y** redoes subtitle edits (text, timing, covers, position and size of one line, add, delete, mark reviewed), up to 50 steps. Undo history starts again after a processing job. Text-style settings for the whole video are not part of undo.
- **Export and preview encode on the NVIDIA card** (`h264_nvenc`) when one is available: about 3× faster than before on the tested PC, with files about 40 % larger at the same quality. If the card's encoder cannot start, the processor encoder (`libx264`) is used as before. A 10-bit source is written as 8-bit by the NVIDIA path.
- **Memory.** The translation model is unloaded from graphics memory as soon as translation ends. If Ollama cannot load a model because another app holds the memory, the error message says so.
- **Compare models…** in Setup scores the installed Ollama models on this project against a subtitle file you corrected by hand (the same check as `tools\compare_models.py`). The project is not changed.

## Reopening, cancellation, and recovery

Use the start screen to reopen a recent project, or **Browse for a project…** to open any `project.json` or an exported `.project.json`. Keep the referenced original video at its path. Changes are saved with atomic file replacement. The app saves on normal close as well.

Cancel requests cooperative shutdown, then terminates its worker tree after five seconds if a native model call is still blocked. Speech checkpoints cover 30-second intervals decoded with three seconds of context on both sides. Timed words are reconciled at the joins, then grouped into cues of up to six seconds / 84 characters (an indivisible overlong word can exceed those limits). Fast speech and fast translations are flagged for review. OCR reads frames sequentially through FFmpeg and saves every eight samples. Translations save atomically per validated batch of up to 12 cues. Resume reuses completed work; interrupted chunks are repeated. Interrupted rendering starts again, leaving an explicitly named `.partial` file. Changing recognition settings creates a backup before replacing existing cues. OCR has its own cache identity so changed crops, languages, sampling, tracks, ranges, or source files cannot silently reuse stale detections.

## Installed models and hardware

- Intel i7-13700KF, approximately 16 GB RAM; NVIDIA RTX 5070 Ti, 16 GB VRAM.
- Whisper Turbo: `mobiuslabsgmbh/faster-whisper-large-v3-turbo` from Hugging Face, approximately 1.6 GB weights; default speech model. Whisper small (~484 MB) remains available. Whisper large-v3 (~3 GB, `Systran/faster-whisper-large-v3`) is optional: slower, more accurate for Chinese, Japanese and Arabic speech.
- EasyOCR official GitHub weights: CRAFT detector (~83 MB), English recognition (~15 MB), Arabic recognition (~215 MB).
- Existing local `gemma4:12b` Ollama model, approximately 8 GB on disk; no translation-model download was required.
- Recognition device: **Auto (prefer GPU)**, **GPU (CUDA)**, or **CPU**. Whisper uses CTranslate2 CUDA float16; OCR uses CUDA PyTorch. Both ran on the RTX 5070 Ti. PyTorch 2.10.0+cu128 and torchvision 0.25.0+cu128 are installed in this app only (official download approximately 2.88 GB). Models run in stages; CPU remains available. In Auto, a GPU that fails to initialize (Whisper runs a one-second warm-up to surface missing CUDA libraries) falls back to CPU with a status message; explicit GPU mode reports the error instead. Auto OCR also retries the same frame on CPU if recognition itself fails on CUDA, without saving that frame twice. GPU initialization can outweigh its benefit on short ranges—do not assume every clip is faster.
- Qt/PySide6 provides Windows playback and text editing. FFmpeg/libass/HarfBuzz/FriBidi renders logical-order Unicode Arabic with connected letters and automatic RTL paragraph direction (`Encoding=-1`). SRT appearance depends on the player; ASS or burned video preserves the chosen style.

Setup downloads come from PyPI, official PyTorch, Hugging Face, and EasyOCR GitHub releases. `setup_models.py` is the only model-download entry point. Runtime recognition uses local-only weights. Translation requests go only to `127.0.0.1:11434`, with environment proxies and redirects disabled and a local-model preflight check. No telemetry is enabled by this app. External software such as Ollama can have its own update settings.

## Known limitations

### Arabic caption style

New projects use the Khaam Arabic preset. The **LIVE TEXT STYLE** panel beside the video keeps font, size, bold, color, spacing, position, and cover padding visible while watching. Existing projects can apply the preset with **Apply Khaam Arabic style**: bundled Almarai Bold, white text, adjustable line height, full-word wrapping, Arabic punctuation, and protected left-to-right dates/ranges. Font files and their OFL license are under `assets/fonts/Almarai` (about 630 KB of fonts, downloaded from Google Fonts). Nothing is installed system-wide. Live edits update immediately, including covers; rendering is only needed for the final layout check and export approval. Raw editable text stays intact; punctuation and joining helpers apply at display/export time. This improves typography, not the accuracy of model translations.

- Recognition and translation are fallible. Review is required.
- OCR boundaries are sampled, not guaranteed frame-exact. Very short subtitles can be missed. Moving/fading text and HUD elements inside the chosen area require inspection. Cover padding and rectangle editing compensate for punctuation missed by the OCR detector.
- Speech recognition is not speaker diarization or audio separation; overlapping commentary/game dialogue and speaker changes may need splitting or retiming. No dubbing is performed.
- Embedded text and image subtitle tracks (PGS, DVD, DVB) are tested for OCR, additive rendering and replacement. Bitmap OCR/additive previews decode from the beginning before trimming so an already-visible subtitle is retained; resuming late in a long bitmap-track video can therefore take extra decoding time. The live player depends on Qt support for displaying native bitmap subtitles; use the rendered preview to verify originals in additive mode.
- Full exports re-encode video as H.264. HDR color preservation, Dolby Vision, and archival/lossless video export are not implemented. Original audio packets are copied; the original file remains unchanged.
- Projects use absolute original-video paths. This is a local folder application, not a signed Windows installer. It includes local FFmpeg binaries and needs the local Ollama service.

## Other notes

For games with speaker-labelled subtitles, select a representative cue and choose **Keep dialogue matching selected layout**. This locks OCR to the centered speaker/dialogue geometry, tolerates small whole-block vertical shifts, and includes a second dialogue line. Excluded cues remain in `excluded_cues`, and raw OCR remains saved. This is a project-specific filter, not universal semantic understanding: unlabelled dialogue or a different subtitle layout needs a different selection/profile. The full sample project excludes menu, map, death-screen, and written-inscription detections.

**Minimum size**, next to the video, prevents tiny replacement text. With a minimum such as 26 px, only each individual line's charcoal background grows as needed around its original position; it never creates a full-width bottom band. Set 1 for the previous strict source-box fitting behavior. Live playback and export share these rectangles.

Translation uses batches with cue IDs, eight preceding cues of context, and saved terminology. **Names / terminology** lets you correct recurring names. Reviewed translations are preserved; malformed or incomplete batches are rejected before saving and retried in halves down to single cues, since the deterministic model would repeat the same reply on Resume. Only a single cue that still fails stops translation, naming that cue. This improves consistency but does not guarantee translation accuracy.

Run checks from this folder:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests
.\.venv\Scripts\python.exe tests\gui_smoke.py
```

The real-model cancellation and track integration checks are in `tests/cancel_resume_real.py` and `tests/integration_tracks.py`. They create their own test projects. `tests/review_excerpt.py` is a one-time test-review script and should not be rerun over your finished edits.

To rebuild dependencies, use Python 3.12, create `.venv`, install `requirements-gpu.txt` for the tested CUDA environment (or CPU PyTorch/torchvision from `https://download.pytorch.org/whl/cpu`), then install `requirements.txt`. Exact tested versions are in `requirements-lock.txt`. Run `setup_models.py --asr turbo` for the default model, `setup_models.py --asr small` for the smaller option, and `setup_models.py --asr large-v3` for the most accurate one. Additional OCR weights: `setup_models.py --ocr ja` (Japanese example).

The app icon is an editable local vector in `assets/video-translator.svg`. `tools/build_app_icon.py` rebuilds the PNG and Windows ICO (16–256 px). The native window, app header and Windows shortcut use the same mark. Restart an already-open window to load the updated icon.

## Word and phrase replacements

Open **Word & phrase replacements** in Setup or Review. Enter literal Find / Replace with pairs, such as `football` → `soccer`, or an Arabic phrase → any replacement text (including invented words). Rules search the **final subtitle language**, not the recognised source or audio. Use speech recognition for videos without subtitles, or OCR for visible subtitles, then the same rules apply after translation.

Whole-word matching and case-insensitive matching are the defaults. Arabic whole-word matching accepts optional attached و / ف, ب / ك / ل, and ال, including بال / كال / لل and conjunction combinations. Prefixes are preserved when replacing; matched vowel marks are consumed (including marks inside the word). For example, وكرة becomes وزومبا, بالكرة becomes بالزومبا, and كرةً becomes زومبا. This is literal prefix matching, not morphological analysis: an ambiguous word such as فكرة can match ف + كرة, so inspect Before/After before applying. Phrases can match across subtitle line breaks within one cue; they do not span different timed cues. The longest overlapping phrase wins. Replacements happen in one pass: new text is not fed into another rule. Turn off Whole words to allow substrings, or turn on Match case for exact case.

**Save rules** stores rules for future translation/resume runs and leaves existing subtitles untouched. **Apply to current subtitles** previews and updates existing text immediately without an AI call. Reviewed lines are excluded unless explicitly included; changed lines become unreviewed and invalidate rendered-preview approval. The original transcript, timing, and audio stay unchanged. Longer replacements can affect wrapping and reading speed, so check a new rendered preview.

Disable/remove rules and Apply to clear their warning and restore pre-rule text where the generated replacement has not been manually edited. Manual corrections become the new baseline. Rules and that baseline are saved in the editable project. Leave Replace with blank to delete a word/phrase, including an attached Arabic prefix. If the whole caption is deleted, it is omitted from SRT/ASS text while its original burned-in subtitle remains covered in replacement mode. Manual empty translations still need correction before rendering. This changes subtitle text, not spoken voices or unrelated signs in the picture.

## Entire video and time display

Setup shows the full media duration as minutes:seconds (or hours:minutes:seconds), with an Entire video checkbox. New projects default to the exact full duration, without rounding away the last fraction of a second. Uncheck it to reveal custom range controls. Existing custom ranges are shown explicitly and preserved until you choose Entire video. Playback shows current time / total time; a rendered preview has its own short duration. The last subtitle timestamp is not the video length: silence can follow the last recognised speech.

## Drag subtitle placement

In Review, Text style has **Drag / resize subtitle in video** (enabled by default) and **Move: All subtitles / Only selected subtitle**. In Live edits, grab the visible translated caption and drag it; playback pauses when the drag starts. All lines move together, remain inside the video, and the position saves automatically. Reset dragged position clears offsets for the selected scope. Moving all subtitles applies the same relative shift to each caption; edge clamping keeps each one inside the frame.

For burned-in replacement, original-text cover rectangles stay where they were detected. The translation and its own background move together, so the old text stays hidden. Cover-edit mode is a separate, mutually exclusive tool. The same placement code is used by the live overlay and ASS/video export. SRT is plain text and cannot store visual positioning; use ASS or the rendered video. Position changes invalidate preview approval; generate and approve a new preview before exporting.

Verified with 141 tests / 4 subtests, including mouse dragging at letterboxed sizes, per-cue/global placement, edge clamping, unchanged original covers, saved offsets and ASS output.

### Resize subtitles with corner handles

In Review → Live edits, drag any teal corner outward to enlarge the caption or inward to shrink it. All lines scale together around the caption centre, with no number entry. The All subtitles / Only selected subtitle scope controls both moving and resizing. Reset dragged size restores the base sizing for that scope. The text and its backing boxes resize together; original burned-in masks remain fixed. Editing handles never appear in rendered output.

Size is saved in the project and used in ASS/video output; SRT cannot store font size. Resizing invalidates preview approval. Verified with 146 tests and 4 subtests.
