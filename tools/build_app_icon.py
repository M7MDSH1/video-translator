"""Build Windows icon sizes from the editable local SVG; no downloads."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication,QImage,QPainter
from PySide6.QtSvg import QSvgRenderer
from PIL import Image

app=QGuiApplication(sys.argv)  # the icon has a text glyph (ع); Qt fonts need an application
svg=QSvgRenderer(str(ROOT/'assets'/'video-translator.svg'))
assert svg.isValid()
canvas=QImage(1024,1024,QImage.Format.Format_ARGB32)
canvas.fill(Qt.GlobalColor.transparent)
painter=QPainter(canvas);svg.render(painter);painter.end()
assert canvas.save(str(ROOT/'assets'/'video-translator.png'))
with Image.open(ROOT/'assets'/'video-translator.png') as image:
    image.save(ROOT/'assets'/'video-translator.ico',sizes=[(n,n) for n in (16,20,24,32,40,48,64,128,256)])
    image.resize((256,256),Image.Resampling.LANCZOS).save(ROOT/'assets'/'video-translator-preview.png')
print('Built SVG, PNG and nine-size Windows ICO.')
