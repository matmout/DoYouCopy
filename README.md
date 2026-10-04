# MyWhisper

Transcription vocale **100 % locale et hors ligne** pour Windows : faster-whisper (`large-v3-turbo` ou `large-v3`) accéléré par **ROCm** sur GPU AMD Radeon (testé sur RX 7800 XT, gfx1101), avec une fenêtre native PySide6.

| Mode Direct, thème sombre | Transcription terminée, thème clair |
|---|---|
| ![Mode Direct](docs/apercu-direct-sombre.png) | ![Terminé](docs/apercu-termine-clair.png) |

- **Dictée universelle** : maintenez Ctrl+Maj+Espace dans n'importe quelle application, parlez, relâchez : le texte y est collé.
- Enregistrement depuis le micro (Ctrl+R) ou ouverture / glisser-déposer d'un fichier audio ou vidéo (wav, mp3, m4a, flac, ogg, mp4…).
- **Mode Direct** (Ctrl+L) : le texte s'affiche pendant que vous parlez.
- Affichage progressif : chaque segment apparaît dès qu'il est décodé.
- Choix du modèle : **turbo** (rapide, beam 1) ou **large-v3** (précis, beam 5).
- Langue forcée ou détection automatique, filtre des silences (Silero VAD).
- **Vocabulaire** : mots à favoriser, remplacements, commandes vocales de ponctuation.
- Copie (texte brut, horodaté, Markdown) et export **TXT**, **SRT**, **WebVTT**, **Markdown**, **Word** et **JSON**.
- Repli automatique sur CPU (int8) si le GPU est indisponible.

## Comment fonctionne l'accélération AMD

faster-whisper s'appuie sur [CTranslate2](https://github.com/OpenNMT/CTranslate2). Depuis la v4.7.0, CTranslate2 publie des **wheels ROCm officielles pour Windows** (asset `rocm-python-wheels-Windows.zip`), compilées pour gfx1030, gfx110x (dont la RX 7800 XT), gfx115x et gfx120x. Elles s'appuient sur le runtime ROCm 7.2 distribué en paquets pip par AMD (`rocm_sdk_core`, `rocm_sdk_libraries_custom`). Il n'y a **rien à compiler** et **le HIP SDK n'est pas nécessaire**.

Le GPU AMD apparaît sous le device `"cuda"` de CTranslate2 : c'est le nom historique du backend GPU, qui passe ici par HIP.

## Installation

Prérequis :

1. **Pilote AMD Software: Adrenalin Edition** récent ([amd.com](https://www.amd.com/en/support/download/drivers.html)).
2. **Python 3.10 à 3.14 x64** (installé via python.org ; le lanceur `py` doit être disponible). Le script utilise 3.13 par défaut.
3. Environ 8 Go d'espace disque : 1,1 Go de runtime ROCm, ~0,3 Go de dépendances, ~4,6 Go pour les deux modèles.

Puis, depuis la racine du dépôt :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\install_rocm.ps1
```

Le script :

1. crée `.venv` (option `-Python 3.12` pour changer de version) ;
2. installe le runtime ROCm 7.2 depuis `repo.radeon.com` ;
3. télécharge la wheel ROCm de CTranslate2 4.8.2 correspondant à la version de Python et l'installe ;
4. installe MyWhisper et ses dépendances (`constraints.txt` empêche pip de remplacer ctranslate2 par la build CUDA de PyPI) ;
5. lance `scripts/check_gpu.py`, puis télécharge les deux modèles (sauf avec `-SkipModels`).

Les modèles sont stockés dans `%LOCALAPPDATA%\MyWhisper\models`. Pour changer cet emplacement, définissez la variable d'environnement `MYWHISPER_MODELS_DIR` ou la clé `models_dir` des réglages. Une fois les modèles présents, l'application n'a plus besoin du réseau : elle charge toujours le cache local en priorité.

## Utilisation

```powershell
.\.venv\Scripts\mywhisper.exe
# ou
.\.venv\Scripts\python.exe -m mywhisper
```

| Raccourci | Action |
|---|---|
| Ctrl+R | Démarrer / arrêter l'enregistrement |
| Ctrl+L | Démarrer / arrêter le mode Direct |
| Ctrl+O | Importer un fichier |
| Ctrl+S | Exporter en TXT (le menu « Exporter » propose les autres formats) |
| Ctrl+Maj+Espace | Dictée universelle, depuis n'importe quelle application (modifiable) |

Le grand bouton micro démarre et arrête la capture dans le mode choisi au-dessus (Enregistrement ou Direct). Le bouton **Réglages**, en haut à droite, regroupe le filtre des silences, l'horodatage, le vocabulaire, la dictée, le choix du micro et le thème (Système, Sombre ou Clair).

Les réglages sont enregistrés dès qu'ils changent dans `%APPDATA%\MyWhisper\settings.json`. Autres clés utiles :

- `"device"` : `"auto"` (par défaut), `"gpu"` ou `"cpu"` ;
- `"allow_download"` : `false` interdit tout accès réseau, même si un modèle manque.

## Dictée universelle

MyWhisper reste dans la zone de notification avec le modèle chargé. Depuis n'importe quelle application :

- **Maintenir** (par défaut) : gardez **Ctrl+Maj+Espace** enfoncé pendant que vous parlez, relâchez pour insérer le texte ;
- **Basculer** : un appui pour démarrer, un second pour arrêter ;
- **Échap** annule la dictée en cours.

Une pastille en bas de l'écran montre le niveau du micro puis l'état de la transcription. Elle ne prend jamais le focus. Le texte est collé dans la fenêtre active (presse-papiers puis Ctrl+V, l'ancien contenu du presse-papiers est restauré), ou seulement copié si vous choisissez « Copier seulement ».

La section **Dictée** des réglages permet de changer le raccourci (avec Ctrl, Alt, Maj ou Win, ou une touche F seule), le mode, la sortie, le signal sonore, le maintien dans la zone de notification et le démarrage avec Windows. Fermer la fenêtre la réduit dans la zone de notification ; **Quitter** se trouve dans le menu de l'icône.

Limites :

- Windows bloque la saisie simulée vers une fenêtre lancée **en administrateur**. Utilisez alors « Copier seulement », puis Ctrl+V.
- La dictée attend qu'une transcription ou un mode Direct en cours dans la fenêtre principale soit terminé.

## Vocabulaire

**Réglages → Vocabulaire…** :

- **Mots à favoriser** : noms propres, sigles, jargon. Ils sont transmis au décodeur (`hotwords` de faster-whisper) pour toutes les transcriptions.
- **Remplacements** : « Entendu → Écrire », sur des mots entiers, sans tenir compte de la casse. Un motif entre barres obliques (`/(\d+) pour ?cent/` → ` %`) est une expression régulière.
- **Commandes vocales**, dans la dictée universelle : « virgule », « point final », « point d'interrogation », « point d'exclamation », « point-virgule », « deux-points », « points de suspension », « à la ligne », « nouveau paragraphe », « ouvrez / fermez les guillemets », « ouvrez / fermez la parenthèse ». En anglais : *comma, full stop, question mark, new line, new paragraph, open / close quote*… Le mot « point » seul n'est jamais interprété, il est trop courant.

## Exports

| Format | Contenu |
|---|---|
| TXT | un segment par ligne |
| SRT, WebVTT | sous-titres de 2 lignes de 42 caractères au plus, coupés de préférence après la ponctuation, minutés au mot |
| Markdown | un paragraphe par segment, précédé de son horodatage |
| Word (.docx) | un paragraphe par segment |
| JSON | segments et mots avec leurs horodatages |

## Mode Direct

Le bouton **◉ Direct** transcrit en continu, sans attendre la fin d'un enregistrement :

- le texte **gris italique** est provisoire : c'est l'hypothèse en cours, qui peut encore changer ;
- le texte **noir** est validé : il ne bouge plus.

À l'arrêt, le texte est regroupé en phrases. La copie et les exports fonctionnent comme pour un enregistrement.

Whisper ne sait pas traiter un flux audio en continu. MyWhisper re-transcrit donc chaque seconde une fenêtre glissante d'audio, en suivant la méthode LocalAgreement de [whisper_streaming](https://github.com/ufal/whisper_streaming), implémentée dans `core/live.py` :

- un mot est validé quand **deux passes successives** s'accordent dessus et qu'il ne se termine pas au bord de la fenêtre. C'est là que Whisper a tendance à « deviner » la suite de la phrase ;
- les mots déjà validés sont reconnus dans les passes suivantes grâce à leurs timestamps, puis ignorés ;
- l'audio n'est coupé qu'à des endroits sûrs : dans une pause détectée par Silero VAD, ou à une frontière de segment déjà validée si vous parlez plus de 15 s sans pause ;
- aucune passe n'est lancée pendant les silences, ce qui évite les hallucinations.

Durée des passes mesurée sur RX 7800 XT (simulation sur un enregistrement de 42 s) et latences qui en découlent :

| Modèle | Passe moyenne (mesurée) | Texte provisoire (estimé) | Texte validé (estimé) |
|---|---|---|---|
| turbo (recommandé) | ~0,4 s | ~1 à 1,5 s après la parole | ~2 s, ou dès une pause |
| large-v3 | ~0,9 s | ~2 s | ~3 s |

## Diagnostic

```powershell
.\.venv\Scripts\python.exe scripts\check_gpu.py
```

Ce script affiche la version de CTranslate2, la présence du runtime ROCm et le nombre de GPU HIP, puis charge le modèle `tiny` en float16 sur le GPU.

- **`GPU HIP : 0`** : vérifiez le pilote Adrenalin. Vérifiez aussi que `pip show ctranslate2` pointe vers la wheel ROCm, sinon relancez le script d'installation.
- **La pastille en bas à droite indique « CPU · int8 »** : le GPU n'a pas pu être initialisé. Les détails se trouvent dans la console.

## Architecture

```
src/mywhisper/
  app.py              bootstrap : détection GPU (avant Qt), moteur, fenêtre
  config.py           réglages JSON (%APPDATA%\MyWhisper\settings.json)
  gpu/rocm_env.py     choix du device : GPU ROCm (float16) ou CPU (int8)
  core/
    types.py          Segment, ModelSpec, TranscribeOptions, DeviceConfig…
    models.py         registre des modèles (turbo / precise)
    engine.py         Protocol TranscriptionEngine + FasterWhisperEngine
    live.py           mode Direct : fenêtre glissante + accord LocalAgreement
    textproc.py       remplacements et commandes vocales (fonctions pures)
  audio/recorder.py   capture micro 16 kHz mono (sounddevice)
  dictation/
    controller.py     dictée universelle : machine à états raccourci → micro → texte
    hotkey.py         raccourci global (hook clavier WH_KEYBOARD_LL)
    inject.py         collage dans la fenêtre active (SendInput), presse-papiers restauré
    autostart.py      démarrage avec Windows (clé Run de HKCU)
    sounds.py         signaux sonores synthétisés
  export/             exporteurs enregistrés par extension (txt, srt, vtt, md, docx, json)
    subtitles.py      découpage des sous-titres (2 × 42 caractères)
  ui/
    workers.py        ModelWorker : thread unique propriétaire du modèle
    main_window.py    fenêtre : composition et enchaînement des états
    tray.py           icône de la zone de notification
    vocabulary_dialog.py  mots à favoriser, remplacements, commandes vocales
    theme.py          tokens de couleurs (sombre / clair), QSS généré, polices Geist
    widgets/          bouton micro, onde, contrôle segmenté, carte transcript,
                      popover de réglages, notifications, pastille de dictée
    resources/fonts/  Geist et Geist Mono (licence OFL)
scripts/              install_rocm.ps1, check_gpu.py, download_models.py,
                      snapshot_ui.py (captures de l'interface dans chaque état)
tests/                tests unitaires + test GPU de bout en bout (-m gpu)
```

Principes :

- **L'interface ne dépend que du Protocol `TranscriptionEngine`.** Un autre backend (whisper.cpp Vulkan, transformers…) s'ajoute dans `core/` sans toucher l'UI.
- **Un seul thread (`ModelWorker`) possède le modèle.** Les demandes (chargement, transcription) passent par des signaux Qt en file d'attente : pas d'accès concurrent au GPU, et l'UI ne gèle jamais.
- **Les segments sont émis un par un** depuis le générateur de faster-whisper. C'est ce qui produit l'affichage progressif et permet d'annuler entre deux segments.
- **Ajouter un modèle** revient à ajouter une entrée `ModelSpec` dans `core/models.py`. **Ajouter un format d'export** revient à créer une classe avec `suffix`, `label` et `render()`, puis à appeler `register()`.

Le mode Direct et la dictée universelle passent eux aussi par `ModelWorker` : le GPU garde un seul utilisateur. La dictée a ses propres signaux (`dictation_finished`), pour que son texte n'apparaisse pas dans la fenêtre principale.

Prochaines évolutions : voir [docs/ROADMAP.md](docs/ROADMAP.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest           # tests unitaires
.\.venv\Scripts\python.exe -m pytest -m gpu    # transcription réelle sur le GPU (synthèse vocale Windows)
```
