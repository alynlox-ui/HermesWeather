from __future__ import annotations
import base64, html, json, re, shutil, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path
from news_crawler import fetch_bilibili_video
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parent
EDGE=Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
GH=Path(r"C:\Program Files\GitHub CLI\gh.exe")
REPO="alynlox-ui/HermesWeather"
NEWSNOW="https://newsnow.busiyi.world/api/s?id="
DOMESTIC={"thepaper":"thepaper","bilibili":"bilibili-hot-search"}
QBITAI_API="https://www.qbitai.com/wp-json/wp/v2/posts?per_page=30&_embed=1"
K36_PAGE="https://m.36kr.com/newsflashes"
def edge_dom(source,url):
 profile=ROOT/".hot-news-fetch-profile"/source;shutil.rmtree(profile,ignore_errors=True)
 r=subprocess.run([str(EDGE),"--headless=new","--disable-gpu","--no-first-run","--disable-extensions",f"--user-data-dir={profile}","--dump-dom",url],capture_output=True,timeout=75)
 if r.returncode:raise RuntimeError(f"Edge fetch failed ({r.returncode})")
 return r.stdout.decode("utf-8","replace")
def fetch_newsnow(source,route):
 dom=edge_dom(source,NEWSNOW+route+"&t="+str(int(time.time()*1000)));m=re.search(r"<pre[^>]*>(.*?)</pre>",dom,re.S|re.I)
 if not m:raise RuntimeError("NewsNow JSON not found")
 payload=json.loads(html.unescape(m.group(1)));out=[]
 for rank,row in enumerate(payload.get("items",[])[:30],1):
  title=str(row.get("title") or row.get("id") or "").strip();url=str(row.get("url") or row.get("mobileUrl") or "").strip();extra=row.get("extra") if isinstance(row.get("extra"),dict) else {};desc=str(extra.get("hover") or extra.get("info") or extra.get("value") or "").strip()
  if title and url.startswith(("http://","https://")):out.append({"title":title,"url":url,"desc":desc,"rank":rank})
 if not out:raise RuntimeError("empty list")
 return out,int(payload.get("updatedTime") or 0)
def plain(value):
 return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",str(value or "")))).strip()
def parse_qbitai_posts(posts):
 if not isinstance(posts,list):raise ValueError("QbitAI API response must be a list")
 out=[]
 for rank,row in enumerate(posts[:30],1):
  title=plain((row.get("title") or {}).get("rendered"));url=str(row.get("link") or "").strip();desc=plain((row.get("excerpt") or {}).get("rendered"));embedded=row.get("_embedded") or {};media=embedded.get("wp:featuredmedia") or [];cover=str((media[0] if media else {}).get("source_url") or "").strip()
  if title and url.startswith(("http://","https://")):out.append({"title":title,"url":url,"desc":desc,"cover":cover,"date":str(row.get("date") or ""),"platform":"qbitai","kind":"article","rank":rank})
 return out
def fetch_qbitai():
 req=Request(QBITAI_API,headers={"User-Agent":"Mozilla/5.0 HermesWeatherNewsCrawler/2.0","Accept":"application/json","Connection":"close"})
 try:
  with urlopen(req,timeout=45) as response:
   content_type=response.headers.get("Content-Type","")
   body=response.read(2_500_001)
   if len(body)>2_500_000:raise ValueError("QbitAI API response too large")
   if "json" not in content_type.lower():raise ValueError("QbitAI API did not return JSON")
   posts=json.loads(body.decode("utf-8"))
 except Exception:
  dom=edge_dom("qbitai",QBITAI_API);match=re.search(r"<pre[^>]*>(.*?)</pre>",dom,re.S|re.I)
  if not match:raise RuntimeError("QbitAI JSON not found")
  posts=json.loads(html.unescape(match.group(1)))
 rows=parse_qbitai_posts(posts)
 if not rows:raise RuntimeError("empty QbitAI list")
 return rows,int(time.time()*1000)
def parse_36kr_initial_state(page):
 marker="window.initialState=";start=page.find(marker)
 if start<0:raise RuntimeError("36Kr initialState not found")
 state,_=json.JSONDecoder().raw_decode(page[start+len(marker):]);bucket=(state.get("newsflashList") or {});out=[]
 for kind,items in (("article",bucket.get("banner") or []),("newsflash",((bucket.get("flow") or {}).get("itemList") or []))):
  for row in items:
   material=row.get("templateMaterial") or {};item_id=row.get("itemId") or material.get("itemId");title=plain(material.get("widgetTitle"));desc=plain(material.get("widgetContent"));cover=str(material.get("widgetImage") or "").strip()
   if not item_id or not title:continue
   path="p" if kind=="article" else "newsflashes";out.append({"title":title,"url":f"https://m.36kr.com/{path}/{item_id}","desc":desc,"cover":cover,"date":material.get("publishTime") or row.get("publishTime") or 0,"platform":"36kr","kind":"article","rank":len(out)+1})
 return out[:30]
def fetch_36kr():
 req=Request(K36_PAGE,headers={"User-Agent":"Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148","Accept":"text/html"})
 with urlopen(req,timeout=45) as response:page=response.read(2_500_000).decode("utf-8","replace")
 rows=parse_36kr_initial_state(page)
 if not rows:raise RuntimeError("empty 36Kr list")
 return rows,int(time.time()*1000)
def enrich_bilibili(rows):
 out=[]
 for row in rows:
  try:
   video=fetch_bilibili_video(row["url"],timeout=20)
   merged={**row,**video,"hotTitle":row.get("title","")}
   out.append(merged)
  except Exception as exc:
   print(f"bilibili resolve fallback: {row.get('title','')} ({exc})")
   out.append(row)
 return out
def gh(args,input_text=None,check=True):
 r=subprocess.run([str(GH),*args],input=input_text,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=90)
 if check and r.returncode:raise RuntimeError(r.stderr or r.stdout)
 return r
def upload(remote,data,message):
 current=gh(["api",f"repos/{REPO}/contents/{remote}"],check=False);payload={"message":message,"content":base64.b64encode(data).decode(),"branch":"main"}
 if current.returncode==0:
  old=json.loads(current.stdout)
  if base64.b64decode(old.get("content",""))==data:return "unchanged"
  payload["sha"]=old["sha"]
 gh(["api","--method","PUT",f"repos/{REPO}/contents/{remote}","--input","-"],json.dumps(payload,ensure_ascii=False));return "uploaded"
def main():
 old_path=ROOT/"hot-news.json";old_sources={}
 if old_path.exists():
  try:old_sources=json.loads(old_path.read_text(encoding="utf-8")).get("sources",{})
  except:pass
 sources={};provider_times={};failures={};fetchers={**{k:(fetch_newsnow,k,v) for k,v in DOMESTIC.items()},"qbitai":(fetch_qbitai,),"36kr":(fetch_36kr,)}
 for source,config in fetchers.items():
  try:
   fn=config[0];sources[source],provider_times[source]=fn(*config[1:])
   if source=="bilibili":sources[source]=enrich_bilibili(sources[source])
   print(f"{source}: {len(sources[source])} live rows")
  except Exception as exc:
   failures[source]=repr(exc)
   if old_sources.get(source):sources[source]=old_sources[source];print(f"{source}: cached fallback ({exc})")
   else:print(f"{source}: failed ({exc})")
 required=set(fetchers);missing=[x for x in required if not sources.get(x)]
 if missing:raise RuntimeError("Required sources empty: "+','.join(missing))
 payload={"updatedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"liveSourceCount":len(required)-len(failures),"sources":sources,"providerUpdatedTime":provider_times,"failures":failures}
 data=json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8");old_path.write_bytes(data);result=upload("hot-news.json",data,"Refresh domestic and AI hot news");print(f"hot-news.json: {result}; {len(data)} bytes; sources={len(sources)}")
if __name__=="__main__":
 try:main()
 except Exception as exc:print("ERROR:",exc,file=sys.stderr);raise SystemExit(1)
