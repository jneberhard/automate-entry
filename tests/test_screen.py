import json
import pytest
from royalty_entry.desktop import aligned_rows, ScreenError
from royalty_entry.ocr import Line
from royalty_entry.profile import DEFAULT, load_profile


def test_independent_column_rows_match_by_height():
    types = [Line('PAYMENT OF ROYALTIES', 1, 0, 200, 12), Line('TRANSFER', 1, 17, 80, 12)]
    amounts = [Line('-0.9', 1, 18, 24, 11), Line('-1.01', 1, 1, 30, 11)]
    rows = aligned_rows(types, amounts)
    assert rows[1][1].text == '-0.9'


def test_missing_or_ambiguous_amount_never_matches():
    left = [Line('TRANSFER', 1, 17, 80, 12)]
    with pytest.raises(ScreenError):
        aligned_rows(left, [])
    with pytest.raises(ScreenError):
        aligned_rows(left, [Line('-.9', 1, 40, 22, 12)])


def test_default_profile_and_invalid_coordinates(tmp_path):
    path = tmp_path/'profile.json'
    assert load_profile(path)['window_size'] == [1907, 1032]
    data = json.loads(json.dumps(DEFAULT))
    data['regions']['manager_title'] = [-1, 0, 12, 12]
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError):
        load_profile(path)
