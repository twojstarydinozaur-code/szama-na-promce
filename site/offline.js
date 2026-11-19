/* Szama na Promce v4 — jeden pulpit, żadnych kont, żadnego Supabase.
   Wszystkie dane trzymane lokalnie w przeglądarce. Wymiana urządzeń = pełny backup JSON.
   Dane z YouTube to tylko kandydaci: gramaturę zatwierdza człowiek. */
'use strict';
(() => {
 const $=id=>document.getElementById(id);
 const get=(key,defaultValue)=>{try{let a=JSON.parse(localStorage.getItem(key)||'null');return Array.isArray(a)?a:defaultValue}catch{return defaultValue}};
 let videos=get('szama_videos',[]);
 let customRecipes=get('szama_recipes',[]);
 let search='';
 let editorVideo=null;
 let status='';
 const saveExtra=()=>{
   try { localStorage.setItem('szama_videos', JSON.stringify(videos));localStorage.setItem('szama_recipes',JSON.stringify(customRecipes)) }
   catch { status='Brak miejsca w przeglądarce na zapis danych. Zrób kopię zapasową.'; }
 };
 const validRecipe=r=>r && typeof r.id==='string' && /^custom-[A-Za-z0-9_-]{6,70}$/.test(r.id) &&
   typeof r.name==='string' && r.name.length<=150 && ['breast','other'].includes(r.type) &&
   Number.isFinite(r.originalMeat) && r.originalMeat>0 && r.originalMeat<=10000 && Array.isArray(r.ingredients) &&
   r.ingredients.length>=2 && r.ingredients.length<=100 && sourceLink(r.url) &&
   r.ingredients.every(i=>i && typeof i.name==='string' && i.name.length>0 && i.name.length<90 &&
     (i.qty===null||(Number.isFinite(i.qty)&&i.qty>0)) && ['g','ml','szt'].includes(i.unit));
 const apply=()=>{
   customRecipes=customRecipes.filter(validRecipe).slice(0,300);
   RECIPES.splice(DEFAULT_RECIPES.length, RECIPES.length-DEFAULT_RECIPES.length, ...customRecipes);
   ingredientNames=[...new Set(RECIPES.flatMap(r=>r.ingredients.filter(i=>!i.stock).map(i=>i.name)))].sort((a,b)=>a.localeCompare(b,'pl'));
 };
 apply();
 const baseRender=render;
 render=function(){baseRender(); if(state.tab==='videos')renderVideos($('content'))};
 function boxMsg(){return status?`<p class="notice">${esc(status)}</p>`:''}
 function renderVideos(el){
   const filtered=videos.filter(v=>((v.tytul||'')+' '+(v.opis||'')).toLowerCase().includes(search.toLowerCase())).slice(0,60);
   let html=`<div class="panel"><h2>📺 Filmy i własne przepisy</h2>
     <p class="muted">Importuj katalog filmów z pięciu playlist Policzona Szama. Film sam w sobie <b>nie jest jeszcze sprawdzonym przepisem</b> — ilości składników musisz zatwierdzić przed dodaniem do rankingu.</p>
     ${boxMsg()}<div class="pair"><div><label class="label" for="videoFile">Import pliku filmy_youtube.json</label><input type="file" id="videoFile" accept=".json,application/json"></div>
     <div><label class="label" for="videoQuery">Wyszukaj wśród ${videos.length} filmów</label><input id="videoQuery" placeholder="np. kurczak, curry, lunchbox" value="${esc(search)}"></div></div>
     <div class="row" style="margin:14px 0"><span class="muted small">${customRecipes.length} własnych przepisów, sprawdzonych ręcznie</span><button class="subtle" id="newRecipe">+ Dodaj przepis</button></div>
     <div id="recipeEditor"></div></div>`;
   html+=`<div class="panel" style="margin-top:14px"><h3>Kandydaci z filmów (${filtered.length})</h3>`;
   if(!filtered.length)html+='<p class="muted small">Nie zaimportowano filmów albo wyszukiwanie nie znalazło dopasowań. Skorzystaj z dołączonego skryptu YouTube API.</p>';
   for (const v of filtered) html+=`<div class="item-card"><b>${esc(v.tytul)}</b><p>${esc((v.opis||'').slice(0,220))}</p>
      <a class="link small" href="${esc(v.url)}" rel="noopener" target="_blank">Zobacz film ↗</a>
      <button class="subtle" data-start-recipe="${esc(v.video_id)}" style="margin-left:9px">Dodaj zweryfikowany przepis</button></div>`;
   html+='</div>';
   if(customRecipes.length){html+='<div class="panel" style="margin-top:14px"><h3>Twoje własne wpisy</h3>';
      for(const r of customRecipes)html+=`<div class="item-card"><b>${esc(r.name)}</b><p>${r.type==='other'?esc(r.meatName)+' · ':'Kurczak · '}${r.ingredients.length} składników</p><button class="subtle danger" data-remove-recipe="${esc(r.id)}">Usuń</button></div>`;
      html+='</div>';
   }
   html+=`<div class="panel" style="margin-top:14px"><h3>📦 Przenieś dane na drugi telefon / komputer</h3>
   <p class="muted small">Bez logowania dane są zapisane oddzielnie w każdej przeglądarce. Eksport obejmuje wszystkie oferty, przeliczniki, playlisty i przepisy. Import <b>zastępuje</b> dotychczasowe dane na drugim urządzeniu.</p>
   <div class="pair"><div><button class="primary full" id="exportFull">⬇ Pobierz pełną kopię danych</button></div>
   <div><label class="small" for="importFull">Wczytaj kopię JSON</label><input id="importFull" type="file" accept=".json,application/json"></div></div>
   <p class="tip">Nie ma publicznej bazy, automatycznej synchronizacji ani żadnego ekranu logowania. Jeżeli wyczyścisz dane przeglądarki bez wykonania kopii, lokalne wpisy mogą zniknąć.</p></div>`;
   el.innerHTML=html;
   if(editorVideo!==null)showEditor(editorVideo);
 }
 function showEditor(videoId){
   editorVideo=videoId;
   const v=videos.find(x=>x.video_id===videoId);
   $('recipeEditor').innerHTML=`<hr class="hr"><h3>Nowy, zweryfikowany przepis</h3>
   <form id="recipeForm"><div class="pair">
   <div><label class="label">Nazwa dania</label><input name="name" required maxlength="120" value="${esc(v?.tytul||'')}"></div>
   <div><label class="label">Rodzaj mięsa</label><select name="type" id="meatType"><option value="breast">Pierś z kurczaka — z zapasów</option><option value="other">Inne mięso — tylko super promocja</option></select></div>
   <div><label class="label">Masa mięsa w oryginale (g)</label><input name="originalMeat" type="number" min="1" max="10000" required placeholder="np. 600"></div>
   <div><label class="label">Nazwa innego mięsa (gdy dotyczy)</label><input name="meatName" placeholder="np. schab wieprzowy"></div>
   <div style="grid-column:1/-1"><label class="label">Oryginalny link</label><input type="url" name="url" required value="${esc(v?.url||'')}"></div>
   <div style="grid-column:1/-1"><label class="label">Krótki opis</label><input name="desc" maxlength="180"></div></div>
   <label class="label">Składniki w ORYGINALNEJ ilości (nazwa;ilość;g/ml/szt;stock tylko dla piersi)</label>
   <textarea name="ingredients" required placeholder="pierś z kurczaka;600;g;stock&#10;ryż basmati;300;g&#10;passata pomidorowa;700;g"></textarea>
   <p class="tip">Dla schabu np. <code>schab wieprzowy;450;g</code> — bez <code>stock</code>. Cena kurczaka jest zawsze pomijana, ale inne mięso wliczamy do wydatków. Pola bez dokładnej gramatury zostaw puste po drugim średniku.</p>
   <p><label><input style="width:auto" name="verified" type="checkbox" required> Sprawdziłem składniki i ilości u autora przepisu.</label></p>
   <button type="submit" class="primary">Zapisz przepis</button> <button type="button" id="cancelRecipe" class="subtle">Anuluj</button></form>`;
 }
 function parseRecipe(fd){
   if(!fd.verified)throw Error('Potwierdź weryfikację przepisu.');
   const originalMeat=Number(fd.originalMeat);
   if(!(originalMeat>0&&originalMeat<=10000))throw Error('Nieprawidłowa masa mięsa.');
   const type=fd.type==='other'?'other':'breast';
   const meatName=type==='breast'?'pierś z kurczaka':String(fd.meatName||'').trim().toLocaleLowerCase('pl');
   if(!meatName)throw Error('Podaj dokładną nazwę mięsa z przepisu.');
   const ingredients=String(fd.ingredients||'').split(/\r?\n/).filter(x=>x.trim()).map(line=>{
     const [name,raw,unit,flag]=line.split(';').map(x=>x.trim());
     const qty=raw===''?null:Number(raw?.replace(',','.'));
     if(!name||!['g','ml','szt'].includes(unit)||(qty!==null&&!(qty>0))||!(name.length<90))throw Error('Błędny składnik: '+line);
     return {name:name.toLocaleLowerCase('pl'),qty,unit,stock:flag==='stock'};
   });
   if(ingredients.length<2||ingredients.length>100)throw Error('Potrzebujesz od 2 do 100 składników.');
   const primary=ingredients.filter(i=>i.name===meatName&&i.qty===originalMeat&&i.unit==='g');
   if(primary.length!==1)throw Error(`Dodaj wiersz: ${meatName};${originalMeat};g`);
   if(type==='breast')primary[0].stock=true;
   else if(ingredients.some(i=>i.stock))throw Error('Innego mięsa nie oznaczaj jako stock — wliczamy je do zakupów.');
   const r={id:'custom-'+crypto.randomUUID().replace(/-/g,''),name:String(fd.name||'').trim().slice(0,120),type,meatName,
     desc:String(fd.desc||'').slice(0,180),originalMeat,originalServings:6,url:sourceLink(String(fd.url||'')),
     youtube:String(fd.url||'').includes('youtube')?String(fd.url):null,
     note:'Przepis ręcznie zweryfikowany z oryginałem. '+(type==='other'?'Wyświetlany przy wyjątkowej promocji na mięso.':'Pierś kurczaka z zapasów.'),ingredients};
   if(!validRecipe(r))throw Error('Nieprawidłowa nazwa, źródło lub składniki przepisu.');
   return r;
 }
 function normalizeVideo(v){
   const video_id=String(v.video_id||v.id||'').trim();
   if(!/^[A-Za-z0-9_-]{11}$/.test(video_id))throw Error('Nieprawidłowy identyfikator filmu.');
   return {video_id,tytul:String(v.tytul||v.title||'').slice(0,220),opis:String(v.opis||v.description||'').slice(0,12000),
     opublikowano:String(v.opublikowano||'').slice(0,32),url:'https://www.youtube.com/watch?v='+video_id};
 }
 function fullBackup(){
   const payload={format:'szama-na-promce-v4',createdAt:new Date().toISOString(),prefs:{chicken:state.chicken,portions:state.portions,sort:state.sort,kind:state.kind,stores:[...state.stores],overrides:state.overrides},offers:state.offers,customRecipes,videos};
   download('szama-na-promce-kopia.json',JSON.stringify(payload,null,2),'application/json');
 }
 async function fullRestore(file){
   if(file.size>15_000_000)throw Error('Plik kopii za duży (maks. 15 MB).');
   const data=JSON.parse(await file.text());
   if(data.format!=='szama-na-promce-v4'||!Array.isArray(data.offers)||!Array.isArray(data.videos)||!Array.isArray(data.customRecipes)||!data.prefs)throw Error('To nie jest pełna kopia danych v4.');
   if(data.offers.length>5000||data.videos.length>3000||data.customRecipes.length>300)throw Error('Kopia przekracza limity.');
   const restoredRecipes=data.customRecipes.filter(validRecipe);
   if(restoredRecipes.length!==data.customRecipes.length)throw Error('Kopia zawiera nieprawidłowy przepis.');
   const oldIngredientNames=ingredientNames;
   let nextOffers;
   try {
     ingredientNames=[...new Set([...ingredientNames,...restoredRecipes.flatMap(r=>r.ingredients.filter(i=>!i.stock).map(i=>i.name))])];
     nextOffers=data.offers.map(asOffer);
   } finally { ingredientNames=oldIngredientNames; }
   const nextVideos=data.videos.map(normalizeVideo);
   if(!confirm('Wczytać kopię? Zastąpi wszystkie dotychczasowe ceny, przepisy i filmy na tym urządzeniu.'))return;
   customRecipes=restoredRecipes;videos=nextVideos;apply();
   state.offers=nextOffers;
   state.chicken=Math.min(10000,Math.max(100,Number(data.prefs.chicken)||1200));
   state.portions=Math.min(30,Math.max(1,Number(data.prefs.portions)||6));
   state.kind=['special','chicken','all'].includes(data.prefs.kind)?data.prefs.kind:'special';
   state.sort=['saving','price','coverage'].includes(data.prefs.sort)?data.prefs.sort:'saving';
   state.stores=new Set((data.prefs.stores||STORES).filter(s=>STORES.includes(s)));
   state.overrides=data.prefs.overrides&&typeof data.prefs.overrides==='object'?data.prefs.overrides:{};
   save();saveExtra();status='Kopia zaimportowana. Dane zapisano na tym urządzeniu.';editorVideo=null;render();
 }
 document.addEventListener('click',e=>{
   const start=e.target.closest('[data-start-recipe]');
   if(start){showEditor(start.dataset.startRecipe);return}
   if(e.target.id==='newRecipe'){showEditor('');return}
   if(e.target.id==='cancelRecipe'){editorVideo=null;render();return}
   if(e.target.id==='exportFull'){fullBackup();return}
   const rem=e.target.closest('[data-remove-recipe]');
   if(rem&&confirm('Usunąć ten przepis?')){customRecipes=customRecipes.filter(r=>r.id!==rem.dataset.removeRecipe);apply();saveExtra();render();}
 });
 document.addEventListener('input',e=>{if(e.target.id==='videoQuery'){
   search=e.target.value;
   const cur=e.target.selectionStart;
   // Odświeżamy tylko listę kandydatów, aby użytkownik nie tracił kursora.
   clearTimeout(window.__szamaSearchTimer);
   window.__szamaSearchTimer=setTimeout(()=>{if(state.tab==='videos'){render();$('videoQuery')?.focus();$('videoQuery')?.setSelectionRange(cur,cur)}},220);
 }});
 document.addEventListener('change',async e=>{
   if(e.target.id==='videoFile'&&e.target.files?.[0]){
     try{
       const p=JSON.parse(await e.target.files[0].text());
       if(!Array.isArray(p)||p.length>3000)throw Error('Lista musi zawierać do 3000 filmów.');
       const next=p.map(normalizeVideo);
       const map=new Map(videos.map(v=>[v.video_id,v]));next.forEach(v=>map.set(v.video_id,v));
       videos=[...map.values()];saveExtra();status='Importowano '+next.length+' filmów. Możesz zatwierdzać przepisy.';render();
     }catch(err){alert('Nie udało się wczytać filmów: '+err.message)}
   }
   if(e.target.id==='importFull'&&e.target.files?.[0]){
     try{await fullRestore(e.target.files[0])}catch(err){alert('Nie udało się wczytać kopii: '+err.message)}
   }
 });
 document.addEventListener('submit',e=>{
   if(e.target.id!=='recipeForm')return;
   e.preventDefault();
   try {const r=parseRecipe(Object.fromEntries(new FormData(e.target)));customRecipes.push(r);apply();saveExtra();
     editorVideo=null;state.tab='recipes';state.kind='special';status='Zapisano przepis';save();render();}
   catch(err){alert(err.message)}
 });
 render();
})();
