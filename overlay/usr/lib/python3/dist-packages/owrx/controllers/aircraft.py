import json, math, time, threading
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen
from owrx.controllers import Controller
_cache = {}
_lock = threading.Lock()
_fi_lock = threading.Lock()
_fi_last = 0.0
SOURCES = {'adsb.lol':'https://api.adsb.lol/v2/point/{:.1f}/{:.1f}/250', 'adsb.fi':'https://opendata.adsb.fi/api/v3/lat/{:.1f}/lon/{:.1f}/dist/250'}
def fetch_source(name, lat, lon):
    global _fi_last
    def request():
        url = SOURCES[name].format(lat,lon)
        with urlopen(Request(url,headers={'User-Agent':'OpenWebRX AirMap contact sdr.evalcom.ru'}),timeout=8) as response:
            payload=json.loads(response.read(4000000))
        if not isinstance(payload.get('ac'),list): raise ValueError('Invalid response')
        return payload['ac']
    if name == 'adsb.fi':
        with _fi_lock:
            delay=1.1-(time.monotonic()-_fi_last)
            if delay>0: time.sleep(delay)
            _fi_last=time.monotonic()
            return request()
    return request()
def merge(results):
    merged={}
    for source, records in results.items():
        for item in records:
            if not isinstance(item,dict): continue
            ident=item.get('hex')
            if not isinstance(ident,str) or not ident.strip(): continue
            ident=ident.strip().lower()
            if ident not in merged:
                merged[ident]=dict(item);continue
            old=merged[ident]
            def age(a):
                value=a.get('seen_pos');return value if isinstance(value,(int,float)) and math.isfinite(value) and value>=0 else float('inf')
            valid_new=isinstance(item.get('lat'),(int,float)) and isinstance(item.get('lon'),(int,float))
            valid_old=isinstance(old.get('lat'),(int,float)) and isinstance(old.get('lon'),(int,float))
            if valid_new and (not valid_old or age(item)<age(old)):
                keep=dict(item)
                for k in ('flight','r','t','desc','ownOp'):
                    if not keep.get(k) and old.get(k): keep[k]=old[k]
                merged[ident]=keep
            else:
                for k in ('flight','r','t','desc','ownOp'):
                    if not old.get(k) and item.get(k): old[k]=item[k]
    return list(merged.values())
class AircraftController(Controller):
    def indexAction(self):
        try:
            lat=float(self.request.query['lat'][0]); lon=float(self.request.query['lon'][0])
            if not math.isfinite(lat) or not math.isfinite(lon) or abs(lat)>90 or abs(lon)>180: raise ValueError()
            lat=round(lat,1);lon=round(lon,1);key=(lat,lon)
        except (KeyError,IndexError,ValueError,TypeError):
            self.send_response('{"error":"Invalid coordinates"}',code=400,content_type='application/json',max_age=0);return
        with _lock:
            now=time.monotonic();cached=_cache.get(key)
            if cached and now-cached[0]<30:
                self.send_response(cached[1],content_type='application/json',max_age=0);return
            results={};failed=[]
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures={n:pool.submit(fetch_source,n,lat,lon) for n in SOURCES}
                for name,future in futures.items():
                    try: results[name]=future.result()
                    except Exception: failed.append(name)
            if not results:
                self.send_response('{"error":"Aircraft data temporarily unavailable"}',code=502,content_type='application/json',max_age=0);return
            data=json.dumps({'ac':merge(results),'sources':list(results),'unavailable':failed},separators=(',',':'))
            if len(_cache)>=100: _cache.clear()
            _cache[key]=(time.monotonic(),data)
        self.send_response(data,content_type='application/json',max_age=0)
