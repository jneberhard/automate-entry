from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re


CENT = Decimal('0.01')


def publisher_number(value):
    text = re.sub(r'\s+', '', str(value or '')).upper()
    if not re.fullmatch(r'(?:PUB\d+|PB1\d*)', text):
        raise ValueError('Publisher number must start with PUB or PB1 and contain only digits after the prefix')
    return text


def normalized(value: object) -> str:
    return ' '.join(str(value or '').split()).casefold()


def money(text: str) -> Decimal:
    """Accept the application's 0, -0.9 and -.25 formats; never guess OCR letters."""
    text = text.strip().replace('−', '-').replace('–', '-').replace(' ', '')
    if text.startswith('(') and text.endswith(')'):
        text = '-' + text[1:-1]
    if not re.fullmatch(r'-?(?:(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?|\.\d{1,2})', text):
        raise ValueError(f'Cannot read an exact monetary amount: {text!r}')
    try:
        result = Decimal(text.replace(',', ''))
    except InvalidOperation as exc:
        raise ValueError(f'Invalid amount: {text!r}') from exc
    if not result.is_finite():
        raise ValueError('Amount is not finite')
    return result


def royalty_amount(transfer: Decimal, balance: Decimal | None = None) -> Decimal:
    if not transfer.is_finite() or transfer != transfer.quantize(CENT):
        raise ValueError('Transfer must be a finite amount with whole cents')
    if transfer == 0:
        return -CENT
    if balance == -CENT:
        return transfer
    return transfer - CENT


def license_text(value: object, number_format: str = '') -> str:
    if isinstance(value, bool) or value is None:
        raise ValueError('Missing or invalid license number')
    if isinstance(value, (float, int)):
        if int(value) != value or value < 0 or value >= 10**15:
            raise ValueError('License must be an exact positive integer or text')
        text = str(int(value))
        if re.fullmatch(r'0+', number_format):
            text = text.zfill(len(number_format))
    else:
        text = str(value).strip()
    if not re.fullmatch(r'\d+', text):
        raise ValueError('License must contain digits only; formulas are not supported')
    return text


@dataclass(frozen=True)
class Record:
    row: int
    license: str
    publisher: str
    publisher_number: str = ''

    @property
    def key(self) -> tuple[str, str]:
        return self.license, normalized(self.publisher_number)
