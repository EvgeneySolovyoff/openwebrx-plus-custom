"""Structured, cached schedules from novosibdx.info for the RusCH panel."""
import json
import re
import time
from html.parser import HTMLParser
from urllib.request import Request, urlopen

from . import Controller

SOURCE_URL = 'https://www.novosibdx.info/schedules.html'
_CACHE = {'time': 0, 'sections': None}


def clean(value):
    return re.sub(r's+', ' ', value).strip()


class ScheduleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.sections = []
        self.heading = ''
        self.heading_parts = None
        self.depth = 0
        self.rows = None
        self.row = None
        self.cell_parts = None
        self.cell_span = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('script', 'style'):
            self.skip += 1
            return
        if self.skip:
            return
        if tag == 'p' and self.depth == 0 and 'стиль13' in attrs.get('class', ''):
            self.heading_parts = []
        if tag == 'table':
            self.depth += 1
            if self.depth == 1:
                self.rows = []
        elif tag == 'tr' and self.depth == 1:
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell_parts = []
            self.cell_span = {}
            for key, maximum in (('rowspan', 50), ('colspan', 10)):
                try:
                    value = int(attrs.get(key, '1'))
                    if 1 < value <= maximum:
                        self.cell_span[key] = value
                except ValueError:
                    pass
        elif tag == 'br' and self.cell_parts is not None:
            self.cell_parts.append(' / ')

    def handle_data(self, data):
        if self.skip:
            return
        if self.heading_parts is not None:
            self.heading_parts.append(data)
        if self.cell_parts is not None:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == 'p' and self.heading_parts is not None:
            value = clean(''.join(self.heading_parts))
            if value:
                self.heading = value
            self.heading_parts = None
        elif tag in ('td', 'th') and self.cell_parts is not None:
            cell = {'text': clean(''.join(self.cell_parts))}
            cell.update(self.cell_span)
            self.row.append(cell)
            self.cell_parts = None
            self.cell_span = None
        elif tag == 'tr' and self.row is not None:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif tag == 'table' and self.depth:
            if self.depth == 1 and self.rows:
                header = ' '.join(cell['text'] for cell in self.rows[0])
                if 'Время UTC' in header and 'кГц' in header:
                    self.sections.append({'title': self.heading or 'Расписание', 'rows': self.rows})
                self.rows = None
            self.depth -= 1


def normalize_sections(source_sections):
    """Expand source row spans, keep shortwave rows, and align five columns."""
    result = []
    headers = ('Время UTC', 'Частота, кГц', 'Передатчик', 'кВт', 'Направление / азимут')
    for section in source_sections:
        rows = [[{'text': value} for value in headers]]
        occupied = {}
        previous = [''] * 6
        for row_number, row in enumerate(section['rows'][1:]):
            values = [''] * 6
            for column, (until, text) in occupied.items():
                if until > row_number:
                    values[column] = text
            column = 0
            for cell in row:
                while column < 6 and occupied.get(column, (0, ''))[0] > row_number:
                    column += 1
                if column >= 6:
                    break
                span = max(1, min(int(cell.get('colspan', 1)), 6 - column))
                text = cell['text']
                for covered in range(column, column + span):
                    values[covered] = text
                    if int(cell.get('rowspan', 1)) > 1:
                        occupied[covered] = (row_number + int(cell['rowspan']), text)
                column += span
            for inherited in (0, 3, 4, 5):
                if not values[inherited]:
                    values[inherited] = previous[inherited]
            previous = values
            frequencies = [int(value) for value in re.findall('[0-9]{3,5}', values[2])]
            frequencies = [value for value in frequencies if value >= 3000]
            if not frequencies:
                continue
            values[2] = ', '.join(map(str, frequencies))
            rows.append([{'text': values[index]} for index in (0, 2, 3, 4, 5)])
        if len(rows) > 1:
            result.append({'title': section['title'], 'rows': rows})
    return result


class NovosibDxScheduleController(Controller):
    def indexAction(self):
        sections = _CACHE['sections']
        if sections is None or time.time() - _CACHE['time'] > 600:
            try:
                request = Request(SOURCE_URL, headers={'User-Agent': 'OpenWebRX+ RusCH schedule'})
                with urlopen(request, timeout=12) as response:
                    page = response.read(1024 * 1024).decode('cp1251', 'replace')
                parser = ScheduleParser()
                parser.feed(page)
                if not parser.sections:
                    raise ValueError('No schedule tables found')
                sections = normalize_sections(parser.sections)
                _CACHE.update(time=time.time(), sections=sections)
            except Exception:
                if sections is None:
                    self.send_response(json.dumps({'error': 'Расписание временно недоступно'}, ensure_ascii=False), code=502, content_type='application/json', max_age=0)
                    return
        payload = {'source': SOURCE_URL, 'sections': sections}
        self.send_response(json.dumps(payload, ensure_ascii=False), content_type='application/json', max_age=0)
