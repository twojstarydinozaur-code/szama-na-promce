"""Browser smoke test with synthetic source rows, no external network.
Run: python -m unittest tests.test_browser_smoke -v
"""
import datetime as dt
import json
import unittest
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]/'site'

class TestPage(unittest.TestCase):
 def test_auto_price_and_expiry(self):
  today=dt.date.today()
  valid_from=(today-dt.timedelta(days=1)).isoformat()
  valid_to=(today+dt.timedelta(days=6)).isoformat()
  now=dt.datetime.now(dt.timezone.utc).isoformat()
  fake={'source':'https://blix.pl/rss/gazetki','status':'ok','generatedAt':now,'leaflets':[{'store':'Dino','url':'https://blix.pl/sklep/dino/gazetka/537168/','from':valid_from,'to':valid_to}],
   'offers':[{'id':'blix_valid','ingredient':'mozzarella','store':'Dino','product':'Mozzarella 500 g','pack':500,'unit':'g','price':9.99,'regularPrice':12.99,'minQty':1,'from':valid_from,'to':valid_to,'url':'https://blix.pl/sklep/dino/gazetka/537168/','note':'Blix','source':'Blix'},
   {'id':'blix_expired','ingredient':'mozzarella','store':'Lidl','product':'Mozzarella 500 g','pack':500,'unit':'g','price':1.0,'regularPrice':20,'minQty':1,'from':'2025-01-01','to':'2025-01-08','url':'https://blix.pl/sklep/lidl/gazetka/123/','source':'Blix'}],
   'review':[{'ingredient':'czosnek','store':'Dino','product':'Czosnek 5,99 zł','price':5.99,'pack':None,'url':'https://blix.pl/sklep/dino/gazetka/537168/'}], 'errors':[]}
  with sync_playwright() as p:
   browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
   page=browser.new_page()
   errs=[]
   page.on('pageerror',lambda e:errs.append(str(e)))
   # Browser sandbox blocks localhost. Render app in-memory with mocked fetch instead.
   page.evaluate('''(payload) => {
     window.fetch = async () => ({ok:true, json: async () => payload});
   }''',fake)
   html=ROOT.joinpath('index.html').read_text(encoding='utf-8')
   html=html.replace('<script src="offline.js"></script>','')
   page.set_content(html,wait_until='domcontentloaded')
   page.add_script_tag(content=ROOT.joinpath('offline.js').read_text(encoding='utf-8'))
   page.wait_for_timeout(200)
   self.assertEqual(errs,[])
   self.assertIn('1 aktywnych cen automatycznych',page.locator('#content').inner_text())
   page.locator('[data-expand="enchilada"]').click()
   text=page.locator('#recipe_enchilada').inner_text()
   self.assertIn('Dino',text)
   self.assertIn('9,99 zł',text)
   self.assertNotIn('1,00 zł',text)
   page.locator('[data-tab="offers"]').click()
   self.assertIn('Do sprawdzenia',page.locator('#content').inner_text())
   self.assertIn('Czosnek 5,99 zł',page.locator('#content').inner_text())
   self.assertNotIn('1,00 zł',page.locator('#content').inner_text())
   browser.close()

if __name__=='__main__':unittest.main()
