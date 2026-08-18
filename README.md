# Mapa rozpuszczonego tlenu w oceanach (BGC-Argo)

Skrypt pobiera pomiary rozpuszczonego tlenu z plywakow BGC-Argo i rysuje z nich
mape swiata: jedna kropka = jeden profil plywaka, kolor = stezenie tlenu
w warstwie przypowierzchniowej.

## Pliki

| Plik | Do czego |
|---|---|
| `argo_tlen.py` | caly kod: pobranie danych, filtrowanie, wykres |
| `requirements.txt` | wersje pakietow przypiete na sztywno (czytelne dla czlowieka) |
| `requirements.lock.txt` | to samo + sumy kontrolne kazdej paczki (do odtwarzania) |
| `.python-version` | wersja Pythona, na ktorej to dziala |
| `odtworz_srodowisko.sh` | buduje `.venv` od zera i robi test dymny |
| `dane_argo.nc` | cache pobranych danych (tworzy sie sam, mozna kasowac) |
| `tlen_mapa.png` | wynikowy wykres |

## Uruchomienie

```bash
bash odtworz_srodowisko.sh        # raz, buduje srodowisko
./.venv/bin/python argo_tlen.py   # rysuje mape
```

Pierwsze uruchomienie skryptu sciaga dane z serwerow Argo i trwa okolo
4 minut. Kazde nastepne czyta z pliku `dane_argo.nc` i zajmuje kilka sekund.
Zeby wymusic swieze pobranie, skasuj `dane_argo.nc`.

## Co mozna zmienic

Wszystkie ustawienia siedza w jednym bloku na gorze `argo_tlen.py`:

- `DATA_OD`, `DATA_DO` - zakres dat (domyslnie styczen 2024),
- `GLEBOKOSC_OD`, `GLEBOKOSC_DO` - warstwa w metrach (domyslnie 0-10 m),
- `OBSZAR` - wycinek swiata; zawezenie do jednego oceanu skraca pobieranie
  do kilkunastu sekund,
- `LIMIT_CZASU`, `PODZIAL` - jak dlugo czekac na serwer i na ile kawalkow
  pociac zapytanie.

## Dlaczego wersje sa przypiete

Trzy rzeczy wywrocily ten projekt przy pierwszym skladaniu. Wszystkie sa juz
zaadresowane w kodzie i w pliku lock, ale warto wiedziec, czego nie ruszac.

**1. `erddapy` musi byc w wersji 2.x.** Od wersji 3.0 usunieto z niego funkcje
`_quote_string_constraints`, ktorej uzywa `argopy` 1.4. Instalacja przechodzi
bez ostrzezenia, a projekt wywala sie dopiero przy `import argopy`. Dlatego
`odtworz_srodowisko.sh` konczy sie testem dymnym, ktory realnie importuje
biblioteki i buduje `DataFetcher` - samo "zainstalowalo sie" nic nie dowodzi.

**2. Wersja Pythona ma znaczenie.** Stack geoprzestrzenny (`cartopy`,
`shapely`, `pyproj`) nie zawsze ma gotowe paczki dla swiezo wydanych wersji
Pythona. Na 3.14 instalacja probuje kompilowac ze zrodel i sie wywraca, stad
`.python-version` przypiety na 3.12.

**3. Jedno globalne zapytanie do Argo nie przechodzi** - serwer zrywa polaczenie
po przekroczeniu limitu czasu (`FSTimeoutError`). Skrypt tnie wiec swiat na
siatke 6 x 3 prostokatow i pobiera je rownolegle.

Osobno, juz po stronie wykresu: cartopy przy wlaczonych podpisach siatki sam
przesuwa tytul osi, a przy wylaczonych podpisach gornej krawedzi wysyla go
w nieskonczonosc. Dlatego tytul jest ustawiony przez `fig.suptitle()`, a nie
`ax.set_title()`, i dlatego nie ma tu `tight_layout()` ani
`bbox_inches="tight"` - oba psuly rysunek. Nie "porzadkuj" tego z powrotem.

## Gdy cos nie wstaje

**`No interpreter found for python 3.12.14`**
Znaczy, ze `uv` nie ma tej konkretnej latki Pythona. W `.python-version` powinno
byc `3.12`, a nie `3.12.14` - kazda latka z linii 3.12 jest rownie dobra,
a przypiecie konkretnej wywala skrypt na maszynie, ktora akurat ma inna.
Sprawdz plik i popraw, jesli ktos go zawezil.

**`No solution found when resolving dependencies`**
Najpewniej `requirements.lock.txt` pochodzi z innej platformy. Lock z sumami
kontrolnymi jest zwiazany z systemem i architektura (tu: Linux x86-64,
CPython 3.12). Na macOS albo ARM przegeneruj go u siebie:

```bash
uv pip compile requirements.txt --generate-hashes -o requirements.lock.txt
```

Zwykly `requirements.txt` przenosi sie miedzy platformami bez zmian.

**`ImportError: cannot import name '_quote_string_constraints'`**
Ktos podniosl `erddapy` do wersji 3.x. Wroc do 2.x - szczegoly nizej.

## Uwagi o danych

Skrypt bierze `DOXY_ADJUSTED` (wartosc po kalibracji eksperckiej), a tam gdzie
jej brak, latae dziury surowym `DOXY`. Zostawia tylko pomiary z flagami jakosci
1 i 2 (dobre / prawdopodobnie dobre). Dla swiezych danych, sprzed kilku
tygodni, udzial wartosci skalibrowanych jest znacznie mniejszy, wiec dokladnosc
mapy bedzie nizsza niz dla okresu sprzed roku.

W `.venv` nie ma `pip` - pakietami zarzadza `uv`. Gdybys potrzebowal klasycznego
pipa w tym srodowisku, dodaj go przez `uv pip install --python .venv/bin/python pip`.
