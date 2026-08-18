"""
Mapa rozpuszczonego tlenu w oceanach na podstawie danych BGC-Argo.

Argo to miedzynarodowa siec autonomicznych plywakow dryfujacych w oceanach.
Czesc z nich (tzw. BGC-Argo, biogeochemiczne) ma na pokladzie czujnik tlenu.
Plywak co kilka dni zanurza sie na 2000 m i wynurza, mierzac po drodze
temperature, zasolenie i wlasnie stezenie rozpuszczonego tlenu.

Skrypt pobiera pomiary tlenu z warstwy przypowierzchniowej z calego swiata
za wybrany miesiac i rysuje z nich mape.

Uruchomienie:
    ./.venv/bin/python argo_tlen.py

Pierwsze uruchomienie sciaga dane z serwera (kilkadziesiat sekund do kilku
minut) i zapisuje je do pliku cache. Kazde kolejne czyta juz z dysku.
Zeby wymusic ponowne pobranie, skasuj plik cache (patrz PLIK_CACHE ponizej).
"""

import os
import sys
import warnings

# argopy potrafi sypac ostrzezeniami o wersjach bibliotek - nie zasmiecamy nimi konsoli
warnings.filterwarnings("ignore")

import matplotlib

# "Agg" = rysowanie prosto do pliku, bez otwierania okna.
# Dzieki temu skrypt dziala tez na serwerze bez srodowiska graficznego.
matplotlib.use("Agg")

import cartopy.crs as ccrs
import cartopy.feature as cfeature
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr


# ---------------------------------------------------------------------------
# USTAWIENIA - to jest jedyne miejsce, ktore normalnie chcesz zmieniac
# ---------------------------------------------------------------------------

# Zakres dat (poczatek wlacznie, koniec wylacznie). Domyslnie styczen 2024.
DATA_OD = "2021-01-01"
DATA_DO = "2025-12-01"

# Warstwa przypowierzchniowa w metrach. Interesuje nas tlen "na gorze" oceanu,
# bo to jego stezenie widac potem jako kolor na mapie.
GLEBOKOSC_OD = 0
GLEBOKOSC_DO = 10

# Obszar: caly swiat (dlugosc -180..180, szerokosc -90..90).
OBSZAR = [-18, 18, -90, 90]

# Pliki wyjsciowe (obok skryptu).
KATALOG = os.path.dirname(os.path.abspath(__file__))
PLIK_CACHE = os.path.join(KATALOG, "dane_argo.nc")
PLIK_WYKRESU = os.path.join(KATALOG, "tlen_mapa.png")

# Flagi kontroli jakosci Argo, ktore uznajemy za wiarygodne:
#   1 = dane dobre, 2 = dane prawdopodobnie dobre.
# Reszta (3 = watpliwe, 4 = zle, 9 = brak pomiaru) leci do kosza.
FLAGI_OK = [1, 2]

# Zakres fizycznie sensownych wartosci tlenu w umol/kg.
# Ocean miesci sie w okolicach 0-400; cokolwiek poza tym to awaria czujnika.
TLEN_MIN = 0
TLEN_MAX = 500

# Limit czasu na odpowiedz serwera Argo (w sekundach). Domyslny jest za krotki
# dla zapytan o caly swiat.
LIMIT_CZASU = 900

# Na ile kawalkow pociac zapytanie. Jedno wielkie zapytanie o caly glob serwer
# odrzuca po przekroczeniu limitu czasu, wiec dzielimy mape na siatke
# 6 x 3 = 18 prostokatow i sciagamy je rownolegle.
PODZIAL = {"lon": 6, "lat": 3, "dpt": 1, "time": 1}


# ---------------------------------------------------------------------------
# KROK 1: pobranie danych
# ---------------------------------------------------------------------------


def pobierz_dane():
    """Zwraca surowe pomiary z Argo jako obiekt xarray.

    Jesli plik cache juz istnieje, czyta z dysku zamiast meczyc serwer.
    """
    if os.path.exists(PLIK_CACHE):
        print(f"Czytam dane z cache: {PLIK_CACHE}")
        return xr.open_dataset(PLIK_CACHE)

    print(f"Pobieram dane BGC-Argo za okres {DATA_OD} - {DATA_DO}...")
    print("(pierwsze uruchomienie, zwykle 3-5 minut)")

    # Import w srodku funkcji, zeby skrypt odpalony z gotowym cache
    # nie placil za ladowanie ciezkiej biblioteki.
    import argopy
    from argopy import DataFetcher

    argopy.set_options(api_timeout=LIMIT_CZASU)

    # ds="bgc"        -> zbior biogeochemiczny (tam mieszka tlen)
    # params=["DOXY"] -> DOXY to standardowa nazwa rozpuszczonego tlenu w Argo
    # mode="expert"   -> daje dostep do surowych wartosci i flag jakosci,
    #                    dzieki czemu mozemy filtrowac dane samodzielnie
    # parallel=True   -> pobiera kawalki mapy jednoczesnie zamiast po kolei
    pobieracz = DataFetcher(
        ds="bgc",
        params=["DOXY"],
        mode="expert",
        parallel=True,
        chunks=PODZIAL,
    ).region(OBSZAR + [GLEBOKOSC_OD, GLEBOKOSC_DO, DATA_OD, DATA_DO])
    dane = pobieracz.to_xarray()

    # Zapis do cache. Gdyby sie nie udalo (np. dziwne metadane), lecimy dalej -
    # brak cache to niedogodnosc, nie powod do przerywania pracy.
    try:
        dane.to_netcdf(PLIK_CACHE)
        print(f"Zapisano cache: {PLIK_CACHE}")
    except Exception as blad:
        print(f"Uwaga: nie udalo sie zapisac cache ({blad}). Lece dalej.")

    return dane


# ---------------------------------------------------------------------------
# KROK 2: czyszczenie i uproszczenie danych
# ---------------------------------------------------------------------------


def wybierz_wiarygodny_tlen(df):
    """Dla kazdego pomiaru wybiera najlepsza dostepna wartosc tlenu.

    Argo podaje tlen w dwoch wariantach:
      * DOXY_ADJUSTED - po kalibracji przez eksperta (tryb opozniony),
                        dokladniejszy, ale pojawia sie z opoznieniem,
      * DOXY          - wartosc surowa z czujnika, dostepna od razu.

    Bierzemy skorygowana tam, gdzie istnieje i ma dobra flage jakosci,
    a w pozostalych miejscach lataamy dziury wartoscia surowa.
    """

    def kolumna(nazwa):
        # Kolumny bywaja tekstowe albo z brakami - wymuszamy liczby,
        # a wszystko, czego nie da sie przeliczyc, staje sie brakiem (NaN).
        if nazwa not in df.columns:
            return pd.Series(float("nan"), index=df.index)
        return pd.to_numeric(df[nazwa], errors="coerce")

    tlen_skorygowany = kolumna("DOXY_ADJUSTED")
    qc_skorygowany = kolumna("DOXY_ADJUSTED_QC")
    tlen_surowy = kolumna("DOXY")
    qc_surowy = kolumna("DOXY_QC")

    # .where() zostawia wartosc tam, gdzie warunek jest prawdziwy, reszte kasuje
    dobry_skorygowany = tlen_skorygowany.where(qc_skorygowany.isin(FLAGI_OK))
    dobry_surowy = tlen_surowy.where(qc_surowy.isin(FLAGI_OK))

    # fillna: gdzie brakuje wartosci skorygowanej, wstaw surowa
    return dobry_skorygowany.fillna(dobry_surowy)


def przygotuj_punkty(dane):
    """Zamienia surowe pomiary na jedna kropke na profil: (szerokosc, dlugosc, tlen).

    Plywak podczas jednego wynurzenia robi wiele pomiarow na roznych glebokosciach.
    Wszystkie sa niemal w tym samym miejscu, wiec na mapie zlalyby sie w jedna
    plame. Usredniamy je do jednego punktu na profil.
    """
    df = dane.to_dataframe().reset_index()

    df["TLEN"] = wybierz_wiarygodny_tlen(df)

    # Wyrzucamy pomiary bez tlenu, bez pozycji oraz z wartosciami absurdalnymi
    df = df.dropna(subset=["TLEN", "LATITUDE", "LONGITUDE"])
    df = df[df["TLEN"].between(TLEN_MIN, TLEN_MAX)]

    # Profil = konkretny plywak (PLATFORM_NUMBER) w konkretnym cyklu (CYCLE_NUMBER)
    profile = (
        df.groupby(["PLATFORM_NUMBER", "CYCLE_NUMBER"])
        .agg(
            LATITUDE=("LATITUDE", "mean"),
            LONGITUDE=("LONGITUDE", "mean"),
            TLEN=("TLEN", "mean"),
        )
        .reset_index()
    )

    print(f"Pomiarow po odsianiu slabej jakosci: {len(df)}")
    print(f"Profili do narysowania: {len(profile)}")
    return profile


# ---------------------------------------------------------------------------
# KROK 3: wykres
# ---------------------------------------------------------------------------


def narysuj_mape(profile):
    """Rysuje mape swiata z kropkami w miejscach profili, kolorowanymi stezeniem tlenu."""
    fig = plt.figure(figsize=(14, 7))

    # PlateCarree = najprostsze odwzorowanie: dlugosc i szerokosc jako zwykle osie X i Y
    osie = fig.add_subplot(1, 1, 1, projection=ccrs.PlateCarree())
    osie.set_global()

    # Tlo mapy: ocean na jasno, lad na szaro, cienkie linie brzegowe.
    # Stonowane kolory, zeby kropki z danymi rzucaly sie w oczy, a nie kontynenty.
    osie.add_feature(cfeature.OCEAN, facecolor="#eef3f7")
    osie.add_feature(cfeature.LAND, facecolor="#d9d9d9")
    osie.coastlines(linewidth=0.4, color="#888888")

    # Siatka poludnikow i rownoleznikow z podpisami na dole i po lewej
    siatka = osie.gridlines(
        draw_labels=True, linewidth=0.3, color="gray", alpha=0.4, linestyle="--"
    )
    siatka.top_labels = False
    siatka.right_labels = False

    # Wlasciwe dane. "viridis" to paleta czytelna takze dla osob
    # z zaburzeniami rozpoznawania barw i w druku czarno-bialym.
    kropki = osie.scatter(
        profile["LONGITUDE"],
        profile["LATITUDE"],
        c=profile["TLEN"],
        cmap="viridis",
        s=18,
        alpha=0.9,
        edgecolors="none",
        transform=ccrs.PlateCarree(),  # informuje cartopy, ze wspolrzedne sa geograficzne
        zorder=3,  # rysuj nad tlem mapy
    )

    # Skala kolorow z opisem jednostki
    pasek = fig.colorbar(kropki, ax=osie, orientation="vertical", shrink=0.7, pad=0.02)
    pasek.set_label("Stezenie rozpuszczonego tlenu [umol/kg]", fontsize=11)

    # Tytul celowo na poziomie figury (suptitle), a nie osi (set_title).
    # Cartopy przy wlaczonych podpisach siatki sam przesuwa tytul osi ponad
    # podpisy gornej krawedzi - a gdy te sa wylaczone, wylicza pozycje ze zbioru
    # pustego i wysyla tytul w nieskonczonosc, przez co znika z obrazka.
    fig.suptitle(
        "Rozpuszczony tlen w oceanach - warstwa przypowierzchniowa\n"
        f"BGC-Argo, {DATA_OD} - {DATA_DO}, "
        f"glebokosc {GLEBOKOSC_OD}-{GLEBOKOSC_DO} m, profili: {len(profile)}",
        fontsize=14,
        y=0.96,
    )

    # Uwaga: swiadomie NIE uzywamy tu ani tight_layout(), ani bbox_inches="tight".
    # Oba probuja same wyliczyc ramke rysunku i na mapach cartopy wychodzi im to
    # zle - raz wysypuja rysowanie siatki, raz przycinaja obrazek do samego
    # paska kolorow. Marginesy ustawiamy wiec recznie, ponizej.
    fig.subplots_adjust(left=0.04, right=0.98, top=0.90, bottom=0.06)
    fig.savefig(PLIK_WYKRESU, dpi=150)
    print(f"Zapisano wykres: {PLIK_WYKRESU}")


# ---------------------------------------------------------------------------
# Glowny przebieg
# ---------------------------------------------------------------------------


def main():
    try:
        dane = pobierz_dane()
    except Exception as blad:
        # Najczestszy powod porazki to brak sieci albo chwilowa niedostepnosc
        # serwerow Argo. Zamiast surowego tracebacka - konkretna podpowiedz.
        # Czesc wyjatkow (np. FSTimeoutError) nie niesie zadnej tresci,
        # wiec pokazujemy tez sama nazwe klasy bledu.
        opis = str(blad) or "brak szczegolow"
        print(
            f"\nNie udalo sie pobrac danych z Argo: {type(blad).__name__} ({opis})\n",
            file=sys.stderr,
        )
        print("Co sprawdzic:", file=sys.stderr)
        print("  * czy masz polaczenie z internetem,", file=sys.stderr)
        print(
            "  * czy serwer Argo nie ma przerwy technicznej "
            "(https://erddap.ifremer.fr),",
            file=sys.stderr,
        )
        print(
            "  * przy przekroczeniu limitu czasu: zwieksz LIMIT_CZASU "
            "albo podnies PODZIAL (wiecej, mniejszych kawalkow),",
            file=sys.stderr,
        )
        print(
            "  * czy w wybranym okresie w ogole sa dane - "
            "sprobuj innego miesiaca w DATA_OD / DATA_DO.",
            file=sys.stderr,
        )
        return 1

    profile = przygotuj_punkty(dane)

    if profile.empty:
        print(
            "\nBrak danych spelniajacych kryteria jakosci w wybranym okresie.",
            file=sys.stderr,
        )
        print(
            "Sprobuj szerszego zakresu dat albo wiekszej glebokosci (GLEBOKOSC_DO).",
            file=sys.stderr,
        )
        return 1

    narysuj_mape(profile)
    return 0


if __name__ == "__main__":
    sys.exit(main())
