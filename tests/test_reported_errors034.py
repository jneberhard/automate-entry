from decimal import Decimal
from types import SimpleNamespace
import json
import pytest
from PIL import Image
from royalty_entry import desktop, search_ocr
from royalty_entry.profile import DEFAULT, load_profile
from royalty_entry.rules import royalty_amount
from royalty_entry.ocr import Line
from test_engine import Driver, run, journal

@pytest.mark.parametrize('balance,transfer,expected', [('-0.01','-0.25','-0.25'),('0','-0.25','-0.26'),('-0.01','0','-0.01'),('0','0','-0.01')])
def test_confirmed_payment_rules(journal,balance,transfer,expected):
    assert royalty_amount(Decimal(transfer),Decimal(balance)) == Decimal(expected)
    driver=Driver(balance=balance,transfer=transfer)
    removed,_=run(journal,driver)
    assert not removed
    assert driver.saved[0][0] == Decimal(expected)

@pytest.mark.parametrize('values,expected', [(['0','0'],Decimal('0')),(['-.25','-.25'],Decimal('-.25')),(['-.25','-.26'],Decimal('-.25'))])
def test_transfer_page_overlap_uses_confirmed_editor_amounts(values,expected):
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver)
    d.click=lambda *args:None;d.ready=lambda *args:None
    rows=[(Line('TRANSFER',0,20,60,10),None)]
    d.pages=lambda *args: [(None,rows),(None,rows)]
    replies=iter(values);d.read_transfer_amount=lambda image,line:Decimal(next(replies))
    if expected is None:
        with pytest.raises(desktop.ScreenError,match='More than one'):d.transfers()
    else:assert d.transfers()==expected

@pytest.mark.parametrize('confirmation,expected',[(['1265743848']*4,'1265743848'),(['1265743848']*3+['1265743843'],None),(['1265743843']*4,None),(['']*4,None)])
def test_search_conflicts_require_unanimous_supported_confirmation(monkeypatch,confirmation,expected):
    image=Image.new('RGB',(266,20),'white')
    monkeypatch.setattr(search_ocr,'search_images',lambda _: [(image,2)]*3)
    monkeypatch.setattr(search_ocr,'search_confirmation_images',lambda _: [(image,2)]*4)
    values=iter(['1265743848','1265743848','1265743843']+confirmation)
    ocr=SimpleNamespace(lines=lambda *a,**k:[Line(next(values),0,0,60,10)])
    if expected is None:
        with pytest.raises(ValueError):search_ocr.read_search_number(ocr,image)
    else:assert search_ocr.read_search_number(ocr,image)==expected

def test_old_profile_gains_transfer_editor_controls(tmp_path):
    profile=json.loads(json.dumps(DEFAULT))
    del profile['regions']['entry_description'];del profile['points']['financials_edit']
    path=tmp_path/'profile.json';path.write_text(json.dumps(profile))
    assert load_profile(path)==DEFAULT

def test_transfer_inspection_restores_grid_focus_before_paging():
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.profile=DEFAULT
    d.click=lambda *args:events.append(('click',args))
    d.keys=lambda *args:events.append(('key',args))
    events=[]
    image=Image.new('RGB',tuple(DEFAULT['window_size']),'white')
    d.expect=lambda _:image;d.crop=lambda im,key:im.crop(DEFAULT['regions'][key])
    d.table=lambda *args:[]
    pages=d.pages('financials','financials_focus','financials_types','financials_types')
    next(pages)
    with pytest.raises(StopIteration):next(pages)
    assert events[-2:]==[('click',('financials_focus','financials')),('key',('financials','pagedown'))]
