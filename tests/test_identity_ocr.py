from types import SimpleNamespace
from PIL import Image
import pytest
from royalty_entry import identity_ocr
from royalty_entry.ocr import Line


def reader(monkeypatch, values):
    monkeypatch.setattr(identity_ocr, 'publisher_images', lambda _: [])
    monkeypatch.setattr(identity_ocr, 'publisher_code_images', lambda _: [])
    image = Image.new('RGB', (300, 21))
    stream = iter(values)
    monkeypatch.setattr(identity_ocr, 'amount_images', lambda _: [(image, 4)]*(len(values)-1))
    ocr = SimpleNamespace(text=lambda _: next(stream),
                          lines=lambda *args, **kwargs: [Line(next(stream), 0, 0, 30, 10)])
    return ocr, image


def test_border_outlier_and_spaced_digits_need_independent_exact_agreement(monkeypatch):
    ocr, image = reader(monkeypatch, ['11264806917', '1264806917', '12648069 17', '', 'I264806917'])
    assert identity_ocr.read_identity(ocr, image, 'license') == '1264806917'


@pytest.mark.parametrize('values', [
    ['', '', ''], ['I264806917', 'I264806917', ''],
    ['1264806917', '', '126480691'],
    ['1264806917', '1264806917', '1264806918', '1264806918'],
])
def test_unreadable_or_conflicting_licenses_stop(values, monkeypatch):
    ocr, image = reader(monkeypatch, values)
    with pytest.raises(ValueError):
        identity_ocr.read_identity(ocr, image, 'license')


def test_publisher_code_is_removed_but_name_and_punctuation_remain_exact(monkeypatch):
    ocr, image = reader(monkeypatch, ['PUB297 - Birnamwood Publications', 'PUB 297 – BIRNAMWOOD Publications', ''])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'birnamwood publications'
    ocr, image = reader(monkeypatch, ['PUB3 - Word Music, Inc.', 'PUB3 - Word Music, Inc.'])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'word music, inc.'


def test_confirmed_different_publishers_are_not_fuzzily_merged(monkeypatch):
    ocr, image = reader(monkeypatch, ['PUB1 - Music A', 'PUB1 - Music A', 'PUB2 - Music B', 'PUB2 - Music B'])
    with pytest.raises(ValueError):
        identity_ocr.read_identity(ocr, image, 'publisher')


def test_split_u_in_publisher_code_does_not_change_publisher_name(monkeypatch):
    ocr, image = reader(monkeypatch, ['PIJB297 - Birnamwood Publications',
                                    'PLIB297 - Birnamwood Publications',
                                    'PUB297 - Birnamwood Publications'])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'birnamwood publications'


def test_publisher_requires_unique_repeated_winner_without_changing_name(monkeypatch):
    ocr, image = reader(monkeypatch, ['5 - Word Music, Inc.'] +
                        ['PUB775 - Word Music, Inc.']*4 + ['PUB775 - Word Musiq Inc.']*2)
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'word music, inc.'


def test_three_exact_publisher_reads_beat_split_ocr_errors(monkeypatch):
    ocr, image = reader(monkeypatch, ['PUB694 - B-Day Publishing']*3 +
                        ['PUB694 - a-Day Publishing']*2 + ['PUB694 - Publishing', 'PUBC4 - Publishing'])
    assert identity_ocr.read_identity(ocr, image, 'publisher') == 'b-day publishing'


def test_full_field_lower_magnification_recovers_exact_publisher(monkeypatch):
    values = ['PUB832 - Sony/ATV songs LLC obo Tre Ball Music',
              "PUB832 - Sony/ATv' songs LLC 0b0 Tre Ball Music",
              'PUB832 - Sony/ATV songs LLC 0b0 Tre Ball Music']
    ocr, image = reader(monkeypatch, values + ['PUB832 - Sony/ATV songs LLC obo Tre Ball Music']*4)
    monkeypatch.setattr(identity_ocr, 'amount_images', lambda _: [(image,4)]*2)
    monkeypatch.setattr(identity_ocr, 'publisher_images', lambda _: [(image,2)]*4)
    assert identity_ocr.read_identity(ocr,image,'publisher') == 'sony/atv songs llc obo tre ball music'


@pytest.mark.parametrize('text,x,width,expected', [
    ('Universal Music Corp. OBO Bieber Time Publish',0,250,True),
    ('Universal Music Corp.',0,120,False),
    ('Universal Music Corp. OBO Bieber Time Publish',0,180,False),
    ('Universal Music Corp. OBO Different Publisher',0,250,False),
])
def test_only_clipped_exact_prefixes_are_candidates(text,x,width,expected):
    assert identity_ocr.clipped_publisher_candidate(Line(text,x,0,width,10),
        'UNIVERSAL MUSIC CORP. OBO BIEBER TIME PUBLISHING',252) is expected


@pytest.mark.parametrize('code', ['PUB832','PB1395'])
def test_publisher_number_is_read_without_relying_on_name(code,monkeypatch):
    ocr,image=reader(monkeypatch,[code+' - Unreadable name',code+' - Different OCR spelling','PUB632 - Other'])
    assert identity_ocr.read_identity(ocr,image,'publisher_number')==code


def test_different_publisher_numbers_never_merge(monkeypatch):
    ocr,image=reader(monkeypatch,['PUB832 - Name','PUB832 - Name','PUB833 - Name','PUB833 - Name'])
    with pytest.raises(ValueError): identity_ocr.read_identity(ocr,image,'publisher_number')


def test_reported_pub824_case_resolves_repeated_ocr_outliers(monkeypatch):
    values=['PUB824 - UNIVERSAL MUSIC CORP.']*3 + ['PUBS24 - UNIVERSAL MUSIC CORP.',
        'PUB824 - UNIVERSAL MUSIC CORP.','PUB624 - UNIVQSAL MUSIC CORP.',
        'PUB624 - UNIVERSAL MUSIC CORP.'] + ['PUB824 - UNIVERSAL MUSIC CORP.']*8
    ocr,image=reader(monkeypatch,values)
    assert identity_ocr.read_identity(ocr,image,'publisher_number')=='PUB824'


@pytest.mark.parametrize('values',[
    ['PUB824 - A']*3+['PUB624 - B']*2,
    ['PUB824 - A']*6+['PUB624 - B']*2,
    ['PUB824 - A']*4+['PUB624 - B']*4,
    ['PUBS24 - A']*15,
])
def test_weak_or_invalid_code_consensus_still_stops(values,monkeypatch):
    ocr,image=reader(monkeypatch,values)
    with pytest.raises(ValueError): identity_ocr.read_identity(ocr,image,'publisher_number')


def test_clear_publisher_code_uses_four_reads_without_slow_fallback(monkeypatch):
    image=Image.new('RGB',(300,21),'white')
    monkeypatch.setattr(identity_ocr,'publisher_images',lambda _: [(image,2)]*4)
    calls=[]
    def recognize(*a,**kw):
        calls.append(kw['scale'])
        return [Line('PUB824 - Display name',0,0,100,10)]
    def forbidden(*args):pytest.fail('Clear code should not need slow fallback')
    ocr=SimpleNamespace(lines=recognize,text=forbidden)
    assert identity_ocr.read_identity(ocr,image,'publisher_number')=='PUB824'
    assert len(calls)==4


def test_disagreeing_fast_reads_use_full_reader_instead_of_shortcut(monkeypatch):
    image=Image.new('RGB',(300,21),'white')
    monkeypatch.setattr(identity_ocr,'publisher_images',lambda _: [(image,2)]*4)
    monkeypatch.setattr(identity_ocr,'publisher_code_images',lambda _: [])
    monkeypatch.setattr(identity_ocr,'amount_images',lambda _: [(image,4)]*6)
    replies=iter(['PUB824 - Name']*3+['PUB624 - Name']+['PUB624 - Name']*10)
    ocr=SimpleNamespace(lines=lambda *a,**kw:[Line(next(replies),0,0,100,10)],text=lambda _: 'PUB624 - Name')
    assert identity_ocr.read_identity(ocr,image,'publisher_number')=='PUB624'


def test_isolated_code_recovers_reported_pub485_without_digit_substitution(monkeypatch):
    image=Image.new('RGB',(300,21),'white')
    monkeypatch.setattr(identity_ocr,'publisher_images',lambda _: [(image,2)]*4)
    monkeypatch.setattr(identity_ocr,'publisher_code_images',lambda _: [(image,3)]*4)
    replies=iter(['PIJB4S5 - Universal Music']*4+['PUB485 - Univt']*4)
    def forbidden(*args):pytest.fail('Unanimous isolated code needs no full-field fallback')
    ocr=SimpleNamespace(lines=lambda *a,**kw:[Line(next(replies),0,0,100,10)],text=forbidden)
    assert identity_ocr.read_identity(ocr,image,'publisher_number')=='PUB485'


@pytest.mark.parametrize('isolated',[
    ['PUB485 -']*3+['PUB465 -'],
    ['PUB4S5 -']*4,
    ['PUB485']*4,  # No separator: a longer code may have been clipped.
    ['PUB485 -']*3+[''],
])
def test_isolated_code_ambiguity_or_clipping_still_uses_full_reader(monkeypatch,isolated):
    image=Image.new('RGB',(300,21),'white')
    monkeypatch.setattr(identity_ocr,'publisher_images',lambda _: [(image,2)]*4)
    monkeypatch.setattr(identity_ocr,'publisher_code_images',lambda _: [(image,3)]*4)
    monkeypatch.setattr(identity_ocr,'amount_images',lambda _: [])
    replies=iter(['PIJB4S5 - Name']*4+isolated+['PUB465 - Name']*4)
    ocr=SimpleNamespace(lines=lambda *a,**kw:[Line(next(replies),0,0,100,10)],text=lambda _: 'PUB465 - Name')
    assert identity_ocr.read_identity(ocr,image,'publisher_number')=='PUB465'
