from types import SimpleNamespace
from decimal import Decimal
from PIL import Image
import pytest
from royalty_entry import text_ocr
from royalty_entry.ocr import Line
from royalty_entry.desktop import RemoteDriver,PaymentNotSaved

@pytest.mark.parametrize('values,expected',[
    (['2026 Q3']*8,'2026 Q3'),
    (['']*2+['HFA Payments 2026 Q3']*6,'HFA Payments 2026 Q3'),
    (['2026 Q3']*4+['2026 03']*4,None),
    (['']*8,None),
])
def test_reference_preserves_exact_text_and_rejects_ambiguous_reads(monkeypatch,values,expected):
    image=Image.new('RGB',(245,19),'white')
    monkeypatch.setattr(text_ocr,'publisher_images',lambda _: [(image,2)]*8)
    replies=iter(values)
    ocr=SimpleNamespace(lines=lambda *a,**k:[Line(next(replies),0,0,60,10)])
    if expected is None:
        with pytest.raises(ValueError):text_ocr.read_reference(ocr,image)
    else:assert text_ocr.read_reference(ocr,image)==expected

@pytest.mark.parametrize('field,wrong',[
    ('entry_type','TRANSFER'),('entry_amount','0.13'),('entry_reference','2026 03'),
])
def test_wrong_payment_field_prevents_all_save_clicks(field,wrong):
    d=RemoteDriver.__new__(RemoteDriver)
    d.expect=lambda _:None
    d.wait=lambda _:None
    values={'entry_type':'PAYMENT OF ROYALTIES','entry_amount':'-0.13','entry_reference':'2026 Q3'}
    values[field]=wrong
    d.text=lambda image,key:values[key]
    d.click=lambda *a:pytest.fail('Incorrect field must block save')
    with pytest.raises(PaymentNotSaved,match='expected'):
        d.commit_payment(Decimal('-.13'),'2026 Q3',Decimal('0'))

def test_two_fresh_frames_required_and_later_reference_change_stops():
    d=RemoteDriver.__new__(RemoteDriver)
    frames=[]
    def frame(_):frames.append(len(frames));return frames[-1]
    d.expect=frame;d.wait=lambda _:None
    def text(image,key):
        if key=='entry_reference':return '2026 Q3' if image==0 else '2026 03'
        return 'PAYMENT OF ROYALTIES' if key=='entry_type' else '-0.13'
    d.text=text
    with pytest.raises(PaymentNotSaved,match='Reference'):
        d.verify_payment_fields(Decimal('-.13'),'2026 Q3')
    assert len(frames)==2
