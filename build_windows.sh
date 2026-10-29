#!/usr/bin/env bash
# Build C-Deck.exe (Windows) avec flet pack / PyInstaller, depuis WSL.
# Ne nécessite ni Visual Studio ni le mode développeur Windows.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WIN_PROJECT_DIR="$(wslpath -w "$PROJECT_DIR")"

VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$PROJECT_DIR/c_deck/__init__.py" | head -1)"
VERSION="${VERSION:-0.0.1}"

if [ ! -f "$PROJECT_DIR/.venv/Scripts/python.exe" ]; then
    echo "Erreur : venv Windows introuvable (.venv\\Scripts\\python.exe)." >&2
    echo "Crée-le depuis PowerShell : py -m venv .venv; .\\.venv\\Scripts\\pip install -r requirements.txt" >&2
    exit 1
fi

EXE_PATH="$PROJECT_DIR/dist/C-Deck.exe"
WIN_EXE_PATH="$WIN_PROJECT_DIR\\dist\\C-Deck.exe"

# PyInstaller ne peut pas remplacer l'exe s'il est en cours d'exécution (fichier verrouillé).
if [ -f "$EXE_PATH" ]; then
    if ! powershell.exe -NoProfile -Command "
        try { [IO.File]::Open('$WIN_EXE_PATH', 'Open', 'ReadWrite', 'None').Close(); exit 0 } catch { exit 1 }
    "; then
        echo "Erreur : $WIN_EXE_PATH est verrouillé." >&2
        echo "C-Deck est probablement encore ouvert : ferme l'application puis relance le build." >&2
        exit 1
    fi
fi

BUILD_START="$(date +%s)"
echo "Build de C-Deck $VERSION dans $WIN_PROJECT_DIR\\dist ..."

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "
    \$ErrorActionPreference = 'Stop'
    \$env:PYTHONIOENCODING = 'utf-8'
    Set-Location '$WIN_PROJECT_DIR'
    .\\.venv\\Scripts\\python.exe -m pip install -q -r requirements.txt pyinstaller
    if (\$LASTEXITCODE -ne 0) { exit \$LASTEXITCODE }
    .\\.venv\\Scripts\\flet.exe pack main.py \`
        -n C-Deck \`
        -i assets\\c-deck-icon.ico \`
        --add-data 'assets;assets' \`
        --product-name C-Deck \`
        --product-version $VERSION \`
        --file-version $VERSION.0 \`
        --file-description 'C-Deck command notebook' \`
        -y
    exit \$LASTEXITCODE
"

if [ ! -f "$EXE_PATH" ] || [ "$(stat -c %Y "$EXE_PATH")" -lt "$BUILD_START" ]; then
    echo "Erreur : $WIN_EXE_PATH n'a pas été régénéré (voir la sortie de PyInstaller ci-dessus)." >&2
    exit 1
fi

echo "OK : $WIN_EXE_PATH"
