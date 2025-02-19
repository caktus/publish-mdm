import tablib
from import_export.formats import base_formats


class XLSX(base_formats.XLSX):
    def create_dataset(self, in_stream):
        """
        Create dataset from first sheet.

        We override this to pad rows to the right with None values and to skip
        empty rows. This avoids `tablib.exceptions.InvalidDimensions` exceptions
        during imports, which seems to occur when an otherwise valid xlsx import
        file is edited in Google Sheets.
        """
        from io import BytesIO

        import openpyxl

        # 'data_only' means values are read from formula cells, not the formula itself
        xlsx_book = openpyxl.load_workbook(BytesIO(in_stream), read_only=True, data_only=True)

        dataset = tablib.Dataset()
        sheet = xlsx_book.active

        # obtain generator
        rows = sheet.rows
        dataset.headers = [cell.value for cell in next(rows)]

        for index, row in enumerate(rows):
            if not row:
                # Skip empty row
                continue
            row_values = [cell.value for cell in row]
            if len(row_values) < dataset.width:
                # Pad to the right with None values
                row_values += [None] * (dataset.width - len(row_values))
            dataset.append(row_values)
        return dataset
