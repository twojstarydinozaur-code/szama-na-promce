#!/usr/bin/env python3
"""Importer METADANYCH filmów z 5 playlist Policzona Szama.

Wymaga środowiskowej zmiennej YOUTUBE_API_KEY (klucz YouTube Data API v3).
Pobiera publiczne tytuły, opisy i adresy YouTube, bez filmów ani napisów.
Nie tworzy automatycznie przepisów bez weryfikacji gramatur.
"""
import csv
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

PLAYLISTS = {
    'orientalne': 'PLuNfzW0zYqmNIhpRFpWSqjHRveFwGdDD_',
    'dzien_jedzenia': 'PLuNfzW0zYqmMAqmTTEebahIOexfYVytMf',
    'do_pracy_i_szkoly': 'PLuNfzW0zYqmMMi6ymEWI2IywGxZJ8BEwp',
    'hity': 'PLuNfzW0zYqmOoXeymZ3QIV-CJT7AFpIM9',
    'lunchboxy': 'PLuNfzW0zYqmP4Sdh6k_KYOINzWpjzFMHr',
}
BASE = 'https://www.googleapis.com/youtube/v3/'

def api(method, **params):
    q = urllib.parse.urlencode({'key': os.environ['YOUTUBE_API_KEY'], **params})
    with urllib.request.urlopen(BASE + method + '?' + q, timeout=25) as r:
        return json.load(r)

def batch(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i+n]

def main():
    if not os.environ.get('YOUTUBE_API_KEY'):
        sys.exit('Brakuje YOUTUBE_API_KEY. Ustaw zmienna srodowiskowa z kluczem YouTube Data API.')
    found = {}
    memberships = {}
    for name, pid in PLAYLISTS.items():
        page = None
        while True:
            p = dict(part='contentDetails', playlistId=pid, maxResults=50)
            if page:
                p['pageToken'] = page
            data = api('playlistItems', **p)
            for v in data.get('items', []):
                vid = v.get('contentDetails', {}).get('videoId')
                if vid:
                    found[vid] = True
                    memberships.setdefault(vid, []).append(name)
            page = data.get('nextPageToken')
            if not page:
                break
        print(f'{name}: odnaleziono {sum(name in names for names in memberships.values())} filmow')
    rows = []
    for ids in batch(list(found), 50):
        resp = api('videos', part='snippet', id=','.join(ids), maxResults=50)
        for video in resp.get('items', []):
            vid = video['id']
            snip = video.get('snippet', {})
            if snip.get('channelTitle', '').lower().strip() != 'policzona szama':
                # Playlisty mogą zawierać również filmy innych autorów.
                continue
            rows.append({
                'playlisty': ', '.join(sorted(set(memberships[vid]))),
                'video_id': vid,
                'tytul': snip.get('title', ''),
                'opis': snip.get('description', ''),
                'opublikowano': snip.get('publishedAt', ''),
                'url': 'https://www.youtube.com/watch?v=' + vid,
                'status_przepisu': 'do_weryfikacji',
            })
    rows.sort(key=lambda r: (r['playlisty'],r['tytul']))
    outdir = Path(__file__).resolve().parent
    with (outdir / 'filmy_youtube.json').open('w', encoding='utf-8') as file:
        json.dump(rows,file,ensure_ascii=False,indent=2)
    with (outdir / 'filmy_youtube.csv').open('w',encoding='utf-8-sig',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=list(rows[0]) if rows else
          ['playlisty','video_id','tytul','opis','opublikowano','url','status_przepisu'],delimiter=';')
        writer.writeheader()
        writer.writerows(rows)
    print(f'Zapisano {len(rows)} filmow. Przeczytaj opisy i zweryfikuj skladniki przed importem do receptur.')

if __name__ == '__main__':
    try: main()
    except Exception as exc:
        sys.exit('Błąd pobierania: '+str(exc))
