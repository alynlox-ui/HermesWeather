#!/usr/bin/env python3
import gzip, hashlib, json, mimetypes, threading, webbrowser, time
from news_crawler import fetch_article
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs,urlparse,urlencode
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError
ROOT=Path(__file__).parent

ALIASES={'纽约':'New York','洛杉矶':'Los Angeles','旧金山':'San Francisco','华盛顿':'Washington','伦敦':'London','巴黎':'Paris','东京':'Tokyo','大阪':'Osaka','首尔':'Seoul','莫斯科':'Moscow','悉尼':'Sydney','墨尔本':'Melbourne','新加坡':'Singapore','曼谷':'Bangkok','迪拜':'Dubai','罗马':'Rome','柏林':'Berlin','马德里':'Madrid','温哥华':'Vancouver','多伦多':'Toronto'}
def get(url,p):
 last=None
 for attempt in range(2):
  try:
   req=Request(url+'?'+urlencode(p),headers={'User-Agent':'HermesWeatherWeb/2.1','Accept':'application/json'})
   with urlopen(req,timeout=12) as r:return json.load(r)
  except Exception as e:
   last=e
   if attempt<1:time.sleep(.5)
 raise RuntimeError('无法连接 Open-Meteo 天气服务，请检查网络或稍后重试')
def geocode(term,language='zh'):
 return get('https://geocoding-api.open-meteo.com/v1/search',{'name':term,'count':20,'language':language,'format':'json'}).get('results',[])

def weather(city):
 raw=city.strip()
 if not raw:raise ValueError('地点名称不能为空')
 # 支持“省/市/区/镇”、空格、逗号等层级写法；末级作为查询目标，上级用于消除同名地点。
 parts=[x.strip() for x in __import__('re').split(r'[/,，>\s]+',raw) if x.strip()]
 target=parts[-1]
 stripped=target
 for suffix in ('自治县','自治州','新区','街道','地区','区','县','市','镇','乡'):
  if stripped.endswith(suffix) and len(stripped)>len(suffix):stripped=stripped[:-len(suffix)];break
 query=ALIASES.get(target,target)
 terms=[]
 for x in (query,target,stripped):
  if x and x not in terms:terms.append(x)
 results=[]
 for term in terms:
  languages=['en','zh'] if term!=target and term in ALIASES.values() else ['zh','en']
  for language in languages:
   rows=geocode(term,language)
   if rows:results.extend(rows);break
 # 某些区镇仅能通过拼音/英文检索；仍找不到时给出明确格式提示。
 if not results:raise ValueError(f'找不到“{raw}”。区或镇请尝试“上级城市/区镇名”，如“北京/海淀”或输入拼音')
 # 去重并根据用户给出的省市区上下文、精确名称、人口进行排序。
 unique={}
 for x in results:unique[(x.get('latitude'),x.get('longitude'))]=x
 contexts=[x.lower().replace('省','').replace('市','').replace('区','').replace('县','').replace('镇','') for x in parts[:-1]]
 def score(x):
  fields=' '.join(str(x.get(k) or '') for k in ('name','admin1','admin2','admin3','country')).lower()
  context_score=sum(100000000 for c in contexts if c and c in fields)
  name=str(x.get('name') or '').lower()
  exact=300000000 if name in (target.lower(),stripped.lower(),query.lower()) else 0
  feature=50000000 if str(x.get('feature_code','')).startswith(('PPL','ADM')) else 0
  return context_score+exact+feature+(x.get('population') or 0)
 q=max(unique.values(),key=score)
 d=get('https://api.open-meteo.com/v1/forecast',{'latitude':q['latitude'],'longitude':q['longitude'],'current':'temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,precipitation','daily':'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunset','timezone':'auto','forecast_days':7})
 return {'place':q,'data':d,'query':raw}

class H(BaseHTTPRequestHandler):
 article_slots=threading.BoundedSemaphore(4)
 article_rate_lock=threading.Lock()
 article_rate={}
 def allow_article_request(self):
  now=time.monotonic();client=self.client_address[0]
  with self.article_rate_lock:
   recent=[stamp for stamp in self.article_rate.get(client,[]) if now-stamp<60]
   if len(recent)>=20:return False
   recent.append(now);self.article_rate[client]=recent
  return True
 def sendj(self,obj,status=200):
  b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Methods','GET, HEAD, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',len(b));self.end_headers();self.wfile.write(b)
 def send_static(self,path,content_type,cache_seconds):
  raw=path.read_bytes();etag='"'+hashlib.sha256(raw).hexdigest()[:24]+'"'
  if self.headers.get('If-None-Match')==etag:
   self.send_response(304);self.send_header('ETag',etag);self.send_header('Cache-Control',f'public, max-age={cache_seconds}, stale-while-revalidate=86400');self.end_headers();return
  use_gzip='gzip' in self.headers.get('Accept-Encoding','').lower();body=gzip.compress(raw,compresslevel=6) if use_gzip else raw
  self.send_response(200);self.send_header('Content-Type',content_type);self.send_header('Cache-Control',f'public, max-age={cache_seconds}, stale-while-revalidate=86400');self.send_header('ETag',etag);self.send_header('Vary','Accept-Encoding');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Access-Control-Allow-Origin','*')
  if use_gzip:self.send_header('Content-Encoding','gzip')
  self.send_header('Content-Length',len(body));self.end_headers()
  if self.command!='HEAD':self.wfile.write(body)
 def do_OPTIONS(self):
  self.send_response(204);self.send_header('Access-Control-Allow-Origin','*');self.send_header('Access-Control-Allow-Methods','GET, HEAD, OPTIONS');self.send_header('Access-Control-Allow-Headers','Content-Type');self.end_headers()
 def do_HEAD(self):self.do_GET()
 def do_GET(self):
  u=urlparse(self.path)
  if u.path=='/api/weather':
    try:self.sendj(weather(parse_qs(u.query).get('city',['北京'])[0]))
    except Exception as e:self.sendj({'error':str(e)},400)
  elif u.path=='/api/news/article':
   acquired=False
   try:
    if not self.allow_article_request():return self.sendj({'error':'请求过于频繁，请稍后重试'},429)
    acquired=self.article_slots.acquire(blocking=False)
    if not acquired:return self.sendj({'error':'正文抓取繁忙，请稍后重试'},429)
    target=parse_qs(u.query).get('url',[''])[0]
    if not target: raise ValueError('新闻网址不能为空')
    self.sendj(fetch_article(target))
   except Exception as e:self.sendj({'error':str(e)},400)
   finally:
    if acquired:self.article_slots.release()
  elif u.path=='/health':
   self.sendj({'status':'ok','service':'hermes-weather-web','crawlerRevision':'web-1.9.0-study-goals'})
  elif u.path in ('/','/index.html'):
   self.send_static(ROOT/'index.html','text/html; charset=utf-8',300)
  elif u.path=='/study-goal-tracker.html':
   self.send_static(ROOT/'study-goal-tracker.html','text/html; charset=utf-8',300)
  elif u.path=='/hot-news.json':
   self.send_static(ROOT/'hot-news.json','application/json; charset=utf-8',300)
  else:self.send_error(404)
 def log_message(self,*a):pass
if __name__=='__main__':
 host='127.0.0.1';s=None
 for port in range(8765,8776):
  try:s=ThreadingHTTPServer((host,port),H);break
  except OSError:continue
 if s is None:
  print('启动失败：8765-8775 端口均被占用。');input('按回车键退出…');raise SystemExit(1)
 url=f'http://{host}:{port}';print('Hermes Weather 已启动：'+url);threading.Timer(.7,lambda:webbrowser.open(url)).start()
 try:s.serve_forever()
 except KeyboardInterrupt:pass
 finally:s.server_close()
