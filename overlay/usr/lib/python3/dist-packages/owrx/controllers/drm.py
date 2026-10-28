from . import Controller
from urllib.request import Request, urlopen
import html
import re

class DrmScheduleController(Controller):
    SOURCE_URL = 'https://muromdx.com/resources/radioveshchanie-v-formate-drm'
    JINA_URL = 'https://r.jina.ai/http://muromdx.com/resources/radioveshchanie-v-formate-drm'

    def _get(self, url, timeout):
        req = Request(url, headers={'User-Agent': 'OpenWebRX+ DRM schedule'})
        return urlopen(req, timeout=timeout).read().decode('utf-8', 'replace')

    def _table_from_markdown(self, text):
        rows = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(('Title:', 'URL Source:', 'Published Time:', 'Markdown Content:')):
                continue
            line = re.sub(r'\*+', '', line).strip()
            match = re.match(r'^(\d{2}:\d{2}\s*[–-]\s*\d{2}:\d{2})\s+(.+)$', line)
            if not match:
                continue
            time = match.group(1)
            rest = match.group(2).strip()
            freqs = re.findall(r'(?<!\d)(\d{4,5})(?!\d)', rest)
            if not freqs:
                continue
            station = re.sub(r'(?<!\d)\d{4,5}(?!\d)', '', rest)
            station = re.sub(r'\s{2,}', ' ', station).strip()
            freq_html = ' '.join('<button type="button" class="owrx-drms-frequency" data-hz="{}">{}</button>'.format(int(freq) * 1000, html.escape(freq)) for freq in freqs)
            rows.append('<tr><td>{}</td><td>{}</td><td>{}</td></tr>'.format(html.escape(time), html.escape(station), freq_html))
        if not rows:
            raise RuntimeError('DRM schedule rows were not found')
        return '<table class="owrx-drms-table"><thead><tr><th>Время UTC</th><th>Станция / дни</th><th>Частоты, кГц</th></tr></thead><tbody>{}</tbody></table>'.format(''.join(rows))

    def indexAction(self):
        try:
            try:
                source = self._get(self.SOURCE_URL, 8)
                match = re.search(r'<table\b[^>]*>.*?</table>', source, re.IGNORECASE | re.DOTALL)
                if match:
                    self.send_response(match.group(0), content_type='text/html', max_age=120)
                    return
            except Exception:
                pass
            self.send_response(self._table_from_markdown(self._get(self.JINA_URL, 20)), content_type='text/html', max_age=120)
        except Exception as error:
            message = '<div class="owrx-drms-error">DRM schedule is temporarily unavailable: {}</div>'.format(html.escape(str(error)))
            self.send_response(message, code=502, content_type='text/html', max_age=30)
