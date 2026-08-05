from __future__ import annotations
import base64, html, json, re, shutil, subprocess, sys, time, xml.etree.ElementTree as ET
from pathlib import Path
from news_crawler import fetch_bilibili_video
ROOT=Path(__file__).resolve().parent
EDGE=Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
GH=Path(r"C:\Program Files\GitHub CLI\gh.exe")
REPO="alynlox-ui/HermesWeather"
NEWSNOW="https://newsnow.busiyi.world/api/s?id="
DOMESTIC={"thepaper":"thepaper","bilibili":"bilibili-hot-search"}
INTERNATIONAL={"x":"site:x.com","instagram":"site:instagram.com","tiktok":"site:tiktok.com"}
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
def fetch_social(source,query):
 from urllib.parse import quote
 url="https://news.google.com/rss/search?q="+quote(query)+"&hl=en-US&gl=US&ceid=US%3Aen"
 dom=edge_dom(source,url);begin=dom.find("<rss")
 if begin<0:raise RuntimeError("RSS not found")
 end=dom.find("</rss>",begin)
 if end<0:raise RuntimeError("RSS end not found")
 xml=dom[begin:end+6];out=[]
 for rank,block in enumerate(re.findall(r"<item>(.*?)</item>",xml,re.S|re.I)[:30],1):
  tm=re.search(r"<title>(.*?)</title>",block,re.S|re.I);lm=re.search(r"<link>(.*?)</link>",block,re.S|re.I);dm=re.search(r"<pubDate>(.*?)</pubDate>",block,re.S|re.I)
  title=html.unescape(re.sub(r"<[^>]+>","",tm.group(1))).strip() if tm else "";link=html.unescape(lm.group(1)).strip() if lm else "";date=html.unescape(dm.group(1)).strip() if dm else ""
  suffix={"x":" - x.com","instagram":" - Instagram","tiktok":" - TikTok"}[source]
  if title.endswith(suffix):title=title[:-len(suffix)].strip()
  if title and link.startswith(("http://","https://")):out.append({"title":title,"url":link,"desc":date,"rank":rank})
 if not out:raise RuntimeError("empty RSS list")
 return out,int(time.time()*1000)
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
 sources={};provider_times={};failures={};fetchers={**{k:(fetch_newsnow,k,v) for k,v in DOMESTIC.items()},**{k:(fetch_social,k,v) for k,v in INTERNATIONAL.items()}}
 for source,(fn,key,arg) in fetchers.items():
  try:
   sources[source],provider_times[source]=fn(key,arg)
   if source=="bilibili":sources[source]=enrich_bilibili(sources[source])
   print(f"{source}: {len(sources[source])} live rows")
  except Exception as exc:
   failures[source]=repr(exc)
   if old_sources.get(source):sources[source]=old_sources[source];print(f"{source}: cached fallback ({exc})")
   else:print(f"{source}: failed ({exc})")
 required=set(fetchers);missing=[x for x in required if not sources.get(x)]
 if missing:raise RuntimeError("Required sources empty: "+','.join(missing))
 payload={"updatedAt":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),"liveSourceCount":len(required)-len(failures),"sources":sources,"providerUpdatedTime":provider_times,"failures":failures}
 data=json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8");old_path.write_bytes(data);result=upload("hot-news.json",data,"Refresh domestic and international hot news");print(f"hot-news.json: {result}; {len(data)} bytes; sources={len(sources)}")
if __name__=="__main__":
 try:main()
 except Exception as exc:print("ERROR:",exc,file=sys.stderr);raise SystemExit(1)
