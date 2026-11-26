"""Which step a running job is on, from the worker's own progress lines (engine.py report())."""

def steps(action,mode):
    read='Listen and transcribe' if mode=='speech' else 'Read on-screen subtitles'
    return {'process':['Load models',read,'Translate','Ready for review'],
            'recognize':['Load models',read,'Ready for review'],
            'translate':['Translate','Ready for review'],
            'covers':['Load OCR','Find subtitle covers','Covers ready'],
            'preview':['Render preview','Ready to watch'],
            'export':['Render video','Saved'],
            'captions':['Write captions file','Captions saved'],
            'ocr-model':['Download OCR model','Installed']}[action]

def current(action,progress,message):
    """Index of the running step. The last step (the result) is reached only when the job finishes."""
    # Recognition reports 0-50 % ("Transcribed…", "OCR …"); translation 50-100 %. Cached recognition starts at 50.
    reading=progress>0 or message.startswith(('Transcribed','OCR '))
    if action=='process':return 2 if progress>=50 or message.startswith('Translat') else 1 if reading else 0
    if action in ('recognize','covers'):return 1 if reading else 0
    return 0
