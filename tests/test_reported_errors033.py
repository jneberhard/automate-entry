import re
from decimal import Decimal
from types import SimpleNamespace
from PIL import Image,ImageDraw
import pytest
from royalty_entry.ocr import Line
from royalty_entry import search_ocr,amount_ocr,desktop
from royalty_entry.rules import Record

@pytest.mark.parametrize('values,expected',[
    (['1265484764']*3,'1265484764'),
    (['11265484764']*3,'11265484764'),
    (['1265484764','1265484764','11265484764'],None),
    (['','',''],None),
    (['I265484764']*3,None),
])
def test_search_reader_does_not_strip_or_infer_digits(monkeypatch,values,expected):
    monkeypatch.setattr(search_ocr,'search_confirmation_images',lambda _: [])
    im=Image.new('RGB',(266,20),'white')
    monkeypatch.setattr(search_ocr,'search_images',lambda _: [(im,2)]*3)
    replies=iter(values);o=SimpleNamespace(lines=lambda *a,**k:[Line(next(replies),0,0,60,10)])
    if expected is None:
        with pytest.raises(ValueError):search_ocr.read_search_number(o,im)
    else:assert search_ocr.read_search_number(o,im)==expected

def test_search_border_removal_preserves_real_short_digit_strokes():
    im=Image.new('RGB',(266,20),'white');draw=ImageDraw.Draw(im)
    draw.line((0,0,0,19),fill='black');draw.line((0,19,265,19),fill='black')
    draw.line((5,5,5,13),fill='black')
    field,_=search_ocr.search_images(im)[0]
    assert field.getpixel((15,22))==(255,255,255)
    assert field.getpixel((20,22))==(0,0,0)

@pytest.mark.parametrize('value',['1265484764','1265484781'])
def test_license_entry_uses_keys_not_rdp_clipboard(monkeypatch,value):
    import pyperclip
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.handle=1;events=[]
    d.click=lambda *a:None;d.expect=lambda *a:None;d.check_stop=lambda:None;d.wait=lambda *a:None
    d.hotkey=lambda *a:events.append(a)
    d.pg=SimpleNamespace(write=lambda text,**kw:events.append(('typed',text)))
    d.text=lambda *a:value
    monkeypatch.setattr(desktop,'foreground',lambda:(1,'RDP',None))
    monkeypatch.setattr(pyperclip,'copy',lambda *a:pytest.fail('Search must not use clipboard'))
    d.paste('search_input',value,'manager','search_value')
    assert ('typed',value) in events and ('ctrl','v') not in events

@pytest.mark.parametrize('full,expected',[
    (['-63.59']*4,Decimal('-63.59')),
    (['-63.59']*3+['63.59'],None),
    (['-63.59']*3+[''],None),
    (['-83.59']*4,None),
])
def test_sign_disagreement_requires_unanimous_intact_field_and_prior_support(monkeypatch,full,expected):
    im=Image.new('RGB',(115,21),'white')
    monkeypatch.setattr(amount_ocr,'amount_images',lambda _: [(im,4)]*6)
    monkeypatch.setattr(amount_ocr,'amount_retry_images',lambda _: [(im,2)]*5)
    monkeypatch.setattr(amount_ocr,'amount_full_field_images',lambda _: [(im,3)]*4)
    replies=iter(['-63.59','63.59']*3+['83.9','63.59','63.59','-63.59','-63.59']+full)
    o=SimpleNamespace(lines=lambda *a,**k:[Line(next(replies),0,0,35,10)])
    if expected is None:
        with pytest.raises(ValueError):amount_ocr.read_amount(o,im)
    else:assert amount_ocr.read_amount(o,im)==expected

@pytest.mark.parametrize('wrong_identity',[False,True])
def test_single_result_grid_ocr_cannot_hide_a_candidate_or_bypass_properties(wrong_identity):
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.profile={'regions':{'result_licenses':[470,382,625,936]}}
    d.expect=lambda _:None;d.text=lambda im,key:'1265484746' if key=='search_value' else '1 License (Number: 1265484746)'
    d.crop=lambda *a:None;d.ocr=SimpleNamespace(lines=lambda *a:[Line('1265484748',0,4,60,10)])
    d.ready=lambda _:None;events=[];d.click=lambda *a,**kw:events.append('open')
    def verify(*a):
        events.append('verify')
        if wrong_identity:raise desktop.ScreenError('Wrong full license in Properties')
    d.verify_open_identity=verify
    if wrong_identity:
        with pytest.raises(desktop.ScreenError):d.open_record(Record(11,'1265484746','Display','PUB358'))
    else:assert d.open_record(Record(11,'1265484746','Display','PUB358'))
    assert events==['open','verify']

@pytest.mark.parametrize('replies',[
    ['11265484764','11265484764'],
    ['',''],
    ['1265484764','11265484764'],
])
def test_wrong_or_blank_search_readback_prevents_search_submission(monkeypatch,replies):
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.handle=1;clicked=[]
    d.click=lambda point,*a:clicked.append(point)
    d.expect=lambda *a:None;d.check_stop=lambda:None;d.wait=lambda *a:None;d.hotkey=lambda *a:None
    d.pg=SimpleNamespace(write=lambda *a,**k:None)
    stream=iter(replies);d.text=lambda *a:next(stream)
    monkeypatch.setattr(desktop,'foreground',lambda:(1,'RDP',None))
    with pytest.raises(desktop.ScreenError,match='Search was not submitted'):
        d.paste('search_input','1265484764','manager','search_value')
    assert clicked==['search_input']
