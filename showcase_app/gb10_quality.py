"""Lossless comparisons for the original fictional vision fixtures."""
import json
import re


def normalized(value):
    if isinstance(value, str):
        return value.strip().casefold()
    if isinstance(value, list):
        return [normalized(item) for item in value]
    if isinstance(value, dict):
        return {key: normalized(item) for key, item in value.items()}
    return value


def canonical_table(value):
    """Accept named or positional rows while comparing every extracted cell."""
    if not isinstance(value, dict) or not isinstance(value.get('columns'), list) or not isinstance(value.get('rows'), list):
        raise ValueError('Expected columns and rows')
    metadata = value['columns']
    if any(isinstance(item, dict) for item in metadata):
        if not all(isinstance(item, dict) and isinstance(item.get('name'), str) for item in metadata):
            raise ValueError('Invalid column metadata')
        columns = [item['name'].strip().casefold() for item in metadata]
    else:
        columns = [str(item).strip().casefold() for item in metadata]
    if len(set(columns)) != len(columns):
        raise ValueError('Duplicate columns')
    rows = []
    for row in value['rows']:
        if isinstance(row, dict):
            row = {str(key).strip().casefold(): cell for key, cell in row.items()}
            if set(row) != set(columns):
                raise ValueError('Row fields differ from columns')
            row = [row[column] for column in columns]
        if not isinstance(row, list) or len(row) != len(columns):
            raise ValueError('Wrong row width')
        cells = []
        for cell in row:
            if isinstance(cell, str):
                cell = cell.strip().casefold()
                if re.fullmatch(r'-?\d+', cell):
                    cell = int(cell)
                elif re.fullmatch(r'-?\d+\.\d+', cell):
                    cell = float(cell)
            cells.append(cell)
        rows.append(cells)
    for index, column in enumerate(metadata):
        if isinstance(column, dict) and 'values' in column:
            if normalized(column['values']) != normalized([row[index] for row in rows]):
                raise ValueError('Column values disagree with row values')
    return {'columns': columns, 'rows': rows}


def extraction_matches(filename, actual, truth):
    if filename.startswith('chart'):
        try:
            return canonical_table(actual) == canonical_table(truth)
        except ValueError:
            return False
    actual, truth = normalized(actual), normalized(truth)
    if not isinstance(actual, list) or not all(isinstance(item, dict) for item in actual):
        return False
    return sorted(actual, key=lambda item: json.dumps(item, sort_keys=True)) == sorted(truth, key=lambda item: json.dumps(item, sort_keys=True))


