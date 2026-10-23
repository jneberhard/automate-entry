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
