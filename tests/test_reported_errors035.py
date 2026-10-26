from decimal import Decimal
from types import SimpleNamespace
from PIL import Image
import pytest
from royalty_entry import desktop, amount_ocr, search_ocr
from royalty_entry.profile import DEFAULT
from royalty_entry.ocr import Line

@pytest.mark.parametrize('value',['0','-.25'])
def test_unreadable_cell_uses_row_context_without_clicks(monkeypatch,value):
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.profile=DEFAULT
    d.click=lambda *args:pytest.fail('Transfer reading must not click Add or Edit')
    def unreadable(*args):raise ValueError('blank cell')
    monkeypatch.setattr(amount_ocr,'read_table_amount',unreadable)
    # Full row is padded 15px and begins at x689. Amount starts at x1179.
    d.ocr=SimpleNamespace(words=lambda *a,**k:[Line('123.45',100,18,40,10),Line(value,520,18,30,10)])
    assert d.read_transfer_amount(Image.new('RGB',tuple(DEFAULT['window_size']),'white'),Line('TRANSFER',0,20,60,10))==Decimal(value)

@pytest.mark.parametrize('values', [['-.25','-.26','-.25'],['','','']])
def test_unconfirmed_context_amount_is_rejected(monkeypatch,values):
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.profile=DEFAULT
    def unreadable(*args):raise ValueError('blank cell')
    monkeypatch.setattr(amount_ocr,'read_table_amount',unreadable)
    replies=iter(values)
    d.ocr=SimpleNamespace(words=lambda *a,**k:[Line(next(replies),520,18,30,10)])
    with pytest.raises(desktop.ScreenError):d.read_transfer_amount(Image.new('RGB',tuple(DEFAULT['window_size']),'white'),Line('TRANSFER',0,20,60,10))

@pytest.mark.parametrize('confirmation,expected',[(['1265484746']*4,'1265484746'),(['1265484748']*4,None),(['1265484746']*3+[''],'1265484746')])
def test_partial_search_glyphs_need_exact_supported_confirmation(monkeypatch,confirmation,expected):
    image=Image.new('RGB',(266,20),'white')
    monkeypatch.setattr(search_ocr,'search_images',lambda _: [(image,2)]*3)
    monkeypatch.setattr(search_ocr,'search_confirmation_images',lambda _: [(image,2)]*4)
    values=iter(['1265484746','12654847%','12654847%']+confirmation)
    ocr=SimpleNamespace(lines=lambda *a,**k:[Line(next(values),0,0,60,10)])
    if expected is None:
        with pytest.raises(ValueError):search_ocr.read_search_number(ocr,image)
    else:assert search_ocr.read_search_number(ocr,image)==expected
