"""Optional visual verification for incomplete Blix price records.

Uses a user's own Gemini API key held in GitHub Actions Secrets, NEVER embedded
in the browser bundle. Requires public leaflet pages to be accessible and their
robots.txt permission to be granted. Nothing is scraped around blocks.

A visual record is only used if its promotional price AND ingredient can be
matched to an independent text-based candidate from window.offers.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from collections import defaultdict
from urllib.parse import urlparse, urlunparse

import requests

PROMPT = '''Analizujesz wyłącznie CENTRALNĄ, WIDOCZNĄ GRAFIKĘ gazetki spożywczej
(nie menu strony ani inne reklamy). Odczytaj WYŁĄCZNIE jednoznacznie czytelne
oferty. Nie zgaduj danych. Jeśli jednostka lub cena regularna nie jest
widoczna, wpisz null. Dla promocji z kartą/kuponem ustaw coupon=true.
Zwróć wyłącznie JSON:
{"items":[{"name":"Cytryny luzem","price":4.99,"regularPrice":11.99,
"discountPct":58,"quantity":1,"unit":"kg","coupon":false,
"conditions":"","evidence":"4,99 / 1 kg; 11,99; -58%"}]}

price i regularPrice są cenami w złotych ZA TĘ SAMĄ JEDNOSTKĘ.
Dostępne jednostki: kg, g, l, ml, szt. Ilość jest mianownikiem ceny,
np. 1 dla 1 kg, 100 dla 100 g. W niejasnych przypadkach pomiń ofertę.
Nie uzupełniaj ceny regularnej na podstawie procentu i odwrotnie.
Nie wymyślaj procentów. Maksymalnie 30 ofert; bez duplikatów.'''


def _read_model(png, model):
    key=os.getenv('GEMINI_API_KEY','')
    if not key:return []
    payload={'contents':[{'parts':[
        {'text':PROMPT},
        {'inline_data':{'mime_type':'image/png','data':base64.b64encode(png).decode('ascii')}}
    ]}], 'generationConfig':{'responseMimeType':'application/json','temperature':0}}
    url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent'
    r=requests.post(url,headers={'x-goog-api-key':key,'Content-Type':'application/json'},json=payload,timeout=65)
    r.raise_for_status()
    parts=r.json().get('candidates',[{}])[0].get('content',{}).get('parts',[])
    raw=''.join(p.get('text','') for p in parts if isinstance(p,dict))
    raw=raw.strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    data=json.loads(raw)
    return data.get('items',[]) if isinstance(data,dict) else []


def _screenshot(page, url):
    page.goto(url,wait_until='domcontentloaded',timeout=25000)
    page.wait_for_timeout(1800)
    # Prefer the visible flyer IMAGE, not a low-resolution full browser page.
    elems=page.locator('img').all()
    winner=None;score=0
    for elem in elems[:90]:
        try:
            v=elem.evaluate('''el => {
              const b=el.getBoundingClientRect();
              return {w:b.width,h:b.height,nw:el.naturalWidth,nh:el.naturalHeight,
                      alt:(el.alt||'').toLowerCase(),visible:b.width>100&&b.height>100};
            }''')
        except Exception:continue
        if not v.get('visible') or v['w']<300 or v['h']<400:continue
        aspect=v['w']/v['h']
        if not 0.35<aspect<1.2:continue
        this=v['w']*v['h']+(1e6 if re.search(r'gazetk|stron|page|leaflet',v.get('alt','')) else 0)
        if this>score:score=this;winner=elem
    if winner:
        return winner.screenshot(timeout=15000)
    return page.screenshot(full_page=False,timeout=15000)


def _quantity(item):
    q=item.get('quantity');unit=str(item.get('unit') or '').strip().lower().rstrip('.')
    if isinstance(q,bool) or not isinstance(q,(float,int)) or q<=0 or q>10000:return None
    if unit=='kg':return (q*1000,'g')
    if unit=='g':return (q,'g')
    if unit=='l':return (q*1000,'ml')
    if unit=='ml':return (q,'ml')
    if unit in ('szt','sztuka'):return (q,'szt')
    return None


def _money(v):
    try:
        if isinstance(v,bool):return None
        x=float(v)
        return round(x,2) if 0.10<=x<=1000 else None
    except (ValueError,TypeError):return None


def _promote(record, item, screenshot_url):
    from blix_import import ingredient_match, UNITS, AMBIGUOUS_UNITS
    name=item.get('name')
    if not isinstance(name,str) or not name.strip():return None
    if ingredient_match(name)!=record['ingredient']:return None
    price=_money(item.get('price'))
    if price is None or abs(price-record['price'])>0.01:return None
    if item.get('coupon') or item.get('conditions') or item.get('minQty',1) not in (None,1):return None
    amt=_quantity(item)
    if not amt or record['ingredient'] in AMBIGUOUS_UNITS:return None
    quantity,unit=amt
    if unit not in [u for u,names in UNITS.items() if record['ingredient'] in names]:return None
    regular=_money(item.get('regularPrice'))
    if regular is not None and regular<=price:regular=None
    pct=item.get('discountPct')
    if isinstance(pct,bool):pct=None
    if pct is not None:
        try:pct=float(pct)
        except (TypeError,ValueError):pct=None
    if pct is not None and not 0<pct<100:pct=None
    if regular is not None and pct is not None and abs(100*(regular-price)/regular-pct)>2:
        # Contradictory visual read; don't record invented savings.
        return None
    output={k:v for k,v in record.items() if k not in ('problem','unitEvidence')}
    output.update({'pack':round(quantity,4),'unit':unit,'regularPrice':regular,
                   'discountPct':pct,'minQty':1,
                   'note':'Jednostka i rabat odczytane z grafiki gazetki; sprawdź przy kasie',
                   'sourceMethod':'window.offers + grafika (AI)',
                   'visualEvidence':str(item.get('evidence',''))[:150],
                   'url':screenshot_url})
    return output


def enrich_review(data,fetcher,max_screens=6):
    if not os.getenv('GEMINI_API_KEY'):return
    from playwright.sync_api import sync_playwright
    by_url=defaultdict(list)
    for r in data.get('review',[]):by_url[r['url'].split('?')[0]].append(r)
    jobs=[]
    # Round-robin 1 screenshot per store, then optional second pass.
    leaflets=[l for l in data.get('leaflets',[]) if l['url'] in by_url]
    for page_number in (2,1,3):
        for leaflet in leaflets:
            jobs.append((leaflet,page_number))
    stats=data.setdefault('diagnostics',{})
    stats.update({'visualPagesAttempted':0,'visualProductsRead':0,'visualOffersAccepted':0})
    accepted=[];completed=set()
    model=os.getenv('GEMINI_MODEL','gemini-2.5-flash')
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            page=browser.new_page(viewport={'width':1280,'height':1200},device_scale_factor=2)
            for leaf,page_no in jobs[:max(0,min(24,max_screens))]:
                url=leaf['url'].rstrip('/')+'/?pageNumber='+str(page_no)
                if not fetcher.allowed(url):continue
                try:
                    image=_screenshot(page,url)
                    stats['visualPagesAttempted']+=1
                    items=_read_model(image,model)
                except Exception as ex:
                    data.setdefault('warnings',[]).append('Obraz '+leaf['store']+' strona '+str(page_no)+': '+str(ex)[:90])
                    continue
                if not isinstance(items,list):continue
                stats['visualProductsRead']+=len(items)
                for item in items:
                    if not isinstance(item,dict):continue
                    for rec in by_url[leaf['url']]:
                        sig=(rec['ingredient'],rec['store'],rec['price'],rec['url'])
                        if sig in completed:continue
                        promoted=_promote(rec,item,url)
                        if promoted:
                            accepted.append(promoted);completed.add(sig);break
                time.sleep(1.5)
        finally:browser.close()
    data['offers'].extend(accepted)
    data['review']=[r for r in data['review'] if (r['ingredient'],r['store'],r['price'],r['url']) not in completed]
    stats['visualOffersAccepted']=len(accepted)
    if stats['visualPagesAttempted'] and not accepted:
        data.setdefault('warnings',[]).append('Analiza obrazów nie potwierdziła jednostek dla produktów z bazy: pozostawiono je do sprawdzenia.')
