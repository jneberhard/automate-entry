from decimal import Decimal
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw
from royalty_entry import amount_ocr,search_ocr,desktop
from royalty_entry.ocr import Line
from royalty_entry.profile import DEFAULT

@pytest.mark.parametrize('confirmation,expected', [(['1265484746','1265484746','12654847%','1265484746'],'1265484746'),(['1265484746','1265484748','12654847%','1265484746'],None),(['1265484746','12654847%','12654847%','1265484746'],None)])
def test_reported_partial_search_requires_three_complete_agreeing_reads(monkeypatch,confirmation,expected):
    image=Image.new('RGB',(266,20),'white')
    monkeypatch.setattr(search_ocr,'search_images',lambda _: [(image,2)]*3)
    monkeypatch.setattr(search_ocr,'search_confirmation_images',lambda _: [(image,2)]*4)
    replies=iter(['1265484746','12654847%','12654847%']+confirmation)
    ocr=SimpleNamespace(lines=lambda *a,**k:[Line(next(replies),0,0,50,10)])
    if expected is None:
        with pytest.raises(ValueError):search_ocr.read_search_number(ocr,image)
    else:assert search_ocr.read_search_number(ocr,image)==expected

@pytest.mark.parametrize('labeled,expected',[(['Amount 0']*3,Decimal('0')),(['Amount -0.25']*3,Decimal('-.25')),(['Amount 0','Amount 0','Amount 8'],None),(['Amount 0','Amount 0',''],None)])
def test_lone_glyph_context_requires_three_exact_amounts(labeled,expected):
    image=Image.new('RGB',(60,15),'white');ImageDraw.Draw(image).text((48,1),'0',fill='black')
    replies=iter(['']*18+labeled)
    ocr=SimpleNamespace(lines=lambda *a,**k:[Line(next(replies),0,0,50,10)])
    if expected is None:
        with pytest.raises(ValueError):amount_ocr.read_table_amount(ocr,image)
    else:assert amount_ocr.read_table_amount(ocr,image)==expected

def test_transfer_keeps_complete_rightmost_glyph(monkeypatch):
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.profile=DEFAULT
    image=Image.new('RGB',tuple(DEFAULT['window_size']),'white')
    right=DEFAULT['regions']['financials_amounts'][2]
    ImageDraw.Draw(image).point((right-1,DEFAULT['regions']['financials_types'][1]+24),fill='black')
    def read(ocr,cell):
        assert cell.width==60
        assert cell.getpixel((59,6))==(0,0,0)
        return Decimal('0')
    d.ocr=object();monkeypatch.setattr(amount_ocr,'read_table_amount',read)
    assert d.read_transfer_amount(image,Line('TRANSFER',0,20,60,10))==0

def test_zero_transfer_flows_to_add_without_edit(monkeypatch):
    from royalty_entry import choice_ocr
    d=desktop.RemoteDriver.__new__(desktop.RemoteDriver);d.profile=DEFAULT;d.ocr=object()
    events=[]
    d.click=lambda point,*a,**kw:events.append(point)
    d.ready=lambda *a:None;d.crop=lambda *a:None
    monkeypatch.setattr(choice_ocr,'exact_choice',lambda *a:Line('PAYMENT OF ROYALTIES',0,0,50,10))
    d.text=lambda *a:'PAYMENT OF ROYALTIES'
    d.paste=lambda *a:events.append(a)
    d.prepare_payment(Decimal('-.01'),'Reference')
    assert events[0]=='financials_add'
    assert 'financials_edit' not in events
    assert ('entry_amount','-0.01','entry','entry_amount') in events
