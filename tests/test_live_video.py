import copy
import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import QPoint,Qt
from PySide6.QtTest import QTest
from videotranslator.project import new_project
from videotranslator.live_video import LiveVideoWidget,active_covers

class LiveVideoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.p=new_project('tests/fixtures/test_excerpt.mp4',{'width':640,'height':360,'duration':10})
        self.p['appearance']='replace';self.p['style'].update(size=28,y=.8,padding=0)
        self.p['cues']=[{'start':1,'end':3,'original':'Hello','translation':'مرحبا بالعالم!','boxes':[[100,300,200,20]]}]
        self.w=LiveVideoWidget();self.w.set_project(self.p);self.w.live=True
        self.w.frame=QImage(640,360,QImage.Format.Format_RGB32);self.w.frame.fill(QColor('#abcdef'));self.w.time=2
    def tearDown(self):self.w.close()
    def test_covers_follow_timed_spans(self):
        c=self.p['cues'][0];c['cover_spans']=[{'start':1,'end':2,'boxes':[[1,2,3,4]]},{'start':2,'end':3,'boxes':[[5,6,7,8]]}]
        self.assertEqual(active_covers(c,2.1),[[5,6,7,8]])
    def test_live_cover_and_text_change_without_encoding(self):
        first=self.w.composite()
        self.assertEqual(first.pixelColor(110,310).name(),'#232323')
        self.p['cues'][0]['translation']='تغير النص الآن';self.p['cues'][0]['boxes']=[[20,30,100,20]]
        second=self.w.composite()
        self.assertNotEqual(first,second)
        self.assertEqual(second.pixelColor(110,310).name(),'#abcdef')
        # The bounded caption can now overlap this pixel. Check cover color
        # independently of the white text drawn over it.
        self.p['cues'][0]['translation']=''
        self.assertEqual(self.w.composite().pixelColor(30,40).name(),'#232323')
    def test_original_and_rendered_views_do_not_overlay(self):
        self.w.live=False;self.assertEqual(self.w.composite(),self.w.frame)
    def test_timing_edit_and_cue_end_remove_overlay(self):
        self.p['cues'][0]['end']=1.5
        self.w.time=2.3  # past the 1.2 s minimum reading time that now holds short captions
        self.assertEqual(self.w.composite(),self.w.frame)
    def test_cover_starts_one_sample_before_recognition(self):
        self.p['sample_interval']=.25;self.p['original_kind']='burned';self.w.time=.8  # cue starts at 1
        self.p['cues'][0]['translation']=''
        self.assertEqual(self.w.composite().pixelColor(110,310).name(),'#232323')
        self.w.time=.7;self.assertEqual(self.w.composite().pixelColor(110,310).name(),'#abcdef')
    def test_add_mode_has_no_cover(self):
        self.p['appearance']='add'
        self.assertEqual(self.w.composite().pixelColor(110,310).name(),'#abcdef')
    def test_drag_cover_changes_only_selected_geometry(self):
        self.w.resize(640,360);self.w.edit_covers=True;self.w.selected=0
        changes=[];self.w.boxesEdited.connect(changes.append)
        QTest.mousePress(self.w,Qt.MouseButton.LeftButton,pos=QPoint(200,310))
        QTest.mouseMove(self.w,QPoint(210,305))
        QTest.mouseRelease(self.w,Qt.MouseButton.LeftButton,pos=QPoint(210,305))
        self.assertEqual(changes[-1],[[110,295,200,20]])

if __name__=='__main__':unittest.main()
