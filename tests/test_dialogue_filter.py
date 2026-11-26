import copy
from videotranslator import subtitles
from videotranslator.project import new_project

PROFILE={'center':.5,'speaker_y':.825,'dialogue_y':.877,'tolerance':.018,'min_height':.025}

def test_dialogue_layout_excludes_menu_map_and_death_text():
    samples=[
        {'time':0,'text':'Soul\nWho are you?','boxes':[[930,874,62,30],[862,928,202,39]],'confidence':.9},
        {'time':1,'text':'Train Abilities\nSave\nLeave','boxes':[[844,854,142,22],[844,906,50,20],[844,956,62,20]],'confidence':.9},
        {'time':2,'text':'Red Thread Barrier\nBroken Puppet Valley','boxes':[[1260,888,104,12],[1018,909,116,16]],'confidence':.9},
        {'time':3,'text':'DEAD','boxes':[[885,925,160,56]],'confidence':.9},
    ]
    before=copy.deepcopy(samples)
    fn=getattr(subtitles,'dialogue_samples',lambda s,*args:s)
    result=fn(samples,PROFILE,1920,1080)
    assert [s['text'] for s in result]==['Soul\nWho are you?','','','']
    assert samples==before

def test_dialogue_filter_removes_noise_but_keeps_short_reply():
    sample={'time':0,'text':'Soul\nMm\n000','boxes':[[930,874,62,30],[918,930,60,30],[1514,950,30,12]],'confidence':.9}
    fn=getattr(subtitles,'dialogue_samples',lambda s,*args:s)
    assert fn([sample],PROFILE,1920,1080)[0]['text']=='Soul\nMm'

def test_dialogue_layout_follows_small_whole_block_vertical_shift():
    sample={'time':0,'text':'The Hunt\nNowhere to hide.','boxes':[[900,906,122,30],[712,956,500,36]],'confidence':.9}
    assert subtitles.dialogue_samples([sample],dict(PROFILE,vertical_drift=.035),1920,1080)[0]['text']==sample['text']

def test_second_dialogue_line_is_kept_below_the_first():
    sample={'time':0,'text':'Man in Black\nExtinguish the flame.\nDrop the blade.','boxes':[[876,874,174,30],[611,925,689,42],[698,980,524,38]],'confidence':.9}
    assert subtitles.dialogue_samples([sample],dict(PROFILE,second_line_gap=.047),1920,1080)[0]['text']==sample['text']

def test_partial_lower_line_ocr_does_not_flash_shorter_caption():
    from videotranslator import dialogue
    detections=[{'text':t,'box':[700,980,520,38],'confidence':.9} for t in ['That is the path to know.','path','That is the path to know.']]
    fn=getattr(dialogue,'stable_lower_lines',lambda x:x)
    assert [v['text'] for v in fn(detections)]==['That is the path to know.']*3

def test_readable_arabic_expands_only_individual_line_cover():
    p=new_project('fixture.mp4',{'width':1920,'height':1080,'duration':4})
    p.update(appearance='replace',original_kind='burned')
    p['style']['minimum_size']=26
    c=subtitles.cue(0,4,'Man in Black\nSpeak',[[876,874,174,30],[862,928,202,39]],1)
    c['translation']='الرجل ذو الملابس السوداء\nأرني قوتك واكسب الإجابة'
    blocks=subtitles.caption_blocks(c,p,1920,1080,0)
    assert min(b['style']['size'] for b in blocks)>=26
    for b in blocks:
        x,y,w,h=b['cover'];ix,iy,iw,ih=b['ink_bounds']
        assert x<=ix and ix+iw<=x+w and y<=iy and iy+ih<=y+h
        assert h<70 and w<1000

def test_project_filter_keeps_translations_and_preserves_excluded_cues():
    from videotranslator.dialogue import filter_project
    p=new_project('fixture.mp4',{'width':1920,'height':1080,'duration':4})
    a=subtitles.cue(0,1,'Soul\nMm\n000',[[930,874,62,30],[918,930,60,30],[1514,950,30,12]],1)
    a['translation']='سول\nهمم\n000'
    b=subtitles.cue(1,2,'DEAD',[[885,925,160,56]],1)
    p['cues']=[a,b]
    assert filter_project(p,PROFILE)==1
    assert p['cues'][0]['translation']=='سول\nهمم'
    assert p['excluded_cues']==[b]
    assert filter_project(p,PROFILE)==0
    assert p['excluded_cues']==[b]
