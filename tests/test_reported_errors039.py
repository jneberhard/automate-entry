from types import SimpleNamespace
from PIL import Image
import pytest
from royalty_entry.desktop import RemoteDriver,ScreenError
from royalty_entry.profile import DEFAULT
from royalty_entry.rules import Record


def test_properties_title_crop_preserves_first_digit_without_changing_other_fields():
    driver=RemoteDriver.__new__(RemoteDriver);driver.profile=DEFAULT
    image=Image.new('RGB',tuple(DEFAULT['window_size']),'white')
    left,top,right,bottom=DEFAULT['regions']['properties_title']
    image.putpixel((left-2,top+5),(0,0,0))
    cropped=driver.crop(image,'properties_title')
    assert cropped.width==right-left+4
    assert cropped.getpixel((2,5))==(0,0,0)
    region=DEFAULT['regions']['general_license']
    assert driver.crop(image,'general_license').size==(region[2]-region[0],region[3]-region[1])

@pytest.mark.parametrize('title,expected',[
    ('1505673315 - Peaches Properties','general'),
    ('1505673316 - Peaches Properties',None),
    ('| 505673315 - Peaches Properties',None),
])
def test_title_must_still_match_the_complete_expected_license(title,expected):
    driver=RemoteDriver.__new__(RemoteDriver)
    driver.record=Record(2,'1505673315','Display name','PB1558')
    driver.text=lambda image,key:title if key=='properties_title' else ''
    if expected is None:
        with pytest.raises(ScreenError,match='Properties belongs to another license: expected'):
            driver.state(None)
    else:assert driver.state(None)==expected

@pytest.mark.parametrize('license_number,code',[('1505673316','PB1558'),('1505673315','PB1559')])
def test_title_fix_does_not_bypass_opened_identity_checks(monkeypatch,license_number,code):
    from royalty_entry import identity_ocr
    driver=RemoteDriver.__new__(RemoteDriver);driver.profile=DEFAULT;driver.ocr=object()
    driver.crop=lambda *args:None
    monkeypatch.setattr(identity_ocr,'read_identity',lambda ocr,image,kind:license_number if kind=='license' else code)
    with pytest.raises(ScreenError):
        driver.verify_open_identity(Record(2,'1505673315','Display','PB1558'),None)
