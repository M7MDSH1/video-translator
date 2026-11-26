import copy,tempfile,unittest
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage,QColor
from PySide6.QtCore import Qt,QPoint
from PySide6.QtTest import QTest
from videotranslator.live_video import LiveVideoWidget
from videotranslator.project import new_project,save_project,load_project,fingerprint,validate
from videotranslator.subtitles import caption_blocks,caption_bounds,rendered_covers,make_ass,display_cues

class CaptionDragTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def setUp(self):
        self.p=new_project('unused.mp4',{'width':640,'height':360,'duration':10,'streams':[]})
        self.p.update(appearance='replace',original_kind='burned')
        self.p['style'].update(size=26,minimum_size=1)
        self.p['cues']=[{'start':1,'end':4,'original':'hello','translation':'مرحبا بالعالم','boxes':[[180,270,280,40]],'flags':[],'reviewed':True}]
        self.w=LiveVideoWidget();self.w.resize(800,600);self.w.frame=QImage(640,360,QImage.Format.Format_RGB32);self.w.frame.fill(QColor('#555555'))
        self.w.set_project(self.p);self.w.live=True;self.w.time=2;self.w.selected=0;self.w.show();self.app.processEvents()
        self.events=[]
        def move(x,y,index):
            self.events.append((x,y,index));owner=self.p['style'] if index<0 else self.p['cues'][index];owner['caption_offset']=[x,y]
        self.w.captionMoved.connect(move)
        self.resize_events=[]
        def resize(scale,index):
            self.resize_events.append((scale,index));owner=self.p['style'] if index<0 else self.p['cues'][index];owner['caption_scale']=scale
        self.w.captionResized.connect(resize)
    def tearDown(self):self.w.close();self.w.deleteLater();self.app.processEvents()
    def bounds(self):return caption_bounds(caption_blocks(self.p['cues'][0],self.p,640,360,2))
    def point(self,x,y):
        rect=self.w.frame_rect();return QPoint(round(rect.x()+x*rect.width()/640),round(rect.y()+y*rect.height()/360))
    def drag(self,dx,dy):
        l,t,r,b=self.bounds();start=self.point((l+r)/2,(t+b)/2);end=self.point((l+r)/2+dx,(t+b)/2+dy)
        QTest.mousePress(self.w,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(self.w,end);QTest.mouseRelease(self.w,Qt.MouseButton.LeftButton,pos=end)
    def test_global_drag_obeys_letterboxing_and_keeps_original_covers(self):
        before=self.bounds();boxes=copy.deepcopy(self.p['cues'][0]['boxes']);original_covers=rendered_covers(self.p['cues'][0],self.p,640,360,2)
        self.drag(40,-70);after=self.bounds()
        self.assertEqual(self.events[-1][2],-1);self.assertAlmostEqual(after[0]-before[0],40,delta=1);self.assertAlmostEqual(after[1]-before[1],-70,delta=1)
        self.assertEqual(self.p['cues'][0]['boxes'],boxes)
        covers=rendered_covers(self.p['cues'][0],self.p,640,360,2)
        self.assertTrue(all(c in covers for c in original_covers));self.assertGreater(len(covers),len(original_covers))
    def test_selected_drag_persists_and_changes_ass_not_other_cues(self):
        second=copy.deepcopy(self.p['cues'][0]);second.update(start=5,end=8);self.p['cues'].append(second)
        self.w.caption_scope='selected';old=fingerprint(self.p);ass=make_ass(self.p);self.drag(-30,-60)
        self.assertEqual(self.events[-1][2],0);self.assertNotIn('caption_offset',second)
        self.assertNotEqual(fingerprint(self.p),old);self.assertNotEqual(make_ass(self.p),ass)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'p.json';save_project(self.p,path)
            self.assertEqual(load_project(path)['cues'][0]['caption_offset'],self.p['cues'][0]['caption_offset'])
    def test_drag_stays_inside_picture(self):
        self.drag(900,-900);l,t,r,b=self.bounds()
        self.assertGreaterEqual(l,-.01);self.assertGreaterEqual(t,-.01);self.assertLessEqual(r,640.01);self.assertLessEqual(b,360.01);validate(self.p)
    def test_cover_mode_does_not_move_caption(self):
        self.w.edit_covers=True;self.drag(10,-10);self.assertEqual(self.events,[])
    def test_drag_moves_added_subtitles_too(self):
        self.p['appearance']='add';before=self.bounds();self.drag(20,-40);after=self.bounds()
        self.assertAlmostEqual(after[0]-before[0],20,delta=1);self.assertAlmostEqual(after[1]-before[1],-40,delta=1)
    def test_held_cue_uses_saved_offset(self):
        self.p['cues'][0]['end']=1.1;self.p['cues'][0]['caption_offset']=[0,-.2]
        original,held=display_cues(self.p)[0]
        self.assertGreater(held['end'],original['end']);self.assertEqual(held['caption_offset'],[0,-.2])

    def resize_corner(self,corner,factor):
        l,t,r,b=self.bounds();cx=(l+r)/2;cy=(t+b)/2
        x,y=((l,t),(r,t),(l,b),(r,b))[corner]
        start=self.point(x,y);end=self.point(cx+(x-cx)*factor,cy+(y-cy)*factor)
        QTest.mousePress(self.w,Qt.MouseButton.LeftButton,pos=start);QTest.mouseMove(self.w,end);QTest.mouseRelease(self.w,Qt.MouseButton.LeftButton,pos=end)

    def test_all_four_corners_resize_text_proportionally(self):
        for corner in range(4):
            self.p['style'].pop('caption_scale',None)
            before=self.bounds();font=caption_blocks(self.p['cues'][0],self.p,640,360,2)[0]['style']['size']
            self.resize_corner(corner,1.2);after=self.bounds()
            self.assertEqual(self.resize_events[-1][1],-1)
            self.assertGreater(caption_blocks(self.p['cues'][0],self.p,640,360,2)[0]['style']['size'],font)
            self.assertAlmostEqual((after[2]-after[0])/(before[2]-before[0]),1.2,delta=.02)
            self.assertAlmostEqual((after[3]-after[1])/(before[3]-before[1]),1.2,delta=.02)
        self.assertEqual(self.events,[],'Corners resize rather than move')

    def test_selected_resize_shrinks_and_persists_in_ass(self):
        self.w.caption_scope='selected';before=make_ass(self.p);boxes=copy.deepcopy(self.p['cues'][0]['boxes'])
        self.resize_corner(0,.7)
        self.assertEqual(self.resize_events[-1][1],0);self.assertLess(self.p['cues'][0]['caption_scale'],1)
        self.assertNotEqual(make_ass(self.p),before);self.assertEqual(boxes,self.p['cues'][0]['boxes'])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'p.json';save_project(self.p,path)
            self.assertEqual(load_project(path)['cues'][0]['caption_scale'],self.p['cues'][0]['caption_scale'])

    def test_resized_caption_fits_frame_and_original_masks_stay(self):
        covers=rendered_covers(self.p['cues'][0],self.p,640,360,2);self.resize_corner(0,8)
        l,t,r,b=self.bounds();self.assertGreaterEqual(l,-.01);self.assertGreaterEqual(t,-.01);self.assertLessEqual(r,640.01);self.assertLessEqual(b,360.01)
        after=rendered_covers(self.p['cues'][0],self.p,640,360,2);self.assertTrue(all(c in after for c in covers))

    def test_corner_resize_in_add_mode(self):
        self.p['appearance']='add';font=caption_blocks(self.p['cues'][0],self.p,640,360,2)[0]['style']['size']
        self.resize_corner(1,1.25)
        self.assertGreater(caption_blocks(self.p['cues'][0],self.p,640,360,2)[0]['style']['size'],font)

    def test_invalid_scale_rejected(self):
        for scale in (0,-1,float('nan'),9):
            self.p['style']['caption_scale']=scale
            with self.assertRaises(ValueError):validate(self.p)

if __name__=='__main__':unittest.main()

class ClickIsNotAnEditTests(unittest.TestCase):
    def test_unchanged_move_or_resize_keeps_approval_and_review(self):
        from unittest.mock import MagicMock
        from videotranslator.app import MainWindow
        p=new_project('unused.mp4',{'width':640,'height':360,'duration':10,'streams':[]})
        p['cues']=[{'start':1,'end':4,'original':'hi','translation':'مرحبا','boxes':[],'flags':[],'reviewed':True}]
        stub=MagicMock();stub.p=p;before=fingerprint(p)
        for index in (-1,0):
            MainWindow.move_caption(stub,0.,0.,index);MainWindow.resize_caption(stub,1.,index)
        self.assertEqual(fingerprint(p),before);self.assertTrue(p['cues'][0]['reviewed']);stub.refresh_approval.assert_not_called()
        MainWindow.move_caption(stub,.1,0.,-1);stub.refresh_approval.assert_called()
