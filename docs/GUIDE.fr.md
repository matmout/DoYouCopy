# DoYouCopy : guide détaillé

Transcription vocale **100 % locale et hors ligne** pour Windows : faster-whisper (`large-v3-turbo` ou `large-v3`) accéléré par **ROCm** sur GPU AMD Radeon (testé sur RX 7800 XT, gfx1101), avec une fenêtre native PySide6.

*English version: [GUIDE.en.md](GUIDE.en.md).*

| Mode Direct, thème sombre | Transcription terminée, thème clair |
|---|---|
| ![Mode Direct](apercu-direct-sombre.png) | ![Terminé](apercu-termine-clair.png) |

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

## Installation (utilisateurs)

Téléchargez et lancez `DoYouCopy-Setup-<version>.exe` (Windows 10 / 11, 64 bits). L'installation se fait dans votre profil, **sans droits administrateur**. L'installeur propose deux raccourcis : **dans le menu Démarrer** (coché par défaut) et **sur le Bureau**. Vous pourrez les ajouter ou les retirer plus tard dans les réglages (Général → Raccourcis). À la fin :

1. l'installeur **détecte la carte graphique** et télécharge l'accélération correspondante depuis les sources officielles, avec des versions et des empreintes SHA-256 figées :

   | Carte | Accélération | Téléchargement |
   |---|---|---|
   | NVIDIA GeForce GTX 900 et plus récentes, RTX | CUDA 12 (cuBLAS + cuDNN 9) | ~1,2 Go |
   | AMD Radeon RX 6800 / 6900, RX 7000, RX 9000, Radeon 780M / 880M / 890M | ROCm 7.2 | ~1,2 Go |
   | Autres (Intel, AMD plus anciennes, aucune carte) | aucune : processeur | — |

   La carte est ensuite testée réellement. En cas d'échec (pilote trop ancien), DoYouCopy utilise le processeur et l'explique.
2. au **premier lancement**, le modèle Turbo (~1,6 Go) se télécharge avec une barre de progression. Le modèle Précis (~3 Go) se télécharge la première fois qu'on le choisit.

Sans accélération, un bandeau « **Transcription plus lente sur cette machine** » en donne la raison. Si une carte compatible est présente, le bouton **Installer l'accélération** télécharge ce qu'il faut, puis redémarre DoYouCopy.

L'installeur n'est pas encore signé : Windows SmartScreen affiche « Windows a protégé votre ordinateur ». Cliquez sur **Informations complémentaires**, puis sur **Exécuter quand même**.

La désinstallation (Paramètres → Applications) supprime l'application, ses raccourcis (y compris ceux créés depuis les réglages) et l'accélération graphique. Elle propose aussi de supprimer l'historique (dictées, transcriptions et enregistrements audio), les modèles et les réglages.

## Installation (développement, depuis les sources)

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
4. installe DoYouCopy et ses dépendances (`constraints.txt` empêche pip de remplacer ctranslate2 par la build CUDA de PyPI) ;
5. lance `scripts/check_gpu.py`, puis télécharge les deux modèles (sauf avec `-SkipModels`).

Les modèles sont stockés dans `%LOCALAPPDATA%\DoYouCopy\models`. Pour changer cet emplacement, définissez la variable d'environnement `DOYOUCOPY_MODELS_DIR` ou la clé `models_dir` des réglages. Une fois les modèles présents, l'application n'a plus besoin du réseau : elle charge toujours le cache local en priorité.

## Utilisation

```powershell
.\.venv\Scripts\doyoucopy.exe
# ou
.\.venv\Scripts\python.exe -m doyoucopy
```

| Raccourci | Action |
|---|---|
| Ctrl+R | Démarrer / arrêter l'enregistrement |
| Ctrl+L | Démarrer / arrêter le mode Direct |
| Ctrl+O | Importer un fichier |
| Ctrl+S | Exporter en TXT (le menu « Exporter » propose les autres formats) |
| Ctrl+Maj+Espace | Dictée universelle, depuis n'importe quelle application (modifiable) |
| Ctrl+H | Afficher / masquer l'historique |
| Ctrl+E | Modifier la transcription |
| Ctrl+Espace | Lecture / pause de l'audio |
| Ctrl+← | Reculer de 5 secondes |

Le grand bouton micro démarre et arrête la capture dans le mode choisi au-dessus (Enregistrement ou Direct), avec la source choisie à côté : **Micro**, **Ordinateur** (ce qui sort des haut-parleurs : réunion Teams/Zoom, vidéo) ou **Les deux**, mixés. La capture de l'ordinateur utilise le périphérique de sortie par défaut de Windows ; prévenez les participants avant d'enregistrer une réunion. En haut, le choix du modèle (**Léger**, **Turbo**, **Précis**) et de la langue. Le bouton **Réglages** ouvre les réglages rapides : silences, horodatage, vocabulaire, micro, thème. **Tous les réglages…** ouvre la fenêtre complète.

## Réglages

Chaque changement s'applique tout de suite et est enregistré dans `%APPDATA%\DoYouCopy\settings.json`. Si ce fichier est abîmé ou modifié à la main avec une valeur invalide, seule cette valeur revient à son défaut (un avertissement est écrit dans le journal).

Les raccourcis et le démarrage avec Windows ne sont pas des réglages : les cases reflètent les fichiers réellement présents (raccourcis `.lnk`, clé `Run` du registre). Depuis les sources, le raccourci lance `pythonw.exe -m doyoucopy` avec l'icône de l'application.

| Section | Réglages |
|---|---|
| Général | thème, taille du texte, horodatage, **langue de l'interface** (celle de Windows, français ou anglais ; appliquée au redémarrage), micro, zone de notification, démarrage avec Windows, **raccourcis sur le Bureau et dans le menu Démarrer**, retour aux réglages par défaut (le vocabulaire est conservé) |
| Transcription | langue parlée, plusieurs langues dans le même audio, **traduction en anglais**, contexte (sujet, noms, style), vocabulaire, qualité de recherche (*beam size*), utilisation du texte précédent, **transcription des fichiers par lots** (3 à 4× plus rapide sur GPU) |
| Silences | filtre des silences (VAD) avec sa sensibilité et la pause minimale, suppression du texte inventé pendant les longs silences, seuil « pas de parole », pénalité de répétition |
| Dictée | raccourci, mode Maintenir / Basculer, coller ou copier, espace après le texte, commandes vocales, signal sonore |
| Mode Direct | intervalle entre passes, silence de fin de phrase |
| Exports | format de Ctrl+S, caractères par ligne et lignes par sous-titre |
| Historique | enregistrement automatique, dictées conservées ou non, audio des enregistrements conservé (FLAC) et durée de conservation, ouverture du dossier, effacement complet |
| Modèles | modèle utilisé, modèles téléchargés (taille, suppression), dossier des modèles, mode hors ligne strict |
| Matériel | **calcul sur la carte graphique ou le processeur**, précision (float16, int8_float16, int8…), threads du processeur, état de la carte et installation de l'accélération, **informations de diagnostic** et dossier des journaux |

Le passage du GPU au processeur (et inversement), la précision, les threads et le dossier des modèles s'appliquent sans redémarrer : le modèle est rechargé après la transcription en cours. Les modèles disponibles :

| Modèle | Taille | Usage |
|---|---|---|
| Léger (small) | 0,5 Go | ordinateurs sans carte graphique |
| Turbo (large-v3-turbo) | 1,6 Go | le meilleur compromis (par défaut) |
| Précis (large-v3) | 3,1 Go | la meilleure précision ; le seul à bien traduire vers l'anglais |

## Dictée universelle

DoYouCopy reste dans la zone de notification avec le modèle chargé. Depuis n'importe quelle application :

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

Whisper ne sait pas traiter un flux audio en continu. DoYouCopy re-transcrit donc chaque seconde une fenêtre glissante d'audio, en suivant la méthode LocalAgreement de [whisper_streaming](https://github.com/ufal/whisper_streaming), implémentée dans `core/live.py` :

- un mot est validé quand **deux passes successives** s'accordent dessus et qu'il ne se termine pas au bord de la fenêtre. C'est là que Whisper a tendance à « deviner » la suite de la phrase ;
- les mots déjà validés sont reconnus dans les passes suivantes grâce à leurs timestamps, puis ignorés ;
- l'audio n'est coupé qu'à des endroits sûrs : dans une pause détectée par Silero VAD, ou à une frontière de segment déjà validée si vous parlez plus de 15 s sans pause ;
- aucune passe n'est lancée pendant les silences, ce qui évite les hallucinations.

Durée des passes mesurée sur RX 7800 XT (simulation sur un enregistrement de 42 s) et latences qui en découlent :

| Modèle | Passe moyenne (mesurée) | Texte provisoire (estimé) | Texte validé (estimé) |
|---|---|---|---|
| turbo (recommandé) | ~0,4 s | ~1 à 1,5 s après la parole | ~2 s, ou dès une pause |
| large-v3 | ~0,9 s | ~2 s | ~3 s |

## Construire l'installeur

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
```

Prérequis : le `.venv` de développement et [Inno Setup 6](https://jrsoftware.org/isinfo.php) (`winget install JRSoftware.InnoSetup`). Le script :

1. embarque la wheel CTranslate2 de PyPI (CPU + CUDA), vérifiée par son empreinte ;
2. construit l'application avec PyInstaller en mode dossier, sans console ni UPX ;
3. vérifie que l'exécutable charge son moteur (`DoYouCopy.exe --probe`) ;
4. compile `dist\DoYouCopy-Setup-<version>.exe` avec Inno Setup (~90 Mo).

Pour signer l'installeur, passez `-CertFile cert.pfx` (mot de passe dans `DOYOUCOPY_SIGN_PASSWORD`) ou `-CertThumbprint <empreinte>`. Le script utilise alors `signtool` du Windows SDK.

Options de l'exécutable :

| Option | Rôle |
|---|---|
| `--setup-runtime` | détecte la carte et installe son accélération (lancée par l'installeur) |
| `--probe fichier.json` | écrit ce que voit CTranslate2 (nombre de GPU, types de calcul) |
| `--minimized` | démarre dans la zone de notification (démarrage avec Windows) |

L'accélération est installée dans `%LOCALAPPDATA%\DoYouCopy\runtime` (variable `DOYOUCOPY_RUNTIME_DIR` pour un autre emplacement). Le journal de l'application packagée se trouve dans `%LOCALAPPDATA%\DoYouCopy\logs`.

## Construire le paquet Microsoft Store (MSIX)

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipInstaller
powershell -ExecutionPolicy Bypass -File scripts\build_msix.ps1
```

Prérequis : le Windows SDK (`makeappx`, `makepri`). Le paquet `dist\DoYouCopy-<version>-x64.msix` n'est pas signé : le Store le signe à la soumission. `-DevSign` le signe avec un certificat de test pour l'installer sur sa machine, `-Wack` lance les tests de certification. Identité, différences de comportement et procédure de soumission : [STORE.fr.md](STORE.fr.md).

## Historique

Chaque transcription (enregistrement, Direct, fichier) est enregistrée automatiquement dans `%LOCALAPPDATA%\DoYouCopy\history`, base SQLite avec recherche plein texte (FTS5). Les longues sessions sont sauvegardées toutes les 30 secondes : un plantage ne fait perdre que les dernières secondes. Le panneau **Historique** (Ctrl+H) liste les sessions : la recherche ignore les accents et trouve les débuts de mots, un clic ouvre une transcription, le clic droit permet de la renommer (F2), de l'ajouter aux favoris ou de la supprimer (Suppr).

L'audio des enregistrements micro et Direct est conservé en FLAC (environ 60 Mo par heure), puis supprimé après 30 jours par défaut ; le texte reste. Supprimer une transcription supprime aussi son audio, même s'il est ouvert dans le lecteur ; au démarrage, les fichiers audio qui ne correspondent plus à aucune transcription (suppression refusée par Windows, plantage pendant l'encodage) sont effacés. Les fichiers importés ne sont pas copiés : le lecteur rejoue le fichier d'origine tant qu'il existe. Le texte des dictées universelles est conservé aussi (jamais leur audio), sauf si l'option est désactivée dans les réglages.

## Éditeur synchronisé

Quand l'audio est disponible, un lecteur apparaît sous la transcription : lecture, recul de 5 s, vitesse de 0,5× à 2×. Le mot prononcé est surligné et un clic sur un mot y amène la lecture. Les mots dont le modèle est peu sûr (probabilité inférieure à 50 %, fichiers importés) sont soulignés en rouge.

**Modifier** (Ctrl+E) rend le texte éditable : une ligne par segment, si bien que les horodatages restent justes pour les sous-titres. Recliquez sur **Modifier** pour valider ; les corrections sont enregistrées dans l'historique. Le clic droit sur un passage propose **Retranscrire avec le modèle Précis** : seuls les segments sélectionnés repassent dans large-v3, puis le modèle courant est rechargé.

## Diagnostic

**Réglages > Matériel > Copier les informations de diagnostic** copie un rapport à joindre à un signalement : Windows, carte graphique et pilote, cartes vues par CTranslate2, versions des bibliothèques, modèles présents, réglages et dernières erreurs du journal. Le rapport ne contient ni transcription, ni vocabulaire, ni contexte. Le journal de l'application est dans `%LOCALAPPDATA%\DoYouCopy\logs\doyoucopy.log` (bouton **Ouvrir le dossier des journaux**).

```powershell
.\.venv\Scripts\python.exe scripts\check_gpu.py
```

Ce script affiche la version de CTranslate2, la présence du runtime ROCm et le nombre de GPU HIP, puis charge le modèle `tiny` en float16 sur le GPU.

- **`GPU HIP : 0`** : vérifiez le pilote Adrenalin. Vérifiez aussi que `pip show ctranslate2` pointe vers la wheel ROCm, sinon relancez le script d'installation.
- **La pastille en bas à droite indique « Processeur · int8 »** : le GPU n'a pas pu être initialisé. Le bandeau en donne la raison, et les détails se trouvent dans le journal.

## Architecture

```
src/doyoucopy/
  app.py              bootstrap : détection GPU (avant Qt), moteur, fenêtre
  config.py           réglages JSON (%APPDATA%\DoYouCopy\settings.json), validés valeur par valeur
  session.py          SessionController : capture, transcription, corrections, résultat courant (sans Qt Widgets)
  history_controller.py  HistoryController : entrée courante, sauvegarde auto, audio et dictées conservés (sans Qt Widgets)
  diagnostics.py      journal, exceptions non rattrapées, rapport de diagnostic
  i18n.py             langue de l'interface : tr("texte français") → traduction, choisie au démarrage
  locales/en.py       traductions anglaises (clé = texte français)
  storage/
    history.py        historique SQLite + FTS5, rétention de l'audio
    audio.py          audio conservé en FLAC (PyAV), repli WAV
  gpu/rocm_env.py     choix du device : GPU ROCm (float16) ou CPU (int8)
  core/
    types.py          Segment, ModelSpec, TranscribeOptions, DeviceConfig…
    models.py         registre des modèles (turbo / precise)
    engine.py         Protocol TranscriptionEngine + FasterWhisperEngine
    live.py           mode Direct : fenêtre glissante + accord LocalAgreement
    textproc.py       remplacements et commandes vocales (fonctions pures)
    model_download.py modèle téléchargé au premier lancement, avec progression
  audio/
    recorder.py       capture micro 16 kHz mono (sounddevice)
    loopback.py       audio de l'ordinateur : WASAPI loopback (COM via ctypes)
    sources.py        choix de la source, mixage micro + ordinateur
  runtime/
    gpu_detect.py     détection de la carte (WMI) : NVIDIA, AMD compatible ou processeur
    packages.py       accélérations épinglées (URL, version, SHA-256)
    install.py        téléchargement avec reprise et décompression des wheels
    store.py          emplacement et activation (sys.path, DLL) avant l'import de ctranslate2
    startup.py        choix au démarrage, test du GPU (--probe), explication du repli processeur
  download.py         téléchargements HTTP : progression, reprise, annulation, SHA-256
  desktop/
    com.py            COM minimal via ctypes (partagé avec loopback.py)
    shortcuts.py      raccourcis Bureau / menu Démarrer (.lnk avec l'AppUserModelID de l'app)
  options.py          TranscribeOptions construites depuis les réglages (fichier, Direct, dictée)
  dictation/
    controller.py     dictée universelle : machine à états raccourci → micro → texte
    hotkey.py         raccourci global (hook clavier WH_KEYBOARD_LL, réinstallé toutes les 15 s)
    inject.py         collage dans la fenêtre active (SendInput), presse-papiers restauré
    autostart.py      démarrage avec Windows (clé Run de HKCU)
    sounds.py         signaux sonores synthétisés
  export/             exporteurs enregistrés par extension (txt, srt, vtt, md, docx, json)
    subtitles.py      découpage des sous-titres (2 × 42 caractères)
  ui/
    workers.py        ModelWorker : thread unique propriétaire du modèle
    main_window.py    fenêtre : composition, affichage de la session et de l'historique, édition
    app_icon.py       icône de l'application (fenêtre, barre des tâches, .ico de l'exe et des raccourcis)
    history_panel.py  panneau latéral de l'historique
    tray.py           icône de la zone de notification
    settings_dialog.py  fenêtre de réglages complète, par sections
    vocabulary_dialog.py  mots à favoriser, remplacements, commandes vocales
    theme.py          tokens de couleurs (sombre / clair), QSS généré, polices Geist
    widgets/          bouton micro, onde, contrôle segmenté, carte transcript (mots
                      synchronisés, mode édition), lecteur audio, popover de réglages,
                      notifications, pastille de dictée
    resources/fonts/  Geist et Geist Mono (licence OFL)
scripts/              install_rocm.ps1, check_gpu.py, download_models.py,
                      snapshot_ui.py (captures de l'interface dans chaque état),
                      build_installer.ps1, make_build_assets.py (icône, version)
packaging/            PyInstaller : doyoucopy.spec, launcher.py
installer/            Inno Setup : doyoucopy.iss
tests/                tests unitaires + test GPU de bout en bout (-m gpu)
```

Principes :

- **L'interface ne dépend que du Protocol `TranscriptionEngine`.** Un autre backend (whisper.cpp Vulkan, transformers…) s'ajoute dans `core/` sans toucher l'UI.
- **Un seul thread (`ModelWorker`) possède le modèle.** Les demandes (chargement, transcription) passent par des signaux Qt en file d'attente : pas d'accès concurrent au GPU, et l'UI ne gèle jamais.
- **Le modèle est aussi libéré sur ce thread, à la fermeture.** Avec la version ROCm de CTranslate2, libérer un modèle GPU depuis un autre thread tue le processus (code 127). Après un modèle processeur, ce thread ne peut même plus se terminer : il est laissé en vie et l'application se termine par `os._exit`, une fois l'historique et les réglages enregistrés.
- **Les segments sont émis un par un** depuis le générateur de faster-whisper. C'est ce qui produit l'affichage progressif et permet d'annuler entre deux segments.
- **Ajouter un modèle** revient à ajouter une entrée `ModelSpec` dans `core/models.py`. **Ajouter un format d'export** revient à créer une classe avec `suffix`, `label` et `render()`, puis à appeler `register()`.

- **Tout texte affiché passe par `tr()`** (`i18n.py`), écrit en français dans le code ; `locales/en.py` en donne la version anglaise. Une constante de module se marque avec `N_()` et se traduit là où elle s'affiche. `tests/test_i18n.py` échoue si une traduction manque, ne sert plus, ou perd un `{paramètre}`. Le rapport de diagnostic et le journal restent en français et en anglais technique : ils s'adressent au développeur.
- **La logique reste hors des widgets.** `SessionController` (capture, transcription) et `HistoryController` (ce qui est enregistré, quand) se testent sans fenêtre ; `MainWindow` affiche et relaie.
- **Windows retire en silence un hook clavier trop lent.** Le raccourci global est donc réinstallé périodiquement (`KeyboardHook.reinstall`), sans trou : le nouveau hook est posé avant le retrait de l'ancien.

Le mode Direct et la dictée universelle passent eux aussi par `ModelWorker` : le GPU garde un seul utilisateur. La dictée a ses propres signaux (`dictation_finished`), pour que son texte n'apparaisse pas dans la fenêtre principale.

Prochaines évolutions : voir [ROADMAP.md](ROADMAP.md).

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest           # tests unitaires
.\.venv\Scripts\python.exe -m ruff check .      # analyse statique (règles dans pyproject.toml)
.\.venv\Scripts\python.exe -m pytest -m gpu    # transcription réelle sur le GPU (synthèse vocale Windows)
.\.venv\Scripts\python.exe -m pytest -m hardware  # capture réelle de l'audio de l'ordinateur (joue un son)
```
