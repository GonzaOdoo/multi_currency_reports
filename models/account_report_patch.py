from odoo import models
from odoo.addons.account_reports.models import account_report

def patched_set_xlsx_cell_sizes(self, sheet, fonts, x, y, value, style, is_merged=False):
    col = x
    row = y

    # Safely get the column width
    col_width_data = sheet.col_sizes.get(col, [8.43])
    col_width = col_width_data if isinstance(col_width_data, float) else col_width_data[0]

    value = str(value)
    content_width = len(value) + 2  # or any logic from original

    if col_width < content_width:
        sheet.col_sizes[col] = [content_width]

    if row not in sheet.row_sizes:
        sheet.row_sizes[row] = 15

# Monkey patch the method
account_report.AccountReport._set_xlsx_cell_sizes = patched_set_xlsx_cell_sizes
