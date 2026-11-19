#!/usr/bin/env python3
"""Polite Blix RSS + public flyer HTML importer.

RSS locates new leaflets; this DOES NOT mean Blix grants redistribution rights.
Robots.txt is respected, rate-limits are observed, and blocked access is never bypassed.
Missing unit/pack/promo details -> review candidate, not a price in the recipe ranking.
"""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

BASE = 'https://blix.pl'
RSS_URL = BASE + '/rss/gazetki'
STORES = {'biedronka':'Biedronka','lidl':'Lidl','kaufland':'Kaufland','dino':'Dino','aldi':'Aldi','auchan':'Auchan'}
USER_AGENT = 'SzamaNaPromce/1.0 (prywatny, umiarkowany czytnik RSS; bez omijania blokad)'
PRICE = re.compile(r'(?<!\d)(\d{1,3}(?:[ .,]\d{3})*[,\.]\d{2})\s*zł\b', re.I)
WEIGHT = re.compile(r'(?<!\d)(\d+(?:[,.]\d+)?)\s*(kg|g|l|ml|szt\.?|sztuk|sztuki)\b',re.I)
DATERANGE = re.compile(r'(?<!\d)(\d{1,2})\.(\d{1,2})\s*[-–]\s*(\d{1,2})\.(\d{1,2})(?:\.(20\d{2}))?')
PROMO_COMPLEX = re.compile(r'\b(?:przy\s+zakupie|od\s+\d+\s+szt|minimum\s+\d+|z\s+aplikacj|z\s+kupon|drugi\s+produkt|2\s*\+\s*1|1\s*\+\s*1|za\s+2\s+szt)\b',re.I)
# Only match sufficiently-specific ingredient names. Avoid replacing cheddar with gouda etc.
ALIASES = {
 'pierś z kurczaka': ['pierś z kurczaka','filet z piersi kurczaka','filet z kurczaka'],
 'łopatka wieprzowa':['łopatka wieprzowa','łopatka bez kości'],
 'schab wieprzowy':['schab wieprzowy','schab bez kości'],
 'śmietana 18%':['śmietana 18%','śmietana 18 %'],
 'przecier pomidorowy':['przecier pomidorowy'],
 'passata pomidorowa':['passata pomidorowa','passata'],
 'ryż basmati':['ryż basmati','basmati'],
 'czosnek':['czosnek'],
 'cebula czerwona':['cebula czerwona','czerwone cebule'],
 'cebula':['cebula biała','cebula żółta','cebula'],
 'kolendra świeża':['kolendra świeża','kolendra pęczek'],
 'olej':['olej rzepakowy','olej słonecznikowy'],
 'oliwa':['oliwa z oliwek'],
 'tortilla pszenna':['tortilla pszenna','tortille pszenne'],
 'mozzarella':['mozzarella'],
 'cheddar':['cheddar'],
 'papryka zielona':['papryka zielona'],
 'natka pietruszki':['natka pietruszki','pietruszka natka'],
 'piwo bezalkoholowe':['piwo bezalkoholowe','piwo 0%'],
 'miód':['miód'],
 'sos sojowy ciemny':['sos sojowy ciemny'],
 'sos sojowy jasny':['sos sojowy jasny'],
 'sos sojowy':['sos sojowy'],
 'cytryna':['cytryna','cytryny'],
 'ziemniaki':['ziemniaki','ziemniak'],
 'szparagi':['szparagi'],
 'szynka szwarcwaldzka':['szynka szwarcwaldzka'],
 'makaron ryżowy':['makaron ryżowy'],
 'jajka':['jajka','jaja'],
 'kiełki fasoli mung':['kiełki mung','kiełki fasoli mung'],
 'orzeszki ziemne':['orzeszki ziemne','orzechy arachidowe'],
 'pasta z tamaryndowca':['pasta z tamaryndowca'],
 'sos rybny':['sos rybny'],
 'cukier brązowy':['cukier brązowy','cukier trzcinowy'],
 'limonka':['limonka','limonki'],
 'ketchup':['ketchup'],
 'musztarda':['musztarda'],
 'papryka wędzona':['papryka wędzona'],
 'marchew':['marchew','marchewka'],
 'ocet ryżowy':['ocet ryżowy'],
 'skrobia ziemniaczana':['skrobia ziemniaczana'],
 'imbir':['imbir'],
}
# Ingredient semantics inferred from known, verified recipe quantities, not from Blix.
UNITS = {'g':{'łopatka wieprzowa','schab wieprzowy','śmietana 18%','przecier pomidorowy','passata pomidorowa','ryż basmati','kolendra świeża','mozzarella','cheddar','miód','ziemniaki','szynka szwarcwaldzka','makaron ryżowy','kiełki fasoli mung','orzeszki ziemne','pasta z tamaryndowca','sos sojowy','sos rybny','cukier brązowy','ketchup','musztarda','papryka wędzona','skrobia ziemniaczana','imbir','pierś z kurczaka','sos sojowy jasny'},'ml':{'olej','oliwa','piwo bezalkoholowe','sos sojowy','sos sojowy jasny','sos sojowy ciemny','ocet ryżowy'},'szt':{'czosnek','cebula','cebula czerwona','papryka zielona','cytryna','tortilla pszenna','jajka','szparagi','limonka','marchew'}}
# Some recipe labels have inconsistent unit across recipes: refuse ambiguous matches.
AMBIGUOUS_UNITS = {'sos sojowy', 'sos sojowy jasny'}
REJECTED_CATEGORIES = re.compile(r'piwo(?!\s+bezalkoholowe)|wódka|whisk|wino\b|brandy|rum\b|papierosy|cygar', re.I)


def normalize(s):
    return re.sub(r'\s+', ' ', s.casefold().replace('\xa0',' ')).strip()


def ingredient_match(title):
    t=normalize(title)
    matches=[]
    for name,aliases in ALIASES.items():
        if any(re.search(r'(?<!\w)'+re.escape(a.casefold())+r'(?!\w)',t) for a in aliases):
            matches.append(name)
    # More precise labels must win; and no ambiguous substitution
    if 'cebula czerwona' in matches and 'cebula' in matches: matches.remove('cebula')
    if 'sos sojowy ciemny' in matches and 'sos sojowy' in matches:matches.remove('sos sojowy')
    if 'sos sojowy jasny' in matches and 'sos sojowy' in matches:matches.remove('sos sojowy')
    if len(matches)!=1:return None
    return matches[0]


def date_range(raw, now):
    m=DATERANGE.search(raw)
    if not m:return None
    d1,m1,d2,m2=(int(m.group(i)) for i in range(1,5))
    y=int(m.group(5) or now.year)
    try:
        a=dt.date(y,m1,d1);b=dt.date(y+(m2<m1),m2,d2)
    except ValueError:return None
    return (a.isoformat(),b.isoformat()) if b>=a and (b-a).days<=70 else None


def parse_rss(xml_text, now, max_per_store=2):
    root=ET.fromstring(xml_text)
    found={key:[] for key in STORES}
    for item in root.findall('.//item'):
        url=(item.findtext('link') or '').strip()
        title=(item.findtext('title') or '').strip()
        m=re.fullmatch(r'https://blix\.pl/sklep/([^/]+)/gazetka/\d+/?',url)
        if not m or m.group(1) not in STORES:continue
        slug=m.group(1)
        if len(found[slug])>=max_per_store:continue
        dates=date_range(title,now)
        if not dates or dates[0]>now.isoformat() or dates[1]<now.isoformat():continue
        if any(x['url']==url for x in found[slug]):continue
        found[slug].append({'store':STORES[slug],'slug':slug,'title':title,'url':url,'from':dates[0],'to':dates[1]})
    return [entry for records in found.values() for entry in records]


def parse_size(text, ingredient):
    if ingredient in AMBIGUOUS_UNITS:return None
    units=[u for u,names in UNITS.items() if ingredient in names]
    if len(units)!=1:return None
    expected=units[0]
    matches=list(WEIGHT.finditer(text))
    converted=[]
    for m in matches:
        val=float(m.group(1).replace(',','.')); raw=m.group(2).lower().rstrip('.')
        unit='g' if raw in ('g','kg') else 'ml' if raw in ('l','ml') else 'szt'
        if raw in ('kg','l'):val*=1000
        if unit==expected:converted.append((val,unit))
    return converted[0] if len(set(converted))==1 and converted else None


def extract_candidates(html, leaflet, today):
    soup=BeautifulSoup(html,'html.parser')
    candidates=[]
    # JSON-LD structured Product/Offer; no JS execution, no bypass.
    def traverse(obj):
        if isinstance(obj,list):
            for x in obj:yield from traverse(x)
        if isinstance(obj,dict):
            if obj.get('@type')=='Product' or (isinstance(obj.get('@type'),list) and 'Product' in obj['@type']):yield obj
            for x in obj.values():yield from traverse(x)
    for tag in soup.select('script[type="application/ld+json"]'):
        try: data=json.loads(tag.string or tag.get_text())
        except (TypeError,ValueError):continue
        for p in traverse(data):
            title=p.get('name','')
            offers=p.get('offers') or {}
            if isinstance(offers,list):offers=offers[0] if offers else {}
            if isinstance(offers,dict):
                price=offers.get('price'); currency=offers.get('priceCurrency','PLN')
                if price and currency=='PLN':candidates.append((str(title),str(price).replace('.',',')+' zł',p.get('url') or leaflet['url'],'jsonld'))
    # Product-specific Blix links with one price in text. Ignore generic page/sidebar links.
    for a in soup.select('a[href]'):
        href=a['href']
        if not any(x in href for x in ('/produkt/','/produkty/','/promocja/','/oferta/')):continue
        name=a.get_text(' ',strip=True)
        if not PRICE.search(name):
            img=a.find('img')
            if img: name=(img.get('alt','')+' '+name).strip()
        if not PRICE.search(name):continue
        candidates.append((name,name,urljoin(leaflet['url'],href),'anchor'))
    # Unstructured product list in meta descriptions: "X za 16,99 zł".
    for meta in soup.select('meta[name="description"],meta[property="og:description"]'):
        description=meta.get('content','')
        m=re.search(r'Znajdziesz\s+w\s+niej\s+m\.in\.\s+oferty\s+na:\s*(.+?)(?:\.\s|$)',description,re.I)
        if m:
            for item in m.group(1).split(', '):
                if PRICE.search(item):candidates.append((item,item,leaflet['url'],'description'))
    unique=set(); accepted=[]; review=[]
    for name,txt,url,method in candidates:
        if REJECTED_CATEGORIES.search(name):continue
        ing=ingredient_match(name)
        if ing is None or ing=='pierś z kurczaka':continue
        # If contains more than one price, one cannot know which is promotional.
        ps=PRICE.findall(txt)
        if len(ps)!=1:continue
        price=float(ps[0].replace(' ','').replace('.','').replace(',','.'))
        if not (0.1<=price<=1000):continue
        size=parse_size(name,ing)
        note='Źródło: Blix, '+method
        if PROMO_COMPLEX.search(txt+' '+name):note+='; sprawdź warunki promocji'
        base={'ingredient':ing,'store':leaflet['store'],'product':name[:220],'price':round(price,2),'regularPrice':None,'from':leaflet['from'],'to':leaflet['to'],'url':url if url.startswith('https://blix.pl/') else leaflet['url'],'note':note,'minQty':1,'source':'Blix','sourceMethod':method}
        key=(ing,base['store'],base['price'],name)
        if key in unique:continue
        unique.add(key)
        if size and not PROMO_COMPLEX.search(txt+' '+name):
            pack,unit=size
            base.update({'pack':pack,'unit':unit,'id':'blix_'+hashlib.sha256((leaflet['url']+str(key)).encode()).hexdigest()[:16]})
            accepted.append(base)
        else:
            base.update({'problem':'brak jednoznacznej gramatury/jednostki lub warunki wielosztukowe','pack':None,'unit':None})
            review.append(base)
    return accepted,review


class Fetcher:
    def __init__(self,timeout=18,delay=2):
        self.session=requests.Session();self.session.headers.update({'User-Agent':USER_AGENT, 'Accept':'text/html, application/rss+xml;q=0.9'})
        self.timeout=timeout;self.delay=delay;self.last=0
        self.robots=None
    def allowed(self,url):
        if urlparse(url).scheme!='https' or urlparse(url).hostname!='blix.pl':return False
        if self.robots is None:
            try:
                self._pace();r=self.session.get(BASE+'/robots.txt',timeout=self.timeout)
                r.raise_for_status()
                rp=RobotFileParser();rp.parse(r.text.splitlines());self.robots=rp
            except requests.RequestException as ex:
                raise RuntimeError('Nie można sprawdzić robots.txt — przerywam pobieranie: '+str(ex)) from ex
        return self.robots.can_fetch(USER_AGENT,url)
    def _pace(self):
        diff=time.monotonic()-self.last
        if diff<self.delay:time.sleep(self.delay-diff)
        self.last=time.monotonic()
    def get(self,url):
        if not self.allowed(url):raise RuntimeError('robots.txt nie dopuszcza: '+url)
        self._pace();response=self.session.get(url,timeout=self.timeout,allow_redirects=False)
        if response.status_code in (301,302,303,307,308):
            raise RuntimeError('Przekierowanie: pomijam bez śledzenia celu: '+url)
        if response.status_code in (403,429):raise RuntimeError('Blix ograniczył dostęp (HTTP '+str(response.status_code)+'). Nie ponawiam.')
        response.raise_for_status()
        if len(response.content)>4_000_000:raise RuntimeError('Odpowiedź za duża — pominięta')
        return response.text


def run(output_path,now=None,fetcher=None,max_per_store=2):
    now=now or dt.date.today();fetcher=fetcher or Fetcher()
    result={'source':'https://blix.pl/rss/gazetki','generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'validFor':now.isoformat(),'status':'ok','leaflets':[],'offers':[],'review':[],'errors':[],'notice':'Automatyczny odczyt strony źródłowej, nie potwierdzenie ceny w sklepie. Braki danych wymagają sprawdzenia.'}
    try: rss=fetcher.get(RSS_URL)
    except Exception as e:
        result['status']='source_unavailable';result['errors'].append(str(e));return write(output_path,result)
    try: leaflets=parse_rss(rss,now,max_per_store=max_per_store)
    except Exception as e:
        result['status']='invalid_feed';result['errors'].append(str(e));return write(output_path,result)
    result['leaflets']=leaflets
    for item in leaflets:
        try:
            html=fetcher.get(item['url'])
            yes,no=extract_candidates(html,item,now)
            result['offers']+=yes;result['review']+=no
        except Exception as e:
            result['errors'].append(item['store']+': '+str(e))
            if 'HTTP 429' in str(e) or 'HTTP 403' in str(e):break
    if result['errors'] and result['status']=='ok':result['status']='partial'
    # prevent excessive stored candidate data
    result['offers']=result['offers'][:350];result['review']=result['review'][:500]
    return write(output_path,result)


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    text=json.dumps(data,ensure_ascii=False,indent=2)+'\n'
    # avoid unnecessary changes on rerun same day (generatedAt excluded only for output content validation)
    path.write_text(text,encoding='utf-8')
    return data

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path(__file__).resolve().parents[1]/'site/data/blix_promocje.json')
    parser.add_argument('--date',type=dt.date.fromisoformat,default=None,help='YYYY-MM-DD (tylko testy)')
    parser.add_argument('--max-per-store',type=int,default=2)
    args=parser.parse_args()
    r=run(args.output,now=args.date,max_per_store=max(1,min(args.max_per_store,4)))
    print('Blix:',r['status'],'gazetki:',len(r['leaflets']),'oferty:',len(r['offers']),'do weryfikacji:',len(r['review']),'błędy:',len(r['errors']))
    for error in r['errors'][:6]:print('  !',error,file=sys.stderr)
    sys.exit(0 if r['status'] in ('ok','partial') else 2)
