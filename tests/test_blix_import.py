import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from blix_import import date_range,parse_rss,parse_size,ingredient_match,extract_candidates,run

TODAY=dt.date(2026,11,19)
LEAFLET={'url':'https://blix.pl/sklep/dino/gazetka/537168/','store':'Dino','from':'2026-11-19','to':'2026-11-24'}
RSS='''<?xml version="1.0"?><rss><channel>
<item><title>Gazetka Dino - Gazetka Super ceny - 19.11-24.11</title><link>https://blix.pl/sklep/dino/gazetka/537168/</link></item>
<item><title>Gazetka Lidl - Oferta - 19.11-21.11</title><link>https://blix.pl/sklep/lidl/gazetka/537102/</link></item>
<item><title>Gazetka Dino - Archiwalna - 01.11-05.11</title><link>https://blix.pl/sklep/dino/gazetka/535111/</link></item>
</channel></rss>'''
HTML='''<html><head><meta name="description" content="Znajdziesz w niej m.in. oferty na: Mozzarella tarta 500 g za 9,99 zł, Przecier pomidorowy 190 g za 3,49 zł, Czosnek 5,99 zł, Schab wieprzowy 1 kg za 10,99 zł przy zakupie 2 szt."></head><body>
<a href="/produkt/abc">Mozzarella tarta 500 g 9,99 zł</a>
<a href="/produkt/def">Schab wieprzowy 1 kg za 10,99 zł przy zakupie 2 szt.</a>
</body></html>'''
class Tests(unittest.TestCase):
 def test_rss_current(self):
  a=parse_rss(RSS,TODAY)
  self.assertEqual([x['store'] for x in a],['Lidl','Dino'])
  self.assertTrue(all(x['from']=='2026-11-19' for x in a))
 def test_aliases(self):
  self.assertEqual(ingredient_match('Mozzarella tarta 500 g'),'mozzarella')
  self.assertEqual(ingredient_match('Cebula czerwona 1 kg'),'cebula czerwona')
  self.assertIsNone(ingredient_match('Ser żółty gouda 500g'))
  self.assertIsNone(ingredient_match('Pierś z kurczaka i mozzarella mix'))
 def test_size(self):
  self.assertEqual(parse_size('Mozzarella tarta 500 g','mozzarella'),(500,'g'))
  self.assertEqual(parse_size('Schab wieprzowy 1,2 kg','schab wieprzowy'),(1200,'g'))
  self.assertIsNone(parse_size('Mozzarella tarta 2x200 g i 500 g','mozzarella'))
 def test_leaflet(self):
  yes,review=extract_candidates(HTML,LEAFLET,TODAY)
  self.assertTrue(any(x['ingredient']=='mozzarella' and x['pack']==500 and x['price']==9.99 for x in yes))
  self.assertTrue(any(x['ingredient']=='przecier pomidorowy' and x['pack']==190 for x in yes))
  self.assertTrue(any(x['ingredient']=='czosnek' and x['pack'] is None for x in review))
  self.assertTrue(any(x['ingredient']=='schab wieprzowy' for x in review))
 def test_no_data_on_unavailable(self):
  class F:
   def get(self,u):raise OSError('Brak internetu')
  with tempfile.TemporaryDirectory() as d:
   result=run(Path(d)/'blix.json',now=TODAY,fetcher=F())
   self.assertEqual(result['status'],'source_unavailable')
   self.assertEqual(result['offers'],[])
   self.assertEqual(json.loads((Path(d)/'blix.json').read_text())['status'],'source_unavailable')
 def test_rss_only_no_claimed_prices(self):
  class F:
   def get(self,url):return RSS if url.endswith('/rss/gazetki') else '<html>Brak ustrukturyzowanych cen</html>'
  with tempfile.TemporaryDirectory() as d:
   r=run(Path(d)/'blix.json',now=TODAY,fetcher=F())
   self.assertEqual(len(r['leaflets']),2)
   self.assertEqual(len(r['offers']),0)

if __name__=='__main__':unittest.main()
