#!/usr/bin/env bash
# Build C-Deck.exe (Windows) avec flet pack / PyInstaller.
# Fonctionne depuis WSL ou Git Bash. Ne nécessite ni Visual Studio ni le mode développeur Windows.
set -euo pipefail

STEP="démarrage"
START_TIME="$(date +%s)"

step() {
    STEP="$2"
    echo
    echo "==> [$1/5] $2"
}

info() {
    echo "    $*"
}

on_error() {
    local code=$?
    echo >&2
    echo "ÉCHEC du build à l'étape : $STEP (code $code)" >&2
    echo "Voir les messages ci-dessus pour le détail." >&2
    exit "$code"
}
trap on_error ERR

fail() {
    trap - ERR
    echo >&2
    echo "ÉCHEC : $*" >&2
    exit 1
}

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

step 1 "Vérification de l'environnement"
if command -v wslpath >/dev/null 2>&1; then
    WIN_PROJECT_DIR="$(wslpath -w "$PROJECT_DIR")"
    TASKLIST_FILTER="/FI"
    # Transmet la variable aux exécutables Windows lancés depuis WSL.
    export WSLENV="PYTHONIOENCODING${WSLENV:+:$WSLENV}"
    info "Shell   : WSL"
elif command -v cygpath >/dev/null 2>&1; then
    WIN_PROJECT_DIR="$(cygpath -w "$PROJECT_DIR")"
    # Git Bash convertit "/FI" en chemin : "//FI" l'en empêche.
    TASKLIST_FILTER="//FI"
    info "Shell   : Git Bash"
else
    fail "lance ce script depuis WSL ou Git Bash."
fi
export PYTHONIOENCODING=utf-8

PYTHON=./.venv/Scripts/python.exe
FLET=./.venv/Scripts/flet.exe
[ -f "$PYTHON" ] || fail "venv Windows introuvable (.venv\\Scripts\\python.exe).
Crée-le depuis PowerShell : py -m venv .venv; .\\.venv\\Scripts\\pip install -r requirements.txt"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' c_deck/__init__.py | head -1)"
[ -n "$VERSION" ] || fail "impossible de lire __version__ dans c_deck/__init__.py."
info "Projet  : $WIN_PROJECT_DIR"
info "Version : $VERSION"
info "Python  : $("$PYTHON" -c 'import sys; print(sys.version.split()[0])' | tr -d '\r')"

step 2 "Vérification que C-Deck n'est pas ouvert"
EXE_PATH="dist/C-Deck.exe"
WIN_EXE_PATH="$WIN_PROJECT_DIR\\dist\\C-Deck.exe"
# PyInstaller ne peut pas remplacer l'exe s'il est en cours d'exécution (fichier verrouillé).
if tasklist.exe "$TASKLIST_FILTER" "IMAGENAME eq C-Deck.exe" | tr -d '\r' | grep -qi "C-Deck.exe"; then
    fail "C-Deck est encore ouvert, l'exe ne peut pas être remplacé.
Ferme toutes les fenêtres C-Deck (vérifie aussi la barre des tâches) puis relance le build."
fi
info "OK, aucune instance de C-Deck en cours."

step 3 "Installation des dépendances (requirements.txt + PyInstaller)"
"$PYTHON" -m pip install --disable-pip-version-check -q -r requirements.txt pyinstaller
info "Dépendances à jour."

step 4 "Build de l'exécutable avec flet pack (1 à 2 minutes)"
BUILD_START="$(date +%s)"
"$FLET" pack main.py \
    -n C-Deck \
    -i 'assets\c-deck-icon.ico' \
    --add-data 'assets;assets' \
    --product-name C-Deck \
    --product-version "$VERSION" \
    --file-version "$VERSION.0" \
    --file-description "C-Deck command notebook" \
    -y

step 5 "Vérification du résultat"
[ -f "$EXE_PATH" ] || fail "$WIN_EXE_PATH est introuvable après le build."
[ "$(stat -c %Y "$EXE_PATH")" -ge "$BUILD_START" ] \
    || fail "$WIN_EXE_PATH n'a pas été régénéré (voir la sortie de PyInstaller ci-dessus)."
SIZE_MB="$(( $(stat -c %s "$EXE_PATH") / 1024 / 1024 ))"
DURATION="$(( $(date +%s) - START_TIME ))"

trap - ERR
echo
echo "=========================================================="
echo " SUCCÈS : C-Deck $VERSION a été généré"
echo "   Fichier : $WIN_EXE_PATH"
echo "   Taille  : ${SIZE_MB} Mo"
echo "   Date    : $(date -r "$EXE_PATH" '+%d/%m/%Y %H:%M:%S')"
echo "   Durée   : ${DURATION} s"
echo "=========================================================="
