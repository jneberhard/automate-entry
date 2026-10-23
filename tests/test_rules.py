from decimal import Decimal
import pytest
from royalty_entry.rules import money, royalty_amount, license_text, Record


@pytest.mark.parametrize('text,expected', [
    ('-.25', '-0.25'), ('-0.9', '-0.90'), ('0', '0'), ('0.00', '0'),
    ('-0.01', '-0.01'), ('1,234.56', '1234.56'), ('(0.26)', '-0.26'),
    ('−.25', '-0.25'), ('0.5', '0.50')])
def test_application_amount_formats(text, expected):
    assert money(text) == Decimal(expected)


@pytest.mark.parametrize('text', ['', 'O.OO', '--.25', '0.001', 'NaN', 'Balance: 0.00', '1,23.00', '.'])
def test_uncertain_ocr_is_rejected(text):
    with pytest.raises(ValueError):
        money(text)


@pytest.mark.parametrize('transfer,payment', [('-0.26', '-0.27'), ('0', '-0.01'), ('-.25', '-.26'), ('-.90', '-.91'), ('.26', '.25')])
def test_transfer_minus_one_cent(transfer, payment):
    assert royalty_amount(Decimal(transfer)) == Decimal(payment)


def test_preserve_license_digits():
    assert license_text(1264577400.0) == '1264577400'
    assert license_text('001234') == '001234'
    assert license_text(1234, '000000') == '001234'
    assert Record(2, '123', ' Oxford  University PRESS ').key == ('123', 'oxford university press')


@pytest.mark.parametrize('value', [None, True, -2, 1.2, '=I2', 10**15])
def test_invalid_identifiers(value):
    with pytest.raises(ValueError):
        license_text(value)


def test_publisher_number_defines_duplicate_key():
    from royalty_entry.rules import Record,publisher_number
    assert publisher_number(' pub 832 ')=='PUB832'
    assert Record(2,'123','Name A','PUB832').key==Record(3,'123','Name B','PUB832').key
    assert Record(2,'123','Same','PUB832').key!=Record(3,'123','Same','PUB833').key
    with pytest.raises(ValueError): publisher_number('PUB83O')
