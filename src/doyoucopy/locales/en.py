"""English interface: French text (as written in the code) -> English text.

Keys are copied exactly from the tr() / trn() / N_() calls; tests/test_i18n.py fails
when one is missing, unused, or when its {placeholders} differ from the French ones.
Grouped by the module that shows them.
"""

EN: dict[str, str] = {
    # ---- app.py --------------------------------------------------------------
    "Redémarrer DoYouCopy": "Restart DoYouCopy",
    "L'accélération graphique sera utilisée au prochain démarrage. Redémarrer DoYouCopy maintenant ?": (
        "Graphics acceleration will be used at the next start. Restart DoYouCopy now?"
    ),
    "DoYouCopy reste disponible": "DoYouCopy is still running",
    "Dictée : {hotkey}. Quittez depuis cette icône.": "Dictation: {hotkey}. Quit from this icon.",
    "Raccourci de dictée invalide": "Invalid dictation shortcut",
    "Dictée indisponible": "Dictation unavailable",
    "Le raccourci global n'a pas pu être installé.": "The global shortcut could not be set up.",
    # ---- audio ---------------------------------------------------------------
    "format audio non pris en charge (type {tag}, {bits} bits)": "unsupported audio format (type {tag}, {bits} bits)",
    "la capture de l'audio de l'ordinateur n'existe que sous Windows": "capturing the computer's audio only works on Windows",
    "le périphérique de sortie ne répond pas": "the output device does not respond",
    "Audio de l'ordinateur indisponible : {error}": "Computer audio unavailable: {error}",
    "Micro": "Microphone",
    "Ordinateur": "Computer",
    "Les deux": "Both",
    # ---- core ----------------------------------------------------------------
    "Aucun modèle chargé": "No model loaded",
    'Modèle {model} absent de {folder}. Autorisez le téléchargement ("allow_download") ou copiez le modèle.': (
        'Model {model} not found in {folder}. Allow downloads ("allow_download") or copy the model there.'
    ),
    "Impossible de joindre huggingface.co : {error}": "Cannot reach huggingface.co: {error}",
    "Modèle introuvable sur huggingface.co : {repo}": "Model not found on huggingface.co: {repo}",
    "small (léger)": "small (light)",
    "Pour les ordinateurs sans carte graphique : rapide sur processeur, moins précis.": (
        "For computers without a graphics card: fast on the processor, less accurate."
    ),
    "large-v3-turbo (rapide)": "large-v3-turbo (fast)",
    "Le meilleur compromis : presque aussi précis que large-v3, plusieurs fois plus rapide.": (
        "The best trade-off: almost as accurate as large-v3, several times faster."
    ),
    "large-v3 (précis)": "large-v3 (precise)",
    "La meilleure précision, et le seul modèle qui sait traduire vers l'anglais.": (
        "The best accuracy, and the only model that can translate into English."
    ),
    # ---- desktop, dictation --------------------------------------------------
    "Transcription vocale locale": "Local speech-to-text",
    "DoYouCopy est occupé": "DoYouCopy is busy",
    "Micro indisponible : {error}": "Microphone unavailable: {error}",
    "Trop court": "Too short",
    "Dictée annulée": "Dictation cancelled",
    "Rien entendu": "Nothing heard",
    "Texte inséré": "Text inserted",
    "Copié dans le presse-papiers": "Copied to the clipboard",
    "Raccourci invalide : « {hotkey} »": "Invalid shortcut: “{hotkey}”",
    "Touche non prise en charge dans « {hotkey} »": "Unsupported key in “{hotkey}”",
    "Ajoutez Ctrl, Alt, Maj ou Win : cette touche seule servirait à la frappe.": (
        "Add Ctrl, Alt, Shift or Win: on its own, this key is needed for typing."
    ),
    # ---- downloads, exports --------------------------------------------------
    "Téléchargement impossible ({host}) : {error}": "Download failed ({host}): {error}",
    "Téléchargement interrompu ({host}) : {error}": "Download interrupted ({host}): {error}",
    "Fichier corrompu ou modifié : {name} (empreinte SHA-256 incorrecte)": (
        "Corrupted or modified file: {name} (wrong SHA-256 checksum)"
    ),
    "Format non pris en charge : {suffix}": "Unsupported format: {suffix}",
    "(aucune extension)": "(no extension)",
    "Document Word": "Word document",
    "JSON (segments et mots)": "JSON (segments and words)",
    "Sous-titres SRT": "SRT subtitles",
    "Texte": "Text",
    "Sous-titres WebVTT": "WebVTT subtitles",
    # ---- graphics card and runtime -------------------------------------------
    "GPU · {compute_type}": "GPU · {compute_type}",
    "Processeur · {compute_type}": "Processor · {compute_type}",
    "Carte NVIDIA détectée : {name}": "NVIDIA card detected: {name}",
    "Carte AMD détectée : {name}": "AMD card detected: {name}",
    "{name} : carte trop ancienne pour l'accélération (CUDA 12)": "{name}: card too old for acceleration (CUDA 12)",
    "{name} : non prise en charge par l'accélération AMD (Radeon RX 6800 et plus récentes)": (
        "{name}: not supported by AMD acceleration (Radeon RX 6800 and newer)"
    ),
    "{name} : pas d'accélération disponible pour cette carte": "{name}: no acceleration available for this card",
    "Aucune carte graphique compatible détectée": "No compatible graphics card detected",
    "Espace disque insuffisant : {size} Go libres nécessaires sur {drive}.": (
        "Not enough disk space: {size} GB free needed on {drive}."
    ),
    "Installation impossible : {error}": "Installation failed: {error}",
    "Accélération NVIDIA (CUDA 12)": "NVIDIA acceleration (CUDA 12)",
    "Accélération AMD (ROCm 7.2)": "AMD acceleration (ROCm 7.2)",
    "Transcription plus lente sur cette machine": "Slower transcription on this computer",
    "La carte graphique n'a pas pu être initialisée. Mettez à jour le pilote {driver}, puis relancez DoYouCopy.": (
        "The graphics card could not be initialised. Update the {driver} driver, then restart DoYouCopy."
    ),
    "Son accélération n'est pas encore installée ({size} Go à télécharger).": (
        "Its acceleration is not installed yet ({size} GB to download)."
    ),
    "DoYouCopy utilise le processeur.": "DoYouCopy is using the processor.",
    # ---- session.py ------------------------------------------------------------
    "Impossible d'ouvrir le micro : {error}": "Cannot open the microphone: {error}",
    "Impossible de démarrer la capture : {error}": "Cannot start the capture: {error}",
    "Enregistrement…": "Recording…",
    "Enregistrement trop court.": "Recording too short.",
    "Fin du direct…": "Ending live transcription…",
    "Analyse de l'audio…": "Analysing the audio…",
    "En attente du modèle…": "Waiting for the model…",
    "Retranscription du passage…": "Transcribing the passage again…",
    "Passage retranscrit.": "Passage transcribed again.",
    "Aucune parole retrouvée dans ce passage.": "No speech found in this passage.",
    "Chargement du modèle…": "Loading the model…",
    "Transcription en cours ({language}, {duration})": "Transcribing ({language}, {duration})",
    "Transcription annulée.": "Transcription cancelled.",
    " · {speed}× temps réel": " · {speed}× real time",
    "{duration} transcrit en {seconds} s": "{duration} transcribed in {seconds} s",
    "passe {seconds} s": "pass {seconds} s",
    "Direct terminé · {count} phrase": "Live transcription ended · {count} sentence",
    "Direct terminé · {count} phrases": "Live transcription ended · {count} sentences",
    # ---- history ---------------------------------------------------------------
    "Enregistrement": "Recording",
    "Direct": "Live",
    "Fichier": "File",
    "Dictée": "Dictation",
    "janv.": "Jan",
    "févr.": "Feb",
    "mars": "Mar",
    "avr.": "Apr",
    "mai": "May",
    "juin": "Jun",
    "juil.": "Jul",
    "août": "Aug",
    "sept.": "Sep",
    "oct.": "Oct",
    "nov.": "Nov",
    "déc.": "Dec",
    "{day} {month} {year} · {time}": "{month} {day}, {year} · {time}",
    "Sans titre": "Untitled",
    "Historique": "History",
    "Favoris seulement": "Favourites only",
    "Rechercher dans les transcriptions": "Search the transcripts",
    "Aucun résultat.": "No results.",
    "Vos transcriptions apparaîtront ici, enregistrées automatiquement.": (
        "Your transcripts will appear here, saved automatically."
    ),
    "audio": "audio",
    "Ouvrir": "Open",
    "Renommer…": "Rename…",
    "Retirer des favoris": "Remove from favourites",
    "Ajouter aux favoris": "Add to favourites",
    "Supprimer…": "Delete…",
    "Renommer": "Rename",
    "Titre": "Title",
    "Supprimer": "Delete",
    "Supprimer cette transcription de l'historique, avec son audio ?": (
        "Delete this transcript from the history, with its audio?"
    ),
    # ---- main window -----------------------------------------------------------
    "Langue auto": "Auto language",
    "Français": "French",
    "Anglais": "English",
    "Allemand": "German",
    "Espagnol": "Spanish",
    "Italien": "Italian",
    "Portugais": "Portuguese",
    "Néerlandais": "Dutch",
    "Polonais": "Polish",
    "Russe": "Russian",
    "Arabe": "Arabic",
    "Chinois": "Chinese",
    "Japonais": "Japanese",
    "Léger": "Light",
    "Précis": "Precise",
    "Audio / vidéo ({patterns});;Tous (*)": "Audio / video ({patterns});;All files (*)",
    "Léger : small, pour le processeur.  Turbo : rapide et précis.  Précis : large-v3, plus lent.": (
        "Light: small, for the processor.  Turbo: fast and accurate.  Precise: large-v3, slower."
    ),
    "Réglages": "Settings",
    "Historique (Ctrl+H)": "History (Ctrl+H)",
    "Ce que DoYouCopy écoute : votre micro, le son de l'ordinateur (réunion, vidéo), ou les deux.": (
        "What DoYouCopy listens to: your microphone, the computer's sound (meeting, video), or both."
    ),
    "Importer un fichier": "Import a file",
    "ou glissez-le dans la fenêtre": "or drop it into the window",
    "Copier": "Copy",
    "Texte brut": "Plain text",
    "Texte horodaté": "Timestamped text",
    "Exporter": "Export",
    "Effacer": "Clear",
    "Modifier": "Edit",
    "Corriger le texte, les horodatages sont conservés (Ctrl+E)": "Correct the text, timestamps are kept (Ctrl+E)",
    "Annuler": "Cancel",
    "DIRECT": "LIVE",
    "Calcul sur le processeur, choisi dans ces réglages.": "Running on the processor, as chosen in these settings.",
    "Accélération graphique active.": "Graphics acceleration is on.",
    "Rechargement du modèle · {device}": "Reloading the model · {device}",
    "Réglages par défaut rétablis": "Default settings restored",
    "Dictée en cours…": "Dictation in progress…",
    "Prévenez les participants avant d'enregistrer une réunion.": "Tell the participants before recording a meeting.",
    "Parlez, le texte s'affiche au fil de l'eau.": "Speak, the text appears as you go.",
    "Sur le processeur, le texte arrive avec plusieurs secondes de retard.": (
        "On the processor, the text arrives several seconds late."
    ),
    "Modèle précis : latence plus élevée en direct.": "Precise model: higher latency in live mode.",
    "Importer un fichier audio": "Import an audio file",
    "Texte copié": "Text copied",
    "Exporter la transcription": "Export the transcript",
    "Échec de l'export : {error}": "Export failed: {error}",
    "Exporté vers {name}": "Exported to {name}",
    "{done} / {total} Go": "{done} / {total} GB",
    "Premier lancement : téléchargement de {model}… {size}": "First start: downloading {model}… {size}",
    "Téléchargement du modèle · {percent} %": "Downloading the model · {percent} %",
    "Modèle {model} prêt.": "Model {model} ready.",
    "Terminez d'abord la transcription en cours": "Finish the current transcription first",
    "Historique effacé": "History cleared",
    "Modification : une ligne par segment. Recliquez sur Modifier pour valider.": (
        "Editing: one line per segment. Click Edit again to confirm."
    ),
    "Corrections enregistrées.": "Corrections saved.",
    "Lire à partir d'ici": "Play from here",
    "Retranscrire avec le modèle {model}": "Transcribe again with the {model} model",
    "L'audio de cette transcription n'est pas disponible.": "The audio of this transcript is not available.",
    "Installer l'accélération": "Install acceleration",
    "Réessayer": "Try again",
    # ---- graphics acceleration window ------------------------------------------
    "{size} Go": "{size} GB",
    "Téléchargement annulé. DoYouCopy utilisera le processeur.": "Download cancelled. DoYouCopy will use the processor.",
    "DoYouCopy utilisera le processeur.": "DoYouCopy will use the processor.",
    "Accélération graphique activée.": "Graphics acceleration enabled.",
    (
        "La carte graphique n'a pas pu être initialisée.\n"
        "Mettez à jour le pilote {driver}, puis relancez cette installation depuis DoYouCopy.\n"
        "En attendant, DoYouCopy utilisera le processeur."
    ): (
        "The graphics card could not be initialised.\n"
        "Update the {driver} driver, then run this installation again from DoYouCopy.\n"
        "Meanwhile, DoYouCopy will use the processor."
    ),
    "DoYouCopy · Accélération graphique": "DoYouCopy · Graphics acceleration",
    "Télécharger": "Download",
    "Utiliser le processeur": "Use the processor",
    (
        "DoYouCopy fonctionnera sur le processeur : la transcription reste possible, "
        "mais plus lente (le modèle Turbo est recommandé)."
    ): "DoYouCopy will run on the processor: transcription still works, but more slowly (the Turbo model is recommended).",
    "Terminer": "Finish",
    "Accélération graphique déjà installée": "Graphics acceleration already installed",
    (
        "DoYouCopy télécharge les composants qui lui permettent de transcrire avec cette carte ({size}), "
        "depuis leurs sources officielles."
    ): "DoYouCopy downloads the components it needs to transcribe with this card ({size}), from their official sources.",
    "Connexion…": "Connecting…",
    "Téléchargement · {done} / {total}": "Downloading · {done} / {total}",
    "Installation · {percent} %": "Installing · {percent} %",
    "Vérification de la carte graphique…": "Checking the graphics card…",
    "Accélération graphique activée": "Graphics acceleration enabled",
    "Annulation…": "Cancelling…",
    # ---- settings window --------------------------------------------------------
    "Détection automatique": "Automatic detection",
    "Automatique": "Automatic",
    "float16 : précision complète (recommandé sur GPU)": "float16: full precision (recommended on GPU)",
    "bfloat16 : précision complète": "bfloat16: full precision",
    "int8_float16 : moins de mémoire vidéo": "int8_float16: less video memory",
    "int8 : le plus léger (recommandé sur processeur)": "int8: the lightest (recommended on processor)",
    "float32 : le plus lent, référence": "float32: the slowest, reference",
    "Général": "General",
    "Transcription": "Transcription",
    "Silences": "Silences",
    "Mode Direct": "Live mode",
    "Exports": "Exports",
    "Modèles": "Models",
    "Matériel": "Hardware",
    "Fermer": "Close",
    "Apparence": "Appearance",
    "Système": "System",
    "Sombre": "Dark",
    "Clair": "Light",
    "Thème": "Theme",
    "Taille du texte": "Text size",
    "Afficher l'horodatage de chaque segment": "Show the timestamp of each segment",
    "Micro par défaut de Windows": "Windows default microphone",
    "Entrée": "Input",
    "Démarrage": "Startup",
    "Rester dans la zone de notification à la fermeture": "Stay in the notification area when closed",
    "Démarrer avec Windows (dans la zone de notification)": "Start with Windows (in the notification area)",
    "Sur le Bureau": "On the desktop",
    "Dans le menu Démarrer": "In the Start menu",
    "Raccourcis": "Shortcuts",
    "Rétablir les réglages par défaut…": "Restore default settings…",
    "Langue de l'interface": "Interface language",
    "La nouvelle langue s'appliquera au prochain démarrage de DoYouCopy.": (
        "The new language will apply the next time DoYouCopy starts."
    ),
    "Redémarrer maintenant": "Restart now",
    "Langue": "Language",
    "Langue parlée": "Spoken language",
    "Plusieurs langues dans le même audio": "Several languages in the same audio",
    "La langue est redétectée à chaque segment (réunions bilingues, citations).": (
        "The language is detected again for each segment (bilingual meetings, quotes)."
    ),
    "Transcrire dans la langue parlée": "Transcribe in the spoken language",
    "Traduire en anglais": "Translate into English",
    "Résultat": "Output",
    "Le modèle Turbo n'a pas été entraîné pour traduire : choisissez le modèle Précis.": (
        "The Turbo model was not trained to translate: choose the Precise model."
    ),
    "Contexte et vocabulaire": "Context and vocabulary",
    "Ex. : Réunion de l'équipe produit sur DoYouCopy, avec Claire et Karim.": (
        "E.g.: DoYouCopy product team meeting, with Claire and Karim."
    ),
    "Contexte": "Context",
    "Le sujet, des noms, un style d'écriture : le modèle s'en inspire.": (
        "The topic, names, a writing style: the model takes them as a hint."
    ),
    "Mots à favoriser et remplacements…": "Preferred words and replacements…",
    "Qualité et vitesse": "Quality and speed",
    "Recherche": "Beam search",
    "Selon le modèle": "Model default",
    "Rapide (1 hypothèse)": "Fast (1 hypothesis)",
    "Équilibrée (3)": "Balanced (3)",
    "Précise (5)": "Accurate (5)",
    "Maximale (8)": "Maximum (8)",
    "Texte précédent": "Previous text",
    "Utilisé comme contexte": "Used as context",
    "Ignoré (évite les boucles)": "Ignored (avoids loops)",
    "Fichiers": "Files",
    "Segment par segment": "Segment by segment",
    "Par lots de 8 (GPU)": "Batches of 8 (GPU)",
    "Par lots de 16 (GPU)": "Batches of 16 (GPU)",
    (
        "Par lots : jusqu'à 3 à 4 fois plus rapide sur une carte graphique, le texte arrive par blocs. "
        "Nécessite le filtre des silences."
    ): "Batches: up to 3 to 4 times faster on a graphics card, the text arrives in blocks. Requires the silence filter.",
    "Filtre des silences (VAD)": "Silence filter (VAD)",
    "Ignorer les silences (fichiers et enregistrements)": "Skip silences (files and recordings)",
    "Sensible": "Sensitive",
    "Strict": "Strict",
    "Détection de la voix": "Voice detection",
    "Pause minimale": "Minimum pause",
    "Seuil bas : capte les voix faibles mais aussi du bruit. Seuil haut : ignore les murmures.": (
        "Low threshold: picks up faint voices but also noise. High threshold: ignores whispers."
    ),
    "Hallucinations": "Hallucinations",
    "Supprimer le texte inventé pendant les longs silences": "Remove text invented during long silences",
    "Whisper « invente » parfois des phrases (« Merci d'avoir regardé ») sur du silence.": (
        "Whisper sometimes “invents” sentences (“Thanks for watching”) over silence."
    ),
    "Seuil « pas de parole »": "“No speech” threshold",
    "Pénalité de répétition": "Repetition penalty",
    "Au-dessus de 1, le modèle répète moins les mêmes mots en boucle.": (
        "Above 1, the model repeats the same words in a loop less often."
    ),
    "Raccourci": "Shortcut",
    "Appuyez sur un raccourci": "Press a shortcut",
    "Maintenir": "Hold",
    "Basculer": "Toggle",
    "Mode": "Mode",
    "Dictée active": "Dictation on",
    "Texte dicté": "Dictated text",
    "Sortie": "Output",
    "Coller dans l'application active": "Paste into the active app",
    "Copier seulement": "Copy only",
    "Ajouter un espace après le texte": "Add a space after the text",
    "Commandes vocales de ponctuation (« virgule », « à la ligne »…)": "Spoken punctuation commands (“comma”, “new line”…)",
    "Signal sonore au début et à la fin": "Sound at the start and the end",
    "Réactivité": "Responsiveness",
    "Intervalle entre passes": "Interval between passes",
    "Silence de fin de phrase": "End-of-sentence silence",
    (
        "Intervalle court : texte plus réactif, mais davantage de calcul (à éviter sur processeur). "
        "Silence de fin court : les phrases sont validées plus tôt."
    ): (
        "Short interval: more responsive text, but more computing (avoid on the processor). "
        "Short end silence: sentences are confirmed sooner."
    ),
    "Export rapide (Ctrl+S)": "Quick export (Ctrl+S)",
    "Format": "Format",
    "Sous-titres (SRT, WebVTT)": "Subtitles (SRT, WebVTT)",
    "Caractères par ligne": "Characters per line",
    "Lignes par sous-titre": "Lines per subtitle",
    "Norme habituelle : 42 caractères, 2 lignes. Réseaux sociaux verticaux : 20 à 30, 1 ligne.": (
        "Usual standard: 42 characters, 2 lines. Vertical social media: 20 to 30, 1 line."
    ),
    "Enregistrement automatique": "Automatic saving",
    "Garder chaque transcription dans l'historique": "Keep every transcript in the history",
    "Garder aussi le texte des dictées (raccourci global)": "Also keep the text of dictations (global shortcut)",
    "Retrouvez vos dictées dans l'historique, marquées « Dictée ».": (
        "Find your dictations in the history, marked “Dictation”."
    ),
    "Audio": "Audio",
    "Conserver l'audio des enregistrements (micro et Direct)": "Keep the audio of recordings (microphone and Live)",
    "Pour réécouter un passage ou le retranscrire avec un autre modèle. FLAC, environ 60 Mo par heure.": (
        "To replay a passage or transcribe it again with another model. FLAC, about 60 MB per hour."
    ),
    " jours": " days",
    "Jamais": "Never",
    "Supprimer l'audio après": "Delete the audio after",
    "Le texte est toujours conservé. Les fichiers importés ne sont pas copiés.": (
        "The text is always kept. Imported files are not copied."
    ),
    "Données": "Data",
    "Ouvrir le dossier": "Open the folder",
    "Tout effacer…": "Clear everything…",
    "Tout reste sur ce PC, dans votre profil Windows.": "Everything stays on this PC, in your Windows profile.",
    "Effacer l'historique": "Clear the history",
    "Effacer toutes les transcriptions et leur audio ? C'est définitif.": (
        "Clear all transcripts and their audio? This cannot be undone."
    ),
    "Modèle utilisé": "Model in use",
    "{model} · {size} Go": "{model} · {size} GB",
    "Modèle": "Model",
    "Modèles téléchargés": "Downloaded models",
    "Emplacement": "Location",
    "Changer…": "Change…",
    "Dossier": "Folder",
    "Télécharger automatiquement un modèle manquant": "Download a missing model automatically",
    "Désactivé : DoYouCopy n'accède jamais au réseau (mode hors ligne strict).": (
        "Off: DoYouCopy never goes online (strict offline mode)."
    ),
    "Non téléchargé": "Not downloaded",
    "{size} Go sur le disque": "{size} GB on disk",
    "Le modèle utilisé ne peut pas être supprimé.": "The model in use cannot be deleted.",
    "Supprimer le modèle": "Delete the model",
    "Supprimer {model} ? Il sera retéléchargé si vous le choisissez à nouveau.": (
        "Delete {model}? It will be downloaded again if you choose it later."
    ),
    "Dossier des modèles": "Models folder",
    "Calcul": "Computing",
    "Carte graphique": "Graphics card",
    "Processeur": "Processor",
    "Calculer sur": "Run on",
    "Précision": "Precision",
    "Threads processeur": "Processor threads",
    (
        "Appliqué tout de suite : le modèle est rechargé (quelques secondes), "
        "après la transcription en cours s'il y en a une."
    ): "Applied at once: the model is reloaded (a few seconds), after the current transcription if there is one.",
    "État": "Status",
    "Utilisé": "In use",
    "Carte": "Card",
    "Installer l'accélération graphique…": "Install graphics acceleration…",
    "Diagnostic": "Diagnostics",
    "Copier les informations de diagnostic": "Copy diagnostic information",
    "Ouvrir le dossier des journaux": "Open the logs folder",
    (
        "Machine, carte graphique, versions, réglages et dernières erreurs, à joindre à un signalement. "
        "Aucune transcription ni aucun mot du vocabulaire n'y figure : relisez-le avant de l'envoyer."
    ): (
        "Computer, graphics card, versions, settings and latest errors, to attach to a bug report. "
        "No transcript and no vocabulary word is included: read it before sending it."
    ),
    "Copié dans le presse-papiers ✓": "Copied to the clipboard ✓",
    "Impossible de modifier le démarrage automatique.": "Cannot change the automatic start.",
    " Vérifiez qu'il n'est pas désactivé dans Paramètres Windows > Applications > Démarrage.": (
        " Check that it is not turned off in Windows Settings > Apps > Startup."
    ),
    "Démarrage avec Windows": "Start with Windows",
    "Impossible de créer le raccourci dans {place}.": "Cannot create the shortcut in {place}.",
    "Impossible de supprimer le raccourci dans {place}.": "Cannot delete the shortcut in {place}.",
    "Rétablir les réglages": "Restore settings",
    "Rétablir tous les réglages par défaut ? Le vocabulaire et le dossier des modèles sont conservés.": (
        "Restore all default settings? The vocabulary and the models folder are kept."
    ),
    # ---- notification area -------------------------------------------------------
    "Ouvrir DoYouCopy": "Open DoYouCopy",
    "Quitter": "Quit",
    "DoYouCopy · dictée : {hotkey}": "DoYouCopy · dictation: {hotkey}",
    # ---- vocabulary window ---------------------------------------------------------
    "Vocabulaire": "Vocabulary",
    "Mots à favoriser": "Preferred words",
    "Noms propres, sigles, jargon : un par ligne.": "Names, acronyms, jargon: one per line.",
    "Remplacements": "Replacements",
    "Mots entiers, sans tenir compte de la casse. /motif/ pour une expression régulière.": (
        "Whole words, case-insensitive. /pattern/ for a regular expression."
    ),
    "Entendu": "Heard",
    "Écrire": "Write",
    "Ajouter": "Add",
    "Commandes vocales de ponctuation dans la dictée": "Spoken punctuation commands in dictation",
    (
        "« virgule », « point final », « point d'interrogation », « à la ligne », "
        "« nouveau paragraphe », « ouvrez les guillemets »…  (en anglais : comma, full stop, new line…)"
    ): (
        "“comma”, “full stop”, “question mark”, “new line”, "
        "“new paragraph”, “open quote”…  (in French: virgule, point final, à la ligne…)"
    ),
    # ---- widgets -------------------------------------------------------------------
    "Échap pour annuler": "Esc to cancel",
    "Écoute…": "Listening…",
    "Transcription…": "Transcribing…",
    "Masquer": "Hide",
    "Lecture / pause (Ctrl+Espace)": "Play / pause (Ctrl+Space)",
    "Reculer de 5 s (Ctrl+←)": "Back 5 s (Ctrl+←)",
    "Vitesse de lecture": "Playback speed",
    "Audio illisible": "Unreadable audio",
    "Arrêter": "Stop",
    "Démarrer la capture": "Start capturing",
    "Ignorer les silences (VAD)": "Skip silences (VAD)",
    "Pour les fichiers et les enregistrements. Le mode Direct l'utilise toujours.": (
        "For files and recordings. Live mode always uses it."
    ),
    "Afficher l'horodatage": "Show timestamps",
    "Vocabulaire…": "Vocabulary…",
    "Mots à favoriser, remplacements, commandes vocales": "Preferred words, replacements, voice commands",
    "Micro par défaut": "Default microphone",
    "Tous les réglages…": "All settings…",
    "Prêt à transcrire": "Ready to transcribe",
    "Cliquez sur le micro ou appuyez sur Ctrl+R.\nVous pouvez aussi déposer un fichier audio ici.": (
        "Click the microphone or press Ctrl+R.\nYou can also drop an audio file here."
    ),
    "À l'écoute": "Listening",
    "Cliquez à nouveau sur le bouton pour arrêter et transcrire.": "Click the button again to stop and transcribe.",
    "Le texte apparaîtra dès les premiers mots.": "The text will appear from the first words.",
    "Chargement de {model}…": "Loading {model}…",
    "Mot incertain : à vérifier": "Uncertain word: check it",
    # ---- model thread ----------------------------------------------------------------
    "Impossible d'appliquer les réglages : {error}": "Cannot apply the settings: {error}",
    "Impossible de charger {model} : {error}": "Cannot load {model}: {error}",
    "Échec de la transcription : {error}": "Transcription failed: {error}",
    "Échec de la transcription en direct : {error}": "Live transcription failed: {error}",
    "Échec de la retranscription : {error}": "Transcribing again failed: {error}",
    "Échec de la dictée : {error}": "Dictation failed: {error}",
}
