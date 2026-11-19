import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from blix_import import extract_candidates,discount_pct,_read_size
from vision_verify import _promote

LEAF={'url':'https://blix.pl/sklep/lidl/gazetka/537102/','store':'Lidl','from':'2026-11-19','to':'2026-11-21'}
class EnrichmentTests(unittest.TestCase):
 def test_structured_discount_and_old_price(self):
  h='<script>window.offers=[{"name":"Imbir luzem 100 g","price":169,"oldPrice":249,"discountPct":32}]</script>'
  accepted,review=extract_candidates(h,LEAF,None)
  self.assertEqual(len(accepted),1)
  self.assertEqual(accepted[0]['pack'],100)
  self.assertEqual(accepted[0]['regularPrice'],2.49)
  self.assertEqual(accepted[0]['discountPct'],32)
 def test_nested_price_unit_and_fractional_discount(self):
  h='<script>window.offers=[{"name":"Łopatka wieprzowa","pricing":{"price":1099,"oldPrice":1999,"priceUnit":"kg","discountRate":0.45}}]</script>'
  yes,review=extract_candidates(h,LEAF,None)
  self.assertEqual(len(yes),1)
  self.assertEqual(yes[0]['unit'],'g')
  self.assertEqual(yes[0]['pack'],1000)
  self.assertEqual(yes[0]['discountPct'],45)
  self.assertEqual(yes[0]['regularPrice'],19.99)
 def test_visual_price_must_match_html(self):
  record={'ingredient':'imbir','store':'Lidl','product':'Imbir luzem', 'price':1.69,'regularPrice':None,'url':LEAF['url'],'from':LEAF['from'],'to':LEAF['to'],'note':'', 'source':'Blix'}
  vis={'name':'Imbir luzem','price':1.69,'regularPrice':2.49,'discountPct':32,'quantity':100,'unit':'g','coupon':False,'conditions':''}
  out=_promote(record,vis,LEAF['url']+'?pageNumber=2')
  self.assertEqual(out['pack'],100)
  self.assertEqual(out['regularPrice'],2.49)
  self.assertEqual(out['discountPct'],32)
  self.assertIsNone(_promote(record,{**vis,'price':1.99},LEAF['url']))
  self.assertIsNone(_promote(record,{**vis,'coupon':True},LEAF['url']))
 def test_cannot_use_kg_for_recipe_piece(self):
  record={'ingredient':'cytryna','store':'Lidl','price':4.99,'url':LEAF['url']}
  vis={'name':'Cytryny luzem','price':4.99,'regularPrice':11.99,'discountPct':58,'quantity':1,'unit':'kg','coupon':False,'conditions':''}
  self.assertIsNone(_promote(record,vis,LEAF['url']))
 def test_conflicting_discount_cannot_be_promoted(self):
  record={'ingredient':'imbir','price':1.69,'store':'Lidl','url':LEAF['url']}
  vis={'name':'Imbir luzem','price':1.69,'regularPrice':2.49,'discountPct':58,'quantity':100,'unit':'g'}
  self.assertIsNone(_promote(record,vis,LEAF['url']))
 def test_discount_parsing(self):
  self.assertEqual(discount_pct('-58%'),58)
  self.assertEqual(discount_pct(0.58),58)
  self.assertIsNone(discount_pct(None))
if __name__=='__main__':unittest.main()
