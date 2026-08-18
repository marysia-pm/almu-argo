#!/usr/bin/env bash
#
# Odtwarza srodowisko Pythona dla skryptu argo_tlen.py, co do wersji.
#
# Uzycie:
#     bash odtworz_srodowisko.sh
#
# Skrypt jest idempotentny - mozna go puszczac wielokrotnie.
# Kasuje istniejacy katalog .venv i buduje go od nowa, wiec jest tez
# lekarstwem na srodowisko, ktore ktos recznie zepsul.

set -euo pipefail

KATALOG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$KATALOG"

WERSJA_PYTHONA="$(cat .python-version)"

echo "==> Srodowisko dla argo_tlen.py"
echo "    katalog: $KATALOG"
echo "    Python : $WERSJA_PYTHONA"
echo

# ---------------------------------------------------------------------------
# 1. uv - menedzer pakietow. Sam potrafi pobrac wlasciwa wersje Pythona,
#    wiec nie zalezymy od tego, co akurat siedzi w systemie.
# ---------------------------------------------------------------------------
export PATH="$HOME/.local/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
    echo "==> Brak uv, instaluje do ~/.local/bin (bez sudo)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi
echo "==> uv: $(uv --version)"

# ---------------------------------------------------------------------------
# 2. Czyste srodowisko na wlasciwej wersji Pythona.
#
#    Przypinamy wersje MINOR (3.12), nie konkretna latke (3.12.14).
#    Powod: gotowe paczki stacku geoprzestrzennego (cartopy, shapely, pyproj)
#    buduje sie osobno dla kazdej wersji minor - i to ona decyduje, czy
#    instalacja pojdzie z gotowca, czy zacznie kompilowac ze zrodel i padnie.
#    Latka nie zmienia tu nic, a przypiecie jej co do numeru wywala skrypt
#    na kazdej maszynie, ktora akurat nie ma dokladnie tego builda:
#        "No interpreter found for python 3.12.14"
#    Kazda 3.12.x jest rownie dobra.
# ---------------------------------------------------------------------------
echo "==> Upewniam sie, ze Python $WERSJA_PYTHONA jest dostepny"
uv python install "$WERSJA_PYTHONA"

echo "==> Buduje czyste .venv"
rm -rf .venv
uv venv --python "$WERSJA_PYTHONA" .venv
echo "    uzyta wersja: $(./.venv/bin/python -c 'import sys; print(sys.version.split()[0])')"

# ---------------------------------------------------------------------------
# 3. Instalacja z pliku lock. --require-hashes sprawia, ze kazda paczka musi
#    zgadzac sie co do sumy kontrolnej. Jesli ktos podmieni zawartosc paczki
#    pod tym samym numerem wersji, instalacja padnie zamiast po cichu wciagnac
#    cos innego niz oryginal.
# ---------------------------------------------------------------------------
echo "==> Instaluje pakiety z requirements.lock.txt (z kontrola sum)"
uv pip install --python .venv/bin/python --require-hashes -r requirements.lock.txt

# ---------------------------------------------------------------------------
# 4. Test dymny. Samo "zainstalowalo sie" nic nie znaczy - liczy sie, czy
#    biblioteki faktycznie sie importuja i czy nie kloca sie wersjami.
#    Dokladnie na tym polegl pierwotny zestaw: erddapy 3.x instalowal sie
#    bez mrugniecia, a argopy wywalalo sie przy imporcie.
# ---------------------------------------------------------------------------
echo "==> Test dymny: probuje zaimportowac biblioteki"
./.venv/bin/python - <<'PYTHON'
import warnings
warnings.filterwarnings("ignore")

import argopy, cartopy, erddapy, matplotlib, numpy, pandas, xarray

print(f"    argopy     {argopy.__version__}")
print(f"    erddapy    {erddapy.__version__}")
print(f"    cartopy    {cartopy.__version__}")
print(f"    matplotlib {matplotlib.__version__}")
print(f"    xarray     {xarray.__version__}")
print(f"    pandas     {pandas.__version__}")
print(f"    numpy      {numpy.__version__}")

# argopy laduje swoje modul pobierania leniwie - samo "import argopy" nie
# wykryloby konfliktu z erddapy. Dlatego dotykamy klasy, ktora go pociaga.
from argopy import DataFetcher
DataFetcher(ds="bgc", params=["DOXY"], mode="expert")
print("    DataFetcher OK")
PYTHON

echo
echo "==> Gotowe. Uruchom wykres:"
echo "    ./.venv/bin/python argo_tlen.py"
