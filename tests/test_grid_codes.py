import pytest
from royalty_entry.ocr import Line
from royalty_entry.grid_codes import publisher_codes,align_code_candidates


@pytest.mark.parametrize('x',[100,700])
def test_codes_are_found_independent_of_column_position(x):
    words=[Line('Publisher',0,0,50,10),Line('Name',60,0,30,10),
           Line('PUB826',x,20,40,10),Line('Active',x+100,20,30,10),
           Line('PB1395',x,37,40,10),Line('Standard',x+100,37,50,10)]
    assert [c.text for c in publisher_codes(words)]==['PUB826','PB1395']


def test_split_prefix_and_digits_keep_row_identity():
    words=[Line('PUB',10,20,20,10),Line('832',32,20,20,10),Line('1395',32,50,20,10)]
    assert [c.text for c in publisher_codes(words)]==['PUB832']


@pytest.mark.parametrize('prefix',['PIJB','PLIB','PLJB'])
def test_split_u_in_prefix_keeps_exact_digits(prefix):
    assert [c.text for c in publisher_codes([Line(prefix+'544',0,20,45,10)])]==['PUB544']
    assert [c.text for c in publisher_codes([Line(prefix,0,20,20,10),Line('544',22,20,20,10)])]==['PUB544']
    assert publisher_codes([Line(prefix+'S44',0,20,45,10)])==[]


def test_exact_readings_from_different_passes_fill_only_their_own_rows():
    licenses=[Line('123',0,20,30,10),Line('123',0,37,30,10)]
    readings=[Line('PUB824',700,20,40,10),Line('PB1395',700,37,40,10),Line('PB1395',700,37,40,10)]
    assert [c.text for _,c in align_code_candidates(licenses,readings)]==['PUB824','PB1395']


@pytest.mark.parametrize('codes',[
    [Line('PUB824',700,20,40,10),Line('PUB826',700,20,40,10)],
    [Line('PUB824',700,37,40,10)],
    [],
])
def test_conflicts_missing_and_unmatched_rows_are_rejected(codes):
    with pytest.raises(ValueError):align_code_candidates([Line('123',0,20,30,10)],codes)


def test_extra_code_without_a_license_row_is_rejected():
    with pytest.raises(ValueError):align_code_candidates([Line('123',0,20,30,10)],
        [Line('PUB824',700,20,40,10),Line('PUB826',700,50,40,10)])

def test_unhighlight_keeps_row_positions_and_unselected_rows():
    from PIL import Image,ImageDraw
    from royalty_entry.grid_codes import unhighlight_grid
    image=Image.new('RGB',(200,60),'white')
    draw=ImageDraw.Draw(image)
    draw.rectangle((0,10,199,25),fill=(0,120,215))
    draw.rectangle((20,14,45,20),fill='white')
    draw.rectangle((20,40,45,46),fill='black')
    fixed=unhighlight_grid(image)
    assert fixed.getpixel((25,16))==(0,0,0)
    assert fixed.getpixel((5,16))==(255,255,255)
    assert fixed.crop((0,30,200,60)).tobytes()==image.crop((0,30,200,60)).tobytes()


def test_highlight_retry_aligns_recovered_code_to_original_license_row():
    from types import SimpleNamespace
    from PIL import Image
    from royalty_entry.desktop import RemoteDriver
    from royalty_entry.profile import DEFAULT
    d=RemoteDriver.__new__(RemoteDriver);d.profile=DEFAULT
    d.crop=lambda *a: Image.new('RGB',(150,40),'white')
    d.publisher_grid=lambda _: Image.new('RGB',(880,40),(0,120,215))
    replies=iter([[],[],[],[Line('PUB544',700,4,45,10)]]*1+
                 [[Line('PUB544',700,4,45,10)]]*2)
    d.ocr=SimpleNamespace(lines=lambda *a:[Line('1265484733',0,4,80,10)],words=lambda *a,**k:next(replies))
    rows=d.table(None,'result_licenses','result_publisher_numbers')
    assert [(a.text,b.text) for a,b in rows]==[('1265484733','PUB544')]

@pytest.mark.parametrize('readings,expected',[
    (['PUB485']*4,['PUB485']),
    (['PUB485','PUB486','PUB485','PUB486'],[]),
    (['PUB4S5']*4,[]),
])
def test_missing_cell_is_read_in_its_own_row_without_guessing(readings,expected):
    from PIL import Image
    from types import SimpleNamespace
    from royalty_entry.grid_codes import recover_code_cells
    licenses=[Line('123',0,y,60,10) for y in (4,21,38)]
    anchors=[Line('PUB485',708,4,37,10),Line('PUB690',708,38,37,10)]
    stream=iter(readings);sizes=[]
    def words(image,**kw):
        sizes.append(image.size)
        return [Line(next(stream),19,20,37,9)]
    got=recover_code_cells(SimpleNamespace(words=words),Image.new('RGB',(880,100),'white'),licenses,anchors)
    assert [line.text for line in got]==expected
    if got:assert got[0].y==21
    assert len(sizes)==4 and all(height<=48 for width,height in sizes)


def test_missing_cell_does_not_infer_a_column_or_replace_existing_conflicts():
    from PIL import Image
    from types import SimpleNamespace
    from royalty_entry.grid_codes import recover_code_cells
    def forbidden(*a,**k):pytest.fail('No unambiguous column or missing cell to read')
    ocr=SimpleNamespace(words=forbidden)
    licenses=[Line('123',0,4,60,10)]
    grid=Image.new('RGB',(880,100),'white')
    assert recover_code_cells(ocr,grid,licenses,[])==[]
    conflicting=[Line('PUB485',708,4,37,10),Line('PUB486',708,4,37,10)]
    assert recover_code_cells(ocr,grid,licenses,conflicting)==[]
    with pytest.raises(ValueError):align_code_candidates(licenses,conflicting)


@pytest.mark.parametrize('code,expected',[('PUB485',True),('PB1395',True),('PB1',True),('PB290',False),('PB832',False),('PUB4S5',False)])
def test_only_pub_or_pb1_prefixes_and_exact_digits_are_accepted(code,expected):
    from royalty_entry.rules import publisher_number
    assert bool(publisher_codes([Line(code,10,20,45,10)])) is expected
    if expected:assert publisher_number(code)==code
    else:
        with pytest.raises(ValueError):publisher_number(code)
