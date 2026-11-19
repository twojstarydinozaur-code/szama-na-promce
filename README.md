# Szama na Promce 5.0 — automatyczny importer Blix (bez logowania w aplikacji)

To rozbudowa projektu v4. **Jeden pulpit, 1200 g mięsa / 6 porcji, pierś z kurczaka z domowych zapasów = 0 zł**. Wyjątkowo duża promocja może uruchomić przepis z 1200 g wieprzowiny. Widok „Składniki i sklepy” wskazuje najtańszą spośród **pobranych i poprawnie rozpoznanych** cen dla każdego składnika.

## Co rzeczywiście działa

1. Importer `scripts/blix_import.py` pobiera oficjalny kanał RSS `https://blix.pl/rss/gazetki` i znajduje aktualne gazetki Biedronki, Lidla, Kauflandu, Dino, Aldi i Auchan.
2. Odwiedza maksymalnie dwie aktualne gazetki na sklep i próbuje odczytać nazwy, ceny i gramatury produktów z publicznie dostępnego HTML, bez wykonywania Javascript i bez obchodzenia blokad.
3. **Tylko produkty z jednoznaczną nazwą składnika, ceną, jednostką, masą opakowania i datami** trafiają do `site/data/blix_promocje.json` jako `offers`. Braki trafiają do `review`; nie są liczone w koszyku. Do ustalenia ceny regularnej wymagane jest niezależne potwierdzenie (importer jej nie zgaduje).
4. Strona wczytuje ten JSON na starcie i przy naciśnięciu „Wczytaj plik ponownie”. Porównuje pobrane oferty z ręcznie dodanymi. Wygasłe i starsze niż 48 godzin dane automatyczne ukrywa. Wszystkie dane użytkownika (ręczne ceny, przepisy, ustawienia) pozostają w jego przeglądarce; nie ma logowania.
5. Workflow `.github/workflows/odswiez_blix.yml` raz dziennie uruchamia importer i publikuje wynik na GitHub Pages. Harmonogram działa po umieszczeniu projektu na własnym GitHub i konfiguracji Pages.

**Uwaga:** publiczne RSS Blixa zawiera *linki do gazetek*, ale nie jest API cenowym. Część gazetek przedstawia ceny wyłącznie na obrazkach, których importer nie odczyta. Dlatego liczba rozpoznanych ofert może być zerowa, a strony lub warunki mogą się zmienić. Nie jest to pełna, przetestowana na żywej witrynie integracja cenowa. Dane z wybranych produktów wymagają sprawdzenia w źródle przed zakupem. Korzystanie z zewnętrznych danych powinno być zgodne z regulaminem i prawami właścicieli. Jeśli serwis blokuje dostęp, skrypt przerywa zamiast omijać blokadę. Jeżeli potrzebne będzie stałe niezawodne pokrycie, należy uzyskać licencjonowany feed cen lub porozumienie z dostawcą.

## 1. Najprostszy sposób na codzienne aktualizacje — GitHub Pages

Potrzebujesz jednorazowo **konta GitHub do publikacji**. **Sama aplikacja nie ma żadnych kont ani logowania**.

1. Wejdź na https://github.com/new i załóż repozytorium, np. `szama-na-promce`. Repozytorium *publiczne* umożliwia prostą publikację na GitHub Pages (bezpłatny limit oraz zasady usług sprawdź przed rozpoczęciem).
2. Wgraj **całą zawartość katalogu projektu**, łącznie z ukrytym folderem `.github` (sam folder `site` nie wystarczy). W repozytorium obok siebie powinny być: `site`, `scripts`, `tests`, `requirements.txt`, `.github/workflows/odswiez_blix.yml`.
3. W `Settings → Pages → Build and deployment → Source` ustaw **GitHub Actions**. Zatwierdź zmiany.
4. W `Actions` wybierz **Odswiez gazetki Blix i opublikuj Szama na Promce** → **Run workflow**. Po pomyślnym zakończeniu strony i importu, w `Settings → Pages` pojawi się adres `https://TWOJ_LOGIN.github.io/szama-na-promce/` (jeśli używasz podanej nazwy repozytorium).
5. Od tego momentu workflow będzie próbował pobierać nowe promocje **codziennie około 07:25 czasu zimowego lub 08:25 letniego** (Github może opóźniać zlecenia). Po aktualizacji wejdź na stronę lub odśwież kartę — nie musisz naciskać „Import CSV”.
6. Pulpit działa na telefonie i komputerze. Ręczne ceny wprowadzone na jednym urządzeniu pozostają tylko tam; żeby przenieść je na drugie, użyj kopii JSON w zakładce „Filmy i przepisy”. **Nie ma automatycznej synchronizacji własnych zmian**, bo świadomie nie wprowadzamy logowania ani serwera z danymi prywatnymi. Automatyczne ceny z Blixa są jednak wspólne dla obu urządzeń po odświeżeniu strony.

**Uwaga na prywatność:** niezabezpieczony link GitHub Pages może otworzyć każda osoba znająca adres. Aplikacja jest przeznaczona do prywatnego użytkowania, ale nie ma blokady dostępu. Nie umieszczaj haseł ani danych osobowych w plikach repozytorium. Ceny i publiczne receptury mogą być widoczne dla innych.

## 2. Test na własnym komputerze (Windows, Python)

W katalogu projektu uruchom PowerShell:

```powershell
py -m pip install -r requirements.txt
py -m unittest discover -s tests -v
py scripts/blix_import.py
cd site
py -m http.server 8000
```

Otwórz `http://localhost:8000` w przeglądarce, potem wejdź w „Ceny z gazetek”. Aby ponowić pobieranie, wróć do folderu głównego projektu w **drugim** oknie terminala i uruchom `py scripts/blix_import.py`. Kliknij „Wczytaj plik ponownie”. W przeciwieństwie do ręcznie otwieranego pliku `file://.../index.html`, tak uruchomiona strona ma dostęp do lokalnego pliku JSON.

Nie uruchamiaj importerów agresywnie ani częściej niż to potrzebne. Używają RSS, sprawdzają robots.txt, ograniczają liczbę stron i robią przerwę pomiędzy zapytaniami.

## 3. Jak sprawdzana jest oferta

Przykład struktury (wyłącznie ilustracyjny, **nie prawdziwa cena aktualnej promocji**):

```json
{
  "ingredient": "mozzarella",
  "store": "Dino",
  "pack": 500,
  "unit": "g",
  "price": 9.99,
  "regularPrice": null,
  "minQty": 1,
  "from": "2026-11-19",
  "to": "2026-11-24",
  "url": "https://blix.pl/sklep/dino/gazetka/537168/",
  "source": "Blix"
}
```

Import automatyczny nie wypełnia `regularPrice`, ponieważ nie każda widoczna kwota jest ceną sprzed obniżki. Dlatego z samych danych bez ceny regularnej można porównywać **koszt zakupów**, ale nie obliczać procentu oszczędności ani kwalifikować promocji na inne mięso do progu 35%/10 zł. Można dopisać **sprawdzoną** cenę regularną ręcznie.

Oferta bez informacji o gramaturze (np. „mozzarella 9,99 zł”) trafia do „Do sprawdzenia”, ponieważ nie wiadomo, czy to paczka 125 g czy 500 g.

## 4. Co będzie potrzebne, aby importer miał 100% pokrycia?

Blix udostępnia nowe gazetki w RSS, ale nie potwierdziliśmy publicznego API gwarantującego komplet cen i warunków dla wszystkich produktów. Pełna automatyzacja graficznych gazetek wymagałaby uprawnionego dostępu do danych produktowych, dodatkowego OCR i kontroli jakości rozpoznania. W takim systemie każda cena powinna mieć link do źródła, daty obowiązywania i oznaczenie pewności.

## 5. Co jest w ZIP?

- `site/index.html`, `site/offline.js`, `site/data/blix_promocje.json` — pulpit plus automatyczny odczyt wygenerowanych danych.
- `scripts/blix_import.py` — moduł RSS i ekstrakcji danych HTML.
- `scripts/youtube_playlist_import.py` — dotychczasowy importer metadanych playlist (wymaga klucza YouTube API).
- `.github/workflows/odswiez_blix.yml` — automatyzacja i publikacja strony.
- `tests/` — testy modułu i test przeglądarkowy (wymaga Chromium/Playwright lokalnie; dla CI skonfiguruj dodatkowo Playwright; sam importer działa na Pythonie).
- `requirements.txt` — biblioteki Python.

## Ograniczenia techniczne środowiska tworzenia projektu

Tu nie można było pobrać bezpośrednio zawartości Blixa z poziomu środowiska wykonującego kod (brak połączenia sieciowego). Testy przeprowadzono na kontrolnych danych HTML/RSS; nie jest to potwierdzenie poprawnego odczytu każdej żywej strony Blix. Nie oznaczamy pliku startowego jako zawierającego aktualne ceny. Po pierwszym rzeczywistym uruchomieniu importera zobaczysz status i liczbę ofert — jeśli będzie 0 lub błąd, trzeba dostosować parser do aktualnej struktury stron albo skorzystać z feedu licencjonowanego.
