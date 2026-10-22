from openpyxl import Workbook as ExcelFile, load_workbook
from royalty_entry.workbook import Workbook, sheet_names


def test_reads_only_selected_sheet_columns_h_i_and_retains_identifiers(tmp_path):
    path = tmp_path/'source.xlsx'
    book = ExcelFile()
    book.active.title = 'Other'
    sheet = book.create_sheet('Payments')
    sheet['H1'], sheet['I1'] = 'Publisher', 'License'
    sheet['H2'], sheet['I2'] = 'Publisher A', '00123'
    sheet['H3'], sheet['I3'] = 'Publisher B', 456
    sheet['I3'].number_format = '000000'
    sheet['H4'], sheet['I4'] = 'Publisher C', '=I3'
    book.save(path)
    before = path.read_bytes()
    selected = Workbook(path, 'Payments', 2)
    assert [r.license for r in selected.records] == ['00123', '000456']
    assert selected.invalid[0][0] == 4
    assert sheet_names(path) == ['Other', 'Payments']
    copy = tmp_path/'copy.xlsx'
    selected.save_filtered(copy, set())
    assert path.read_bytes() == before
    assert load_workbook(copy)['Payments']['I2'].value == '00123'
