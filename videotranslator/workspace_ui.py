"""Native Qt implementation of the approved four-step desktop workspace."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QPixmap
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QTabWidget, QSplitter, QTableWidget, QHeaderView, QGroupBox,
    QPlainTextEdit, QCheckBox, QSlider, QProgressBar, QScrollArea, QComboBox,
    QSpinBox, QSizePolicy)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from .live_video import LiveVideoWidget
from .project import LANGUAGES,ROOT
from . import motion
# Output types: project value and the name shown in Export. Order matches the Export list.
APPEARANCES=[('add','Add translation; keep originals'),('replace','Replace original subtitles'),('file','Subtitle files only'),
             ('youtube','YouTube captions (file you upload)')]

STYLE = '''
QWidget { background:#151B24; color:#EDF2FA; font-family:"Segoe UI"; font-size:13px; }
QLabel { background:transparent; }
QLabel[role="title"] { font-size:25px; font-weight:700; }
QLabel[role="muted"] { color:#B0BDCE; }
QGroupBox { background:#1D2632; border:1px solid #354153; border-radius:8px; margin-top:16px; padding:16px 12px 12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 5px; }
QLineEdit,QPlainTextEdit,QTableWidget,QDoubleSpinBox,QSpinBox,QComboBox { background:#121923; border:1px solid #354153; border-radius:4px; padding:6px; selection-background-color:#326D65; }
QPushButton { background:#253241; border:1px solid #354153; border-radius:6px; padding:9px 13px; }
QPushButton:focus,QComboBox:focus,QLineEdit:focus,QPlainTextEdit:focus { border:2px solid #57D6B5; }
QPushButton[primary="true"] { background:#57D6B5; color:#121923; font-weight:700; }
.QPushButton:hover { background:#334757; border-color:#57D6B5; }
QPushButton:pressed { background:#1A2430; border-color:#57D6B5; }
QPushButton[primary="true"]:pressed { background:#45B89A; }
QPushButton:disabled { background:#202B36; color:#82909F; border-color:#303B47; }
QTabWidget::pane { border:0; }
QTabWidget::tab-bar { alignment:center; }
QTabBar::tab { padding:12px 22px; margin:4px; border-radius:6px; color:#B0BDCE; border:1px solid transparent; background:transparent; }
QTabBar::tab:selected { color:#57D6B5; }
QHeaderView::section { background:#1D2632; color:#B0BDCE; border:0; padding:9px; }
QTableWidget { gridline-color:#293544; }
QTableWidget::item:selected { background:#234D49; }
QScrollArea { border:0; }
QSplitter::handle { background:#354153; }
QCheckBox { spacing:8px; }
QRadioButton { spacing:8px; }
QRadioButton::indicator { width:12px; height:12px; border-radius:8px; border:2px solid #82909F; background:#121923; }
QRadioButton::indicator:checked { border:2px solid #57D6B5; background:qradialgradient(cx:.5,cy:.5,radius:.5,fx:.5,fy:.5,stop:0 #57D6B5,stop:.55 #57D6B5,stop:.6 #121923,stop:1 #121923); }
'''

def label(text, role=None):
    w=QLabel(text);w.setWordWrap(True)
    if role:w.setProperty('role',role)
    return w

def scroll(widget):
    area=QScrollArea();area.setWidgetResizable(True);area.setWidget(widget)
    area.setMinimumWidth(320);return area

def build(w):
    from .app import button,number,combo
    # Page 0 is the start screen (new or open project); page 1 is the four-step workspace.
    from PySide6.QtWidgets import QStackedWidget
    from .start_screen import StartScreen
    # One Update button per screen, top right; hidden until a newer version is found.
    w.update_buttons=[]
    def update_button():
        b=button('Update available',w.install_update);b.setProperty('primary',True);b.setToolTip('A newer version of Video Translator is ready. Click to install it.')
        b.hide();w.update_buttons.append(b);return b
    w.update_button=update_button
    w.stack=QStackedWidget();w.setCentralWidget(w.stack);w.start=StartScreen(w);w.stack.addWidget(w.start)
    central=QWidget();w.stack.addWidget(central);outer=QVBoxLayout(central)
    outer.setContentsMargins(22,16,22,12);outer.setSpacing(12)
    # The four bands rise in on launch (motion.fade_in), header first.
    head=QWidget();header=QHBoxLayout(head);header.setContentsMargins(0,0,0,0);brand=QLabel();brand.setPixmap(QPixmap(str(ROOT/'assets'/'video-translator.png')).scaled(40,40,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation));header.addWidget(brand)
    header.addWidget(label('Video Translator','title'))
    header.addStretch();privacy=label('Local AI  /  No uploads  /  Original audio kept','muted');privacy.setWordWrap(False);header.addWidget(privacy);header.addWidget(update_button());outer.addWidget(head)
    tools=QWidget();bar=QHBoxLayout(tools);bar.setContentsMargins(0,0,0,0)
    for title,fn in [('Home',w.go_home),('Save project',w.save_from_button)]:bar.addWidget(button(title,fn))
    w.file_label=label('','muted');bar.addWidget(w.file_label,1);outer.addWidget(tools)
    w.tabs=motion.PillTabWidget();outer.addWidget(w.tabs,1)
    w.side_panels=[];w.side_layouts=[]
    w.player_hosts=[]
    for title,heading in [('Setup','Set up your translation'),('Review','Review your translation'),('Preview','Check a short preview'),('Export','Export your translation')]:
        page=QWidget();layout=QVBoxLayout(page);layout.setContentsMargins(0,8,0,0)
        layout.addWidget(label(heading,'title'))
        split=QSplitter(Qt.Orientation.Horizontal);layout.addWidget(split,1)
        left=QWidget();left_layout=QVBoxLayout(left);left_layout.setContentsMargins(0,0,8,0)
        right=QWidget();right_layout=QVBoxLayout(right);right_layout.setContentsMargins(8,0,0,0)
        split.addWidget(left);split.addWidget(right);split.setSizes([850,460]);split.setChildrenCollapsible(False)
        w.player_hosts.append(left_layout);w.side_panels.append(right);w.side_layouts.append(right_layout)
        setattr(w,title.lower()+'_layout',right_layout)
        w.tabs.addTab(page,f'{w.tabs.count()+1}  {title}')
    # One player is moved between pages, preserving playback, edits and its video sink.
    w.player_panel=QWidget();lv=QVBoxLayout(w.player_panel);lv.setContentsMargins(0,0,0,0)
    w.video=LiveVideoWidget();w.video.setMinimumSize(320,180);lv.addWidget(w.video,1)
    w.player=QMediaPlayer(w);w.audio=QAudioOutput(w);w.player.setAudioOutput(w.audio);w.player.setVideoSink(w.video.videoSink())
    w.video.boxesEdited.connect(w.live_boxes_changed)
    w.video.captionMoved.connect(w.move_caption);w.video.captionDragStarted.connect(w.begin_caption_drag)
    w.video.captionResized.connect(w.resize_caption)
    w.player.errorOccurred.connect(lambda e,s:w.status.setText('Playback: '+s))
    w.view_label=label('Loading the video…','muted');lv.addWidget(w.view_label)
    w.pending_position=None;w.preview_freeze_position=None
    w.video.videoSink().videoFrameChanged.connect(w.preview_frame_ready)
    w.player.mediaStatusChanged.connect(w.media_loaded);w.player.tracksChanged.connect(w.configure_subtitle_track)
    row=QHBoxLayout()
    for title,fn in [('Play / pause',w.toggle_play),('Live edits',w.live_view),('Original',w.original_video),('Rendered preview',w.play_preview)]:row.addWidget(button(title,fn))
    w.time_label=label('0:00');row.addWidget(w.time_label);lv.addLayout(row)
    w.seek=QSlider(Qt.Orientation.Horizontal);lv.addWidget(w.seek);w.seek.sliderMoved.connect(w.player.setPosition)
    w.player.durationChanged.connect(lambda v:w.seek.setRange(0,int(v)));w.player.positionChanged.connect(w.position)
    w.player_hosts[0].addWidget(w.player_panel,1)
    build_setup(w)
    w.style_panel_setup();w.style_panel.setTitle('Text style · live for all subtitles')
    w.inspector=motion.PillTabWidget();w.review_layout.addWidget(w.inspector,1);w.inspector.addTab(scroll(w.style_panel),'Text style')
    w.live_panel=QGroupBox('Selected subtitle');editor=QVBoxLayout(w.live_panel)
    timing=QHBoxLayout();w.live_start=number(0,999999,0,3);w.live_end=number(0,999999,1,3)
    timing.addWidget(label('Start'));timing.addWidget(w.live_start);timing.addWidget(label('End'));timing.addWidget(w.live_end);editor.addLayout(timing)
    w.live_text=QPlainTextEdit();w.live_text.setPlaceholderText('Select a subtitle to edit its translation.');w.live_text.setMinimumHeight(120)
    w.live_text.setLayoutDirection(Qt.LayoutDirection.RightToLeft);w.live_text.setFont(QFont('Almarai',14));editor.addWidget(w.live_text)
    w.draw_covers=QCheckBox('Drag covers in video');editor.addWidget(w.draw_covers)
    editor.addWidget(button('Clear selected covers',lambda:w.live_boxes_changed([])))
    editor.addWidget(label('Cover rectangles · x, y, width, height','muted'))
    w.live_boxes=QPlainTextEdit();w.live_boxes.setMaximumHeight(80);editor.addWidget(w.live_boxes)
    w.live_hint=label('Drag inside to move; drag a corner to resize. Numeric coordinates also work.','muted');editor.addWidget(w.live_hint)
    editor.addWidget(button('Edit original text / timing / line breaks',w.edit_cue));editor.addWidget(button('Edit exact line covers',w.edit_covers))
    editor.addStretch();w.inspector.addTab(scroll(w.live_panel),'Text && timing')
    review_bottom=QWidget();rv=QVBoxLayout(review_bottom);rv.setContentsMargins(0,0,0,0)
    row=QHBoxLayout();table_title=label('Original and translation   ·   Space play/pause · Enter edit · Ctrl+Enter reviewed, next · Ctrl+Z undo','muted');table_title.setWordWrap(False);row.addWidget(table_title);row.addStretch()
    w.review_filter=combo(['All subtitles','Needs review','Flagged','Reviewed']);row.addWidget(w.review_filter);rv.addLayout(row)
    w.table=QTableWidget(0,5);w.table.setHorizontalHeaderLabels(['Start','End','Original','Translation','Review'])
    w.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows);w.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    for c in (2,3):w.table.horizontalHeader().setSectionResizeMode(c,QHeaderView.ResizeMode.Stretch)
    w.table.setColumnWidth(0,72);w.table.setColumnWidth(1,72);w.table.setColumnWidth(4,90)
    w.table.cellDoubleClicked.connect(lambda r,c:w.edit_cue());w.table.itemSelectionChanged.connect(w.seek_cue);rv.addWidget(w.table,1)
    row=QHBoxLayout()
    for title,fn in [('Add cue',w.add_cue),('Delete cue',w.delete_cue),('Mark reviewed',w.mark_reviewed)]:row.addWidget(button(title,fn))
    rv.addLayout(row);w.summary=label('Recognition flags and reviewed status are independent.','muted');rv.addWidget(w.summary)
    # Resizable video/table split, with an independently scrolling inspector.
    w.review_split=QSplitter(Qt.Orientation.Vertical)
    w.review_player_slot=QWidget();w.review_player_layout=QVBoxLayout(w.review_player_slot);w.review_player_layout.setContentsMargins(0,0,0,0)
    w.review_split.addWidget(w.review_player_slot);w.review_split.addWidget(review_bottom);w.review_split.setSizes([420,320])
    w.player_hosts[1].addWidget(w.review_split,1)
    w.review_layout.addWidget(button('Keep dialogue matching selected layout',w.lock_dialogue_layout))
    w.review_layout.addWidget(button('Detect covers from video',lambda:w.run('covers')))
    w.review_layout.addWidget(button('Word && phrase replacements',w.edit_replacements))
    w.review_layout.addWidget(button('Continue to preview',lambda:w.tabs.setCurrentIndex(2)))
    build_output(w)
    footer=QWidget();foot=QVBoxLayout(footer);foot.setContentsMargins(0,0,0,0);foot.setSpacing(8);outer.addWidget(footer)
    # Which step a job is on: done ✓, running ● (breathing), still to come ○. Hidden until the first job.
    w.steps=motion.StepStrip();foot.addWidget(w.steps)
    # A thin strip with no text on it: white on teal is hard to read, and Qt would use the system's digits.
    w.progress=motion.GlideBar();foot.addWidget(w.progress)
    row=QHBoxLayout();w.status=label('Ready.','muted');row.addWidget(w.status,1)
    w.elapsed_label=label('','muted');row.addWidget(w.elapsed_label)
    w.cancel=button('Cancel processing',w.cancel_job);w.cancel.setEnabled(False);row.addWidget(w.cancel);foot.addLayout(row)
    w.log=QPlainTextEdit();w.log.setReadOnly(True);w.log.setMaximumHeight(80);w.log.hide()
    details=button('Show / hide processing log',lambda:motion.reveal(w.log,w.log.isHidden()));foot.addWidget(details,0,Qt.AlignmentFlag.AlignLeft);foot.addWidget(w.log)
    w.workspace_parts=[head,tools,footer]  # faded when the workspace opens; never the tabs, which hold the player
    w.row_flash=motion.RowFlash(w.table);w.table.setItemDelegate(w.row_flash)
    w.tabs.currentChanged.connect(w.change_page);w.review_filter.currentIndexChanged.connect(w.filter_rows)
    w.review_filter.currentIndexChanged.connect(lambda:motion.fade_in(w.table,160))  # the list fades when the filter changes

def build_setup(w):
    from .app import button,number,combo
    panel=QWidget();layout=QVBoxLayout(panel);w.setup_layout.addWidget(scroll(panel))
    form=QFormLayout();form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow);layout.addLayout(form)
    w.mode=combo(['Spoken dialogue (audio)','Visible subtitles (OCR)']);form.addRow('Translation source',w.mode)
    w.source=combo(list(LANGUAGES));w.target=combo(list(LANGUAGES)[1:]);w.target.setCurrentText('Arabic')
    form.addRow('Source language',w.source);form.addRow('Translate into',w.target)
    w.model=QComboBox();w.model.setEditable(True);w.model.setCurrentText('gemma4:12b')
    row=QHBoxLayout();row.addWidget(w.model,1);row.addWidget(button('Refresh',w.refresh_models));form.addRow('Translation model',row)
    w.model_status=label('Ollama connection not checked','muted');layout.addWidget(w.model_status)
    w.ollama_setup=button('Set up translation (Ollama)…',w.setup_ollama);w.ollama_setup.hide();layout.addWidget(w.ollama_setup)
    layout.addWidget(label('Changing model or target language retranslates unreviewed lines. Reviewed translations are retained.','muted'))
    layout.addWidget(button('Edit names / terminology',w.edit_glossary))
    layout.addWidget(button('Compare models…',w.compare_models))
    layout.addWidget(button('Word && phrase replacements',w.edit_replacements))
    w.ocr_panel=QGroupBox('Visible subtitle source');ocr=QFormLayout(w.ocr_panel)
    w.script=combo(['English','Auto','Arabic','Chinese','Japanese','Korean','French','Spanish','German','Russian','Turkish','Hindi','Persian','Urdu'])
    ocr.addRow('Subtitle alphabet',w.script);w.interval=number(.04,2,.25);ocr.addRow('Check picture every (s)',w.interval)
    ocr.addRow(label('Source Auto detects language from readable text. Choose its alphabet here; Auto OCR reads Arabic + Latin.','muted'))
    ocr.addRow(button('Select subtitle area on the video',w.select_roi))
    w.roi_label=label('Select a tight dialogue area to exclude menus and map labels.','muted');ocr.addRow(w.roi_label)
    w.kind=combo(['Burned into the picture','Separate subtitle track'])
    w.track=QSpinBox();w.track.setRange(0,99)
    ocr.addRow(button('Download selected OCR model',w.setup_ocr))
    w.dialogue_status=label('For dialogue-only filtering: select a recognised dialogue cue in Review, then keep its layout.','muted');ocr.addRow(w.dialogue_status)
    layout.addWidget(w.ocr_panel)
    w.speech_panel=QGroupBox('Spoken dialogue source');speech=QFormLayout(w.speech_panel)
    w.asr=combo(['turbo','small','large-v3']);speech.addRow('Speech model',w.asr)
    w.asr.setToolTip('turbo: fast, the default. small: lightest. large-v3: slowest and most accurate, best for Chinese, Japanese and Arabic speech (separate 3 GB download).')
    w.audio_track=QComboBox();w.audio_track.addItem('First audio track',0);speech.addRow('Audio track',w.audio_track)
    speech.addRow(label('Keeps original voices; creates subtitles only.','muted'));layout.addWidget(w.speech_panel)
    w.full_video=QCheckBox('Entire video');w.full_video.setChecked(True);layout.addWidget(w.full_video)
    w.range_summary=label('Full duration is selected by default.','muted');layout.addWidget(w.range_summary)
    advanced=QGroupBox('Advanced processing settings');advanced.setCheckable(True);advanced.setChecked(False)
    w.advanced=advanced
    advanced_layout=QVBoxLayout(advanced);body=QWidget();af=QFormLayout(body)
    w.device=combo(['Auto (prefer GPU)','GPU (CUDA)','CPU']);af.addRow('Device',w.device)
    w.begin=number(0,999999,0);w.end=number(0,999999,0);af.addRow('Start (seconds)',w.begin);af.addRow('End (seconds)',w.end)
    advanced_layout.addWidget(body);body.hide();advanced.toggled.connect(lambda on:motion.reveal(body,on));layout.addWidget(advanced)
    w.run_hint=label('Recognise and translate locally. Processing can be cancelled and resumed.','muted');layout.addWidget(w.run_hint)
    w.process=button('Process / Resume',w.primary_process);w.process.setProperty('primary',True);layout.addWidget(w.process)
    w.resume=button('Resume saved processing',lambda:w.run('process'));layout.addWidget(w.resume)
    layout.addWidget(label('Resume reuses completed recognition and translation batches. Translate again refreshes unreviewed translations.','muted'))
    layout.addWidget(button('Start over…',w.start_over));layout.addStretch()

def build_output(w):
    from .app import button,number,combo
    panel=QWidget();layout=QVBoxLayout(panel);w.preview_layout.addWidget(scroll(panel))
    layout.addWidget(label('Approve the translation, timing and covers before export.','muted'))
    form=QFormLayout();w.preview_start=number(0,999999,0);w.preview_length=number(2,60,12)
    form.addRow('Start (seconds)',w.preview_start);form.addRow('Duration (seconds)',w.preview_length);layout.addLayout(form)
    w.generate_button=button('Generate preview',lambda:w.run('preview'));w.generate_button.setProperty('primary',True);layout.addWidget(w.generate_button)
    layout.addWidget(button('Watch rendered preview',w.play_preview));w.approve_button=button('I watched this preview · approve',w.approve);layout.addWidget(w.approve_button)
    w.approval_label=label('Generate and watch a preview first.');layout.addWidget(w.approval_label)
    layout.addWidget(label('Check names, line breaks, text size and exact cover positions. Approval does not mark subtitles reviewed.','muted'))
    w.continue_export=button('Continue to export',lambda:w.tabs.setCurrentIndex(3));layout.addWidget(w.continue_export);layout.addStretch()
    panel=QWidget();layout=QVBoxLayout(panel);w.export_layout.addWidget(scroll(panel))
    form=QFormLayout();w.appearance=combo([name for _,name in APPEARANCES]);form.addRow('Subtitle appearance',w.appearance)
    form.addRow('Original subtitle type',w.kind);form.addRow('Subtitle track (0 = first)',w.track);layout.addLayout(form)
    layout.addWidget(label('Original video stays unchanged. Video exports preserve every original audio track.','muted'))
    w.output_label=label('The output folder is based on the source video name.');w.output_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(w.output_label)
    w.output_files=label('MKV video · SRT · ASS · Editable project');layout.addWidget(w.output_files)
    w.export_approval=label('A current approved preview is required.');layout.addWidget(w.export_approval)
    # Shown only for YouTube captions: how to upload, and what this output cannot do.
    w.youtube_help=label('','muted');w.youtube_help.setTextFormat(Qt.TextFormat.RichText);w.youtube_help.hide();layout.addWidget(w.youtube_help)
    w.export_button=button('Export translated video',lambda:w.run('export'));w.export_button.setProperty('primary',True);layout.addWidget(w.export_button)
    layout.addWidget(button('Back to preview && approval',lambda:w.tabs.setCurrentIndex(2)))
    w.open_video_button=button('Open exported video',w.open_export_video);layout.addWidget(w.open_video_button);layout.addWidget(button('Open output folder',w.open_outputs));layout.addStretch()
