import unittest
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
import numpy as np
from videotranslator.project import new_project
from videotranslator.subtitles import cue,caption_layout,caption_anchor,make_ass
from videotranslator.live_video import LiveVideoWidget

class CaptionLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.p=new_project('fixture.mp4',{'width':640,'height':360,'duration':5})
        self.p.update(appearance='replace',original_kind='burned')
        self.p['style']['size']=28
        self.c=cue(0,4,'Source',[[0,0,120,35]],1)
        self.c['translation']='هذه ترجمة طويلة يجب أن تظهر كاملة\nThis translated line must remain visible.'
        self.p['cues']=[self.c]
    def assert_inside(self,layout):
        self.assertGreaterEqual(layout['x']-layout['width']/2,7.9)
        self.assertLessEqual(layout['x']+layout['width']/2,632.1)
        self.assertGreaterEqual(layout['y']-layout['height'],7.9)
        self.assertLessEqual(layout['y'],352.1)
    def test_all_four_frame_corners_keep_full_block_visible(self):
        for x,y in [(0,0),(520,0),(0,325),(520,325)]:
            self.c['boxes']=[[x,y,120,35]]
            with self.subTest(x=x,y=y):self.assert_inside(caption_layout(self.c,self.p,640,360,1))
    def test_oversized_unbroken_word_and_many_lines_fit_without_text_loss(self):
        for text in ['W'*180,'\n'.join(['مرحبا بالعالم']*20)]:
            self.c['translation']=text
            layout=caption_layout(self.c,self.p,640,360,1)
            self.assert_inside(layout)
            self.assertEqual('\n'.join(layout['lines']),text)
            self.assertLess(layout['style']['size'],self.p['style']['size'])
    def moving(self):
        self.c['translation']='مرحبا'
        self.c['cover_spans']=[{'start':0,'end':2,'boxes':[[100,120,160,30]]},{'start':2,'end':4,'boxes':[[400,260,160,30]]}]
    def test_active_span_overrides_stale_static_boxes_and_ass_splits_at_boundary(self):
        self.moving()
        self.assertEqual(caption_anchor(self.c,self.p,640,360,2),(480,290))
        events=[s for s in make_ass(self.p).splitlines() if s.startswith('Dialogue: 1')]
        self.assertEqual(len(events),2)
        self.assertIn('0:00:00.00,0:00:02.00',events[0]);self.assertRegex(events[0],r'\\pos\(180,15[0-5]\)')
        self.assertIn('0:00:02.00,0:00:04.00',events[1]);self.assertRegex(events[1],r'\\pos\(480,29[0-5]\)')
        preview=make_ass(self.p,offset=2.5)
        self.assertNotIn('\\pos(180,150)',preview)
        self.assertIn('0:00:00.00,0:00:01.50',preview)
    def test_span_gap_uses_manual_position_not_stale_covers(self):
        self.moving();self.c['cover_spans'][0]['end']=1;self.c['cover_spans'][1]['start']=3
        self.assertEqual(caption_anchor(self.c,self.p,640,360,2),(320,360*self.p['style']['y']))
    def test_live_text_pixels_follow_active_cover(self):
        self.moving();w=LiveVideoWidget();w.set_project(self.p);w.live=True
        w.frame=QImage(640,360,QImage.Format.Format_RGB32);w.frame.fill(QColor('#123456'))
        centers=[]
        for t in [1,2.5]:
            w.time=t;image=w.composite();pixels=np.frombuffer(image.bits(),np.uint8).reshape(360,640,4)
            yy,xx=np.where((pixels[:,:,:3]>180).all(axis=2));self.assertGreater(len(xx),20)
            centers.append((xx.mean(),yy.mean()))
        self.assertAlmostEqual(centers[1][0]-centers[0][0],300,delta=2)
        self.assertAlmostEqual(centers[1][1]-centers[0][1],140,delta=2)
        w.close()
