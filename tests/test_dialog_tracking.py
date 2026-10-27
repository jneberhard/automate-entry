import numpy as np
import cv2
import pytest
from PIL import Image
from royalty_entry.dialog_tracking import DialogTracker
from royalty_entry.tracking import ToolbarTracker

@pytest.mark.parametrize('name',[n for n,_ in DialogTracker.anchors])
@pytest.mark.parametrize('scale',[.5,1,1.5])
def test_dialog_maps_independently_of_parent_toolbar(name,scale):
    tracker=DialogTracker()
    _,anchor,template=next(item for item in tracker.templates if item[0]==name)
    image=Image.new('RGB',(1600,1000),'#aaa')
    w,h=round(template.shape[1]*scale),round(template.shape[0]*scale)
    image.paste(Image.fromarray(cv2.resize(template,(w,h),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_CUBIC)).convert('RGB'),(500,300))
    view,found_anchor=tracker.locate(image,scale)
    assert found_anchor==anchor
    assert view.point(*anchor)==(500,300)
    assert abs(view.scale-scale)<.01


def test_nested_entry_takes_priority_over_visible_financials_parent():
    tracker=DialogTracker();image=Image.new('RGB',(1600,1000),'#aaa')
    for name,anchor,template in tracker.templates:
        if name in {'financials','entry'}:
            image.paste(Image.fromarray(template).convert('RGB'),(100,100) if name=='financials' else (500,300))
    _,anchor=tracker.locate(image,1)
    assert anchor==dict(DialogTracker.anchors)['entry']


def test_toolbar_tracks_uncovered_first_icons_when_properties_covers_the_rest():
    from royalty_entry.paths import asset_root
    full=Image.open(asset_root()/'assets/license-toolbar.png').convert('RGB')
    image=Image.new('RGB',(1600,1000),'#aaa');image.paste(full,(500,200))
    from PIL import ImageDraw
    ImageDraw.Draw(image).rectangle((657,208,1250,850),fill='white')
    tracker=ToolbarTracker();view=tracker.locate(image)
    assert view.point(*tracker.reference)==(500,200)


def test_snapshot_uses_dialog_transform_for_reading_and_clicks(monkeypatch):
    from types import SimpleNamespace
    from royalty_entry import desktop
    from royalty_entry.tracking import ViewTransform
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    d.profile={'window_size':[1907,1032]};d.window_prepared=True;d.module_prepared=True
    d.handle=None;d.transform=ViewTransform(1,68,28);d.check_stop=lambda:None;d.log=lambda _:None
    d.dialog_tracker=SimpleNamespace(locate=lambda *a:(ViewTransform(1,0,-31),(773,252)))
    d.tracker=SimpleNamespace(locate=lambda _:pytest.fail('Covered toolbar must not be used'))
    raw=Image.new('RGB',(1920,1080),'white');raw.putpixel((802,290),(0,0,0))
    monkeypatch.setattr(desktop,'capture_remote',lambda _:(raw,1,(0,0,1920,1080)))
    result=d.snapshot()
    assert result.getpixel((802,321))==(0,0,0)
    assert d.transform.point(973,297)==(973,266)
