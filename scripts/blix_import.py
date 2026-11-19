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


def parse_rss_document(xml_text):
    """Read a complete RSS document. Accept *only* a valid RSS followed by junk.

    Blix occasionally sends extra data after its closing </rss> tag. Strict XML
    parsing rejects this as 'junk after document element'. We may safely ignore
    ONLY the surplus trailing bytes if the leading RSS document itself parses
    without errors. Broken entries inside RSS are not silently repaired.
    """
    try:
        root = ET.fromstring(xml_text)
        recovered = False
    except ET.ParseError as exc:
        if 'junk after document element' not in str(exc):
            raise
        open_tag = re.search(r'<rss(?=[\s>])', xml_text, re.I)
        close_tag = re.search(r'</rss\s*>', xml_text, re.I)
        if open_tag is None or close_tag is None or close_tag.start() <= open_tag.start():
            raise
        # Parse strictly again: any broken XML *inside* the RSS still fails.
        root = ET.fromstring(xml_text[:close_tag.end()])
        recovered = True
    if root.tag != 'rss':
        raise ValueError('Nieoczekiwany główny element XML: '+str(root.tag))
    return root, recovered


def parse_rss(xml_text, now, max_per_store=2, warnings=None):
    root, recovered = parse_rss_document(xml_text)
    if recovered and warnings is not None:
        warnings.append('RSS zawierał dodatkowe dane po </rss>; użyto tylko poprawnego dokumentu RSS.')
    found={key:[] for key in STORES}
    for item in root.findall('.//item'):
        url=(item.findtext('link') or '').strip()
        title=(item.findtext('title') or '').strip()
        m=re.fullmatch(r'https://blix\.pl/sklep/([^/]+)/gazetka/\d+/?',url)
        if not m or m.group(1) not in STORES:continue
        slug=m.group(1)
        # Avoid local-only flyers for other cities (as seen in current RSS).
        if re.search(r'wielkie otwarcie|pabianice|zielona g[oó]ra|racib[oó]rz', title, re.I):continue
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


# Blix leaflet pages can embed a product catalog as window.offers = [...] .
# Decode only JSON literals: never run JavaScript and never guess a price.
WINDOW_OFFERS = re.compile(r'(?:window\s*\.\s*offers|window\s*\[\s*[\"\']offers[\"\']\s*\])\s*=\s*', re.I)

def embedded_offers(html):
    """Read valid JSON array/object assigned to window.offers, if exposed publicly."""
    decoder=json.JSONDecoder()
    records=[]
    for m in list(WINDOW_OFFERS.finditer(html))[:5]:
        piece=html[m.end():].lstrip()
        try:
            if piece.startswith('JSON.parse('):
                arg=piece[len('JSON.parse('):].lstrip()
                json_string,_=decoder.raw_decode(arg)
                if not isinstance(json_string,str):continue
                data=json.loads(json_string)
            else:
                data,_=decoder.raw_decode(piece)
        except (json.JSONDecodeError,ValueError,TypeError):
            continue
        if isinstance(data,dict):
            data=data.get('offers',data.get('products',data.get('items',[])))
        if isinstance(data,list):
            records += [x for x in data if isinstance(x,dict)]
    return records


def embedded_name(row):
    p=row.get('product')
    nested=p if isinstance(p,dict) else {}
    for candidate in (row.get('name'),row.get('productName'),row.get('title'),
                      nested.get('name'), nested.get('productName'), nested.get('title')):
        if isinstance(candidate,str) and candidate.strip():return candidate.strip()
    return ''


def embedded_price(value):
    """Return price in PLN or None. Integer fields in Blix window.offers are grosze."""
    if isinstance(value,dict):
        for key in ('amount','value','gross','price'):
            if key in value:return embedded_price(value[key])
        return None
    if isinstance(value,bool) or value is None:return None
    if isinstance(value,int):
        amount=value/100
    elif isinstance(value,float):
        amount=value
    elif isinstance(value,str):
        txt=value.strip().replace('\xa0','').replace('zł','').strip().replace(',','.')
        if not re.fullmatch(r'\d+(?:\.\d{1,2})?',txt):return None
        amount=int(txt)/100 if '.' not in txt else float(txt)
    else:
        return None
    if not (0.10<=amount<=1000):return None
    return round(amount,2)


def embedded_size(row):
    """Textual pack information only; a bare number without units is not trusted."""
    product=row.get('product') if isinstance(row.get('product'),dict) else {}
    for d in (row,product):
        for key in ('packageSize','packSize','weight','quantity','size','unitSize','netWeight'):
            v=d.get(key)
            if isinstance(v,str) and WEIGHT.search(v):return v
            if isinstance(v,dict):
                value=v.get('value',v.get('amount'))
                unit=v.get('unit',v.get('unitOfMeasure'))
                if isinstance(value,(int,float)) and isinstance(unit,str) and unit.lower() in ('kg','g','l','ml','szt','szt.'):
                    return str(value)+' '+unit
    return ''


def window_offer_candidates(html,leaflet):
    rows=embedded_offers(html)
    candidates=[]
    for row in rows:
        name=embedded_name(row)
        if not name:continue
        price=None
        for key in ('promotionalPrice','promoPrice','currentPrice','price','grossPrice'):
            if key in row:
                price=embedded_price(row[key]);break
        if price is None:
            for key in ('price','promotionalPrice'):
                nested=row.get('product')
                if isinstance(nested,dict) and key in nested:
                    price=embedded_price(nested[key]);break
        if price is None:continue
        size=embedded_size(row)
        label=(name+' '+size).strip() if size and size.lower() not in name.lower() else name
        detail=''
        for key in ('promotionText','promoText','conditions','promoLabel'):
            value=row.get(key)
            if isinstance(value,str):detail+=' '+value[:200]
        line=f'{label} za {str(format(price,".2f")).replace(".",",")} zł{detail}'
        url=row.get('url') or row.get('link') or leaflet['url']
        if not isinstance(url,str) or not url.startswith('https://blix.pl/'):
            url=leaflet['url']
        regular=None
        for key in ('regularPrice','originalPrice','oldPrice','previousPrice'):
            if key in row:
                regular=embedded_price(row[key])
                break
        extras={'regularPrice':regular if regular is not None and regular>price else None}
        candidates.append((label,line,url,'window.offers',extras))
    return candidates,len(rows)


def extract_candidates(html, leaflet, today, diagnostics=None):
    soup=BeautifulSoup(html,'html.parser')
    candidates, catalog_count=window_offer_candidates(html,leaflet)
    if diagnostics is not None:
        diagnostics['embeddedObjects']+=catalog_count
        diagnostics['catalogCandidates']+=len(candidates)
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
    for candidate in candidates:
        name,txt,url,method=candidate[:4]
        extras=candidate[4] if len(candidate)>4 else {}
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
        base={'ingredient':ing,'store':leaflet['store'],'product':name[:220],'price':round(price,2),'regularPrice':extras.get('regularPrice'),'from':leaflet['from'],'to':leaflet['to'],'url':url if url.startswith('https://blix.pl/') else leaflet['url'],'note':note,'minQty':1,'source':'Blix','sourceMethod':method}
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
    if diagnostics is not None:
        diagnostics['accepted']+=len(accepted)
        diagnostics['review']+=len(review)
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
    result={'source':'https://blix.pl/rss/gazetki','generatedAt':dt.datetime.now(dt.timezone.utc).isoformat(),'validFor':now.isoformat(),'status':'ok','leaflets':[],'offers':[],'review':[],'errors':[],'warnings':[],'diagnostics':{'pagesFetched':0,'embeddedObjects':0,'catalogCandidates':0,'accepted':0,'review':0},'notice':'Automatyczny odczyt strony źródłowej, nie potwierdzenie ceny w sklepie. Braki danych wymagają sprawdzenia.'}
    try: rss=fetcher.get(RSS_URL)
    except Exception as e:
        result['status']='source_unavailable';result['errors'].append(str(e));return write(output_path,result)
    try: leaflets=parse_rss(rss,now,max_per_store=max_per_store,warnings=result['warnings'])
    except Exception as e:
        result['status']='invalid_feed';result['errors'].append(str(e));return write(output_path,result)
    result['leaflets']=leaflets
    for item in leaflets:
        try:
            html=fetcher.get(item['url'])
            result['diagnostics']['pagesFetched']+=1
            yes,no=extract_candidates(html,item,now,diagnostics=result['diagnostics'])
            result['offers']+=yes;result['review']+=no
        except Exception as e:
            result['errors'].append(item['store']+': '+str(e))
            if 'HTTP 429' in str(e) or 'HTTP 403' in str(e):break
    if (result['errors'] or result['warnings']) and result['status']=='ok':result['status']='partial'
    if not result['leaflets'] and result['status'] in ('ok','partial'):
        result['warnings'].append('Nie znaleziono gazetek tych sześciu sklepów z jednoznaczną aktualną datą w tytule RSS.')
    if result['leaflets'] and not result['offers'] and not result['review']:
        result['warnings'].append('Wykryto gazetki, ale nie udało się odczytać ani jednej ceny składnika. Sprawdź diagnostics oraz strukturę stron Blixa.')
        if result['status']=='ok':result['status']='partial'
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
