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

## Build Windows

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

## Recherche avancée

La recherche accepte du texte libre et des filtres :

```text
cache tag:moodle category:Moodle favorite:true danger:false var:class_task used:true
```

Les commandes sensibles (`rm -rf`, `docker compose down -v`, `DROP DATABASE`, etc.) activent une confirmation avant copie.
