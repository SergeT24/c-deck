# C-Deck

Petite application de bureau Flet pour stocker, retrouver, copier, importer et exporter les commandes que tu utilises souvent.

## Lancer

```bash
pip install -r requirements.txt
python main.py
```

Si `pip` ou `venv` n'est pas disponible sous Debian/Ubuntu :

```bash
sudo apt install python3-pip python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Les données sont stockées dans `~/.c-deck/commands.json`.

Si un ancien fichier `~/.jutsudeck/commands.json` ou `~/.command_vault/commands.json` existe, C-Deck le récupère automatiquement au premier lancement.

Les icônes de l'application sont disponibles ici :

```text
assets/c-deck-icon.png
assets/c-deck-icon.ico
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Build Windows rapide (.exe sans Visual Studio)

Depuis WSL, à la racine du projet :

```bash
./build_windows.sh
```

Le script utilise le venv Windows (`.venv\Scripts`), installe PyInstaller si besoin et lance `flet pack`.
Résultat : `dist\C-Deck.exe` (un seul fichier, avec l'icône et la version lue dans `c_deck/__init__.py`).

Ferme C-Deck avant de lancer le build : si l'exe est ouvert (fichier verrouillé), le script s'arrête avec une erreur explicite. Il vérifie aussi à la fin que l'exe a bien été régénéré.

Équivalent manuel depuis PowerShell :

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\flet.exe pack main.py -n C-Deck -i assets\c-deck-icon.ico --add-data "assets;assets" --product-name C-Deck --product-version 0.0.1 --file-version 0.0.1.0 -y
```

Le premier lancement de l'exe est un peu lent (décompression dans un dossier temporaire).

## Build Windows (Flutter, `flet build`)

Le build Windows Flet nécessite trois prérequis côté système :

1. Activer le mode développeur Windows pour autoriser les symlinks :

```powershell
start ms-settings:developers
```

Active ensuite **Mode développeur** dans la fenêtre Windows.

2. Installer Visual Studio ou Visual Studio Build Tools avec le workload :

```text
Desktop development with C++
```

Il faut garder les composants recommandés, notamment MSVC et le Windows SDK.

3. Vérifier que Flutter est accessible dans le terminal qui lance le build. Si Flutter est installé ici :

```text
C:\Users\Serge\flutter\3.44.8\bin
```

tu peux l’ajouter temporairement au terminal PowerShell courant :

```powershell
$env:Path = "C:\Users\Serge\flutter\3.44.8\bin;$env:Path"
```

Puis relancer :

```powershell
.\.venv\Scripts\activate
flet build windows
```

Les erreurs Android de `flutter doctor` ne bloquent pas le build Windows.

## Format JSON

```json
{
  "version": 1,
  "settings": {
    "theme_mode": "light",
    "view_mode": "detailed"
  },
  "commands": [
    {
      "id": "uuid",
      "title": "Moodle purge caches",
      "command": "php admin/cli/purge_caches.php",
      "category": "Moodle",
      "tags": ["moodle", "cache"],
      "variables": [],
      "variable_defaults": {},
      "notes": "A lancer depuis la racine Moodle.",
      "favorite": false,
      "confirm_before_copy": false,
      "use_count": 0,
      "created_at": "2026-10-05T12:00:00",
      "updated_at": "2026-10-05T12:00:00",
      "last_used_at": null
    }
  ]
}
```

Une commande peut contenir jusqu'à 5 variables sous la forme `{{nom_variable}}`.
Exemple :

```json
{
  "title": "Moodle scheduled task",
  "command": "php admin/cli/scheduled_task.php --execute='{{class_task}}'",
  "category": "Moodle",
  "tags": ["moodle", "task"],
  "variables": ["class_task"],
  "variable_defaults": {
    "class_task": "local_dashboard_eticeo\\task\\send_info"
  }
}
```

Au moment de copier, l'application demande la valeur de `class_task`, puis copie la commande finale.

Les anciennes commandes qui déclarent explicitement leurs variables avec `variables` peuvent encore utiliser `$nom_variable`; les nouvelles détections automatiques utilisent `{{nom_variable}}` pour éviter les collisions avec les variables shell comme `$HOME`.

## Raccourcis clavier

| Raccourci | Action |
| --- | --- |
| `Ctrl+F` | Aller dans la recherche |
| `↑` / `↓` | Sélectionner la commande précédente / suivante (hors champs d'édition) |
| `Ctrl+C` | Copier la commande sélectionnée (hors champs d'édition, où il copie le texte normalement) |
| `Ctrl+N` | Nouvelle commande |
| `Ctrl+S` | Enregistrer |
| `Échap` | Annuler les modifications / fermer la boîte de dialogue |
| `F1` | Afficher le récapitulatif des raccourcis |

Dans l'app, le bouton clavier en bas de la barre latérale affiche ce récapitulatif, et le bouton ⓘ affiche la fenêtre « À propos » (nom, version, auteur, emplacement des données).
La version est définie dans `c_deck/__init__.py` (`__version__`) : c'est elle qu'utilisent l'app et `build_windows.sh`.

Si la commande en cours d'édition a été modifiée, changer de commande (clic, flèches, `Ctrl+N`, dupliquer) demande d'abord : **Rester**, **Ignorer** ou **Enregistrer**.

Le bouton **Dupliquer** (à côté de Copier) crée une copie « (copie) » de la commande sélectionnée.

Lors de la copie d'une commande avec variables, les 5 dernières valeurs utilisées pour chaque variable sont proposées sous le champ (stockées dans `variable_history`).

## Recherche avancée

La recherche accepte du texte libre et des filtres :

```text
cache tag:moodle category:Moodle favorite:true danger:false var:class_task used:true
```

Les commandes sensibles (`rm -rf`, `docker compose down -v`, `DROP DATABASE`, etc.) activent une confirmation avant copie.
