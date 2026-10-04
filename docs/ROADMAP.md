# Roadmap MyWhisper : les 10 prochaines fonctionnalités

*Rédigée le 4 octobre 2026, à partir de l'état du dépôt après le mode Direct (commit `46f2a42`) et la refonte de l'interface en cours.*

> **Avancement (4 octobre 2026)** : la phase 1 est livrée (n°1, n°2, n°3). Reporté : les profils de vocabulaire du n°2 (un seul vocabulaire pour l'instant) et le découpage de `main_window.py` en contrôleur, à faire avant le n°4.

## Où en est l'application

MyWhisper fait déjà très bien **une** chose : transformer de l'audio en texte, localement, vite, sur un GPU AMD. Enregistrement micro, import de fichiers, mode Direct, export TXT/SRT, deux modèles, thèmes.

Ce qui manque, c'est tout ce qui se passe **avant** et **après** la transcription :

| Moment | Besoin utilisateur | Aujourd'hui |
|---|---|---|
| Avant | « Je veux dicter dans **n'importe quelle** application, pas dans MyWhisper. » | Il faut ouvrir la fenêtre, transcrire, copier, revenir, coller. |
| Pendant | « Il se trompe sur les noms propres et le jargon de mon métier. » | Aucun vocabulaire personnalisé. |
| Pendant | « Je veux transcrire ma réunion Teams/Zoom, pas seulement mon micro. » | Micro uniquement. |
| Après | « Où est la transcription d'hier ? » | Rien n'est conservé : fermer la fenêtre, c'est tout perdre. |
| Après | « Je veux corriger les erreurs en réécoutant le passage. » | Le texte n'est pas éditable, l'audio n'est pas rejouable. |
| Après | « Qui a dit quoi ? » / « Fais-moi un résumé. » | Pas de locuteurs, pas de post-traitement. |

La roadmap suit ce constat : d'abord faire de MyWhisper un **outil de dictée de tous les jours** (usage quotidien, rétention), ensuite un **outil de travail sur les transcriptions** (historique, édition), enfin un **assistant de réunion local** (audio système, locuteurs, résumé), sans jamais renoncer au principe fondateur : **100 % local, aucun octet ne quitte la machine**.

## Vue d'ensemble

| # | Fonctionnalité | Phase | Impact | Effort | Dépend de |
|---|---|---|---|---|---|
| 1 | ✅ Dictée universelle (raccourci global + collage dans l'app active) | 1 · Dicter partout | ★★★★★ | M | — |
| 2 | ✅ Vocabulaire personnalisé et commandes vocales | 1 · Dicter partout | ★★★★ | S | — |
| 3 | ✅ Exports enrichis (VTT, JSON, DOCX, Markdown, sous-titres pro) | 1 · Dicter partout | ★★★ | S | — |
| 4 | Historique local avec recherche plein texte | 2 · Garder et corriger | ★★★★★ | M | — |
| 5 | Éditeur synchronisé avec l'audio | 2 · Garder et corriger | ★★★★ | L | 4 |
| 6 | File d'attente, traitement par lot et ligne de commande | 2 · Garder et corriger | ★★★ | M | 4 (souhaitable) |
| 7 | Capture de l'audio système (réunions, vidéos) | 3 · Réunions | ★★★★ | M | — |
| 8 | Identification des locuteurs (diarisation) | 3 · Réunions | ★★★★ | L | 7 (souhaitable) |
| 9 | Post-traitement par IA locale (nettoyage, résumé, actions) | 4 · Intelligence | ★★★★ | M | 4 |
| 10 | Traduction et sous-titres bilingues | 4 · Intelligence | ★★★ | S → M | 9 (pour les langues autres que l'anglais) |

Effort : **S** ≈ quelques jours, **M** ≈ 1 à 2 semaines, **L** ≈ 3 semaines ou plus (un développeur).

```
Phase 1 — Dicter partout       [1 Dictée universelle ][2 Vocab.][3 Exports]
Phase 2 — Garder et corriger                          [4 Historique  ][5 Éditeur synchronisé   ][6 Lot/CLI ]
Phase 3 — Réunions                                                   [7 Audio système ][8 Locuteurs      ]
Phase 4 — Intelligence                                                                 [9 IA locale ][10 Trad.]
```

---

## Phase 1 — Dicter partout

### 1. Dictée universelle

**Le problème.** Le cas d'usage n°1 d'un outil de transcription sur poste de travail, c'est de dicter un e-mail, un message Teams, un prompt, un document. Aujourd'hui, MyWhisper impose cinq manipulations là où il en faudrait une. C'est la fonctionnalité qui fait passer l'application d'« outil occasionnel » à « outil ouvert toute la journée ». Le README la mentionne déjà comme piste d'évolution.

**Ce qu'on livre.**
- Un **raccourci global** configurable (ex. `Ctrl+Alt+Espace`), actif même quand la fenêtre est réduite, en deux modes :
  - **appui maintenu** (push-to-talk) : on parle tant que la touche est enfoncée ;
  - **bascule** : un appui pour démarrer, un appui pour arrêter.
- À l'arrêt, le texte est **inséré dans l'application qui a le focus**. Option de repli : copie seule dans le presse-papiers.
- Une **icône dans la zone de notification** : l'application vit en arrière-plan, le modèle reste chargé sur le GPU, la fermeture de la fenêtre la réduit au lieu de la quitter.
- Une **pastille flottante** discrète (bas de l'écran) pendant la dictée : onde audio, état (écoute / transcription), touche Échap pour annuler.
- Option « démarrer avec Windows ».
- Un retour sonore court au début et à la fin de la capture (désactivable).

**Ancrage technique.**
- Raccourci : `RegisterHotKey` (Win32, via `ctypes`) pour le mode bascule ; hook clavier bas niveau (`WH_KEYBOARD_LL`) pour l'appui maintenu, qui a besoin de l'événement « touche relâchée ».
- Insertion : sauvegarder le presse-papiers → y placer le texte → `SendInput` Ctrl+V → restaurer le presse-papiers. C'est la méthode la plus fiable (Unicode, accents, emojis), plus robuste que la frappe caractère par caractère.
- `QSystemTrayIcon` ; la pastille est un `QWidget` sans bordure, toujours au premier plan, qui ne prend pas le focus (`WindowDoesNotAcceptFocus`), sinon le collage partirait dans la mauvaise fenêtre.
- Le pipeline existe déjà : `AudioRecorder` → `ModelWorker.transcribe()` → segments. Il faut sortir l'enchaînement « enregistrer puis transcrire » de `main_window.py` vers un contrôleur réutilisable par la fenêtre **et** par la dictée globale.

**Risques.** Windows bloque `SendInput` d'un processus normal vers une fenêtre lancée en administrateur : détecter le cas et basculer sur le presse-papiers avec une notification. Conflits de raccourcis : vérifier le retour de `RegisterHotKey` et le signaler.

**Critère de succès.** Du relâchement de la touche au texte collé : moins d'1 s pour 10 s de parole avec turbo sur la RX 7800 XT.

### 2. Vocabulaire personnalisé et commandes vocales

**Le problème.** Whisper écorche les noms propres, les sigles, les noms de produits et le jargon métier. C'est la première source de frustration des utilisateurs réguliers, et la première raison pour laquelle ils corrigent à la main.

**Ce qu'on livre.**
- Une liste de **mots à favoriser** (« ROCm », « CTranslate2 », « Mme Dupuis », noms de clients…).
- Une table de **remplacements** appliquée après la transcription (« ia » → « IA », « mail » → « e-mail », expressions régulières en option avancée).
- Des **commandes vocales de mise en forme** pour la dictée, en français et en anglais : « à la ligne », « nouveau paragraphe », « point », « virgule », « point d'interrogation », « ouvrez les guillemets »… Désactivables, car elles gênent la transcription de fichiers.
- Plusieurs **profils** (ex. « Médical », « Développement », « Personnel »), sélectionnables dans les réglages.

**Ancrage technique.** faster-whisper accepte déjà `hotwords` et `initial_prompt` : on ajoute `hotwords` à `TranscribeOptions` et on le transmet dans `FasterWhisperEngine.transcribe()`. Les remplacements et les commandes vocales forment une étape de post-traitement pure (fonction `str → str`), facile à tester, appliquée segment par segment, y compris sur le texte validé du mode Direct. Stockage dans `settings.json` ou dans un `vocabulary.json` à part.

**Critère de succès.** Sur un jeu de 20 phrases contenant des termes métier, le taux d'erreur sur ces termes est divisé par deux.

### 3. Exports enrichis

**Le problème.** TXT et SRT couvrent le minimum. Les monteurs vidéo veulent du VTT et des sous-titres bien découpés, les rédacteurs du Word, les développeurs du JSON.

**Ce qu'on livre.**
- **WebVTT** (web, YouTube), **JSON** (segments et mots avec horodatage, pour l'intégration dans d'autres outils), **Markdown**, **DOCX**.
- Des **sous-titres de qualité professionnelle** : découpage par mots (horodatage au mot), 42 caractères par ligne au maximum, 2 lignes, durée d'affichage minimale et maximale, coupure de préférence sur la ponctuation.
- « Copier comme… » : texte brut, texte horodaté, Markdown.

**Ancrage technique.** Le registre `export/base.py` est fait pour ça : une classe par format et un appel à `register()`. Le découpage des sous-titres a besoin des mots : il faut activer `word_timestamps` à la demande (coût faible). DOCX : dépendance `python-docx`, à garder optionnelle.

**Critère de succès.** Un SRT produit par MyWhisper passe sans retouche dans DaVinci Resolve et sur YouTube.

---

## Phase 2 — Garder et corriger

### 4. Historique local avec recherche plein texte

**Le problème.** Aujourd'hui, une transcription non exportée disparaît à la fermeture de la fenêtre ou au prochain enregistrement. Perdre 40 minutes de transcription d'un entretien, c'est le genre d'incident qui fait abandonner un outil.

**Ce qu'on livre.**
- Chaque transcription est **enregistrée automatiquement** : date, durée, source (micro, Direct, nom du fichier), modèle, langue, texte, segments et mots.
- Un **panneau latéral** listant les sessions, avec une **recherche plein texte** instantanée, le renommage, les favoris et la suppression.
- Option « **conserver l'audio** » des enregistrements micro (FLAC ou Opus), indispensable pour l'éditeur (n°5) et pour retranscrire plus tard avec large-v3.
- Une politique de rétention (ex. supprimer l'audio après 30 jours, garder le texte) et un bouton « tout effacer ».
- Par défaut, la dictée universelle (n°1) n'est **pas** historisée, ou seulement le texte : à régler dans les options.

**Ancrage technique.** SQLite (bibliothèque standard) avec **FTS5** pour la recherche, dans `%LOCALAPPDATA%\MyWhisper\history.db`. Un module `storage/` indépendant de Qt, testable comme `config.py`. La sauvegarde se fait à la fin de `transcription_finished` / `live_finished`, ainsi qu'à intervalles réguliers pendant les longues sessions, pour qu'un plantage ne fasse pas tout perdre.

**Prérequis conseillé.** `main_window.py` atteint 600 lignes : avant d'y ajouter un panneau d'historique, extraire la logique de session (capture, transcription, résultat courant) dans un contrôleur. Ce travail sert aussi aux n°1 et n°5.

**Critère de succès.** Retrouver une phrase prononcée il y a trois semaines en moins de 5 secondes.

### 5. Éditeur synchronisé avec l'audio

**Le problème.** Aucune transcription n'est parfaite. Pour corriger, l'utilisateur doit réécouter le passage douteux, et aujourd'hui ni l'audio ni le texte ne s'y prêtent.

**Ce qu'on livre.**
- Un **lecteur audio** intégré (lecture/pause, vitesse de 0,5× à 2×, retour de 5 s) associé à la transcription.
- **Surlignage du mot en cours** pendant la lecture ; **un clic sur un mot** amène la lecture à cet instant.
- **Édition directe du texte**, qui conserve les horodatages des segments, pour que l'export SRT reste juste après correction.
- Les mots à **faible confiance** sont soulignés (faster-whisper fournit une probabilité par mot) : l'œil va droit aux erreurs probables.
- « **Retranscrire cette sélection** avec large-v3 » : on garde turbo pour la vitesse, on passe au modèle précis seulement là où c'est nécessaire.

**Ancrage technique.** `QMediaPlayer` + `QAudioOutput` ; les `Word` ont déjà `start` et `end`, il faut y ajouter `probability`. Le texte est édité dans `transcript_view.py` ; le modèle de données devient une liste de segments modifiables, persistée par l'historique (n°4).

**Critère de succès.** Corriger une transcription de 10 minutes prend moins de 5 minutes.

### 6. File d'attente, traitement par lot et ligne de commande

**Le problème.** Les podcasteurs, journalistes, étudiants et chercheurs ont des **dizaines** de fichiers à transcrire. Glisser-déposer un fichier, attendre, exporter, recommencer : ça ne passe pas à l'échelle.

**Ce qu'on livre.**
- Le glisser-déposer accepte **plusieurs fichiers ou un dossier** et les place dans une **file d'attente** visible (progression par fichier, temps restant estimé, réordonnancement, annulation).
- **Export automatique** à côté de chaque fichier source, dans les formats choisis.
- Un **dossier surveillé** (option) : tout fichier audio déposé dedans est transcrit automatiquement.
- Une **ligne de commande** sans interface : `mywhisper transcribe *.mp3 --model turbo --lang fr --format srt,txt`. Elle sert aux automatisations et aux scripts.

**Ancrage technique.** `ModelWorker` traite déjà les requêtes une par une dans l'ordre : la file existe en substance, il lui manque un modèle de données et une vue. La CLI réutilise `FasterWhisperEngine` et les exporteurs directement, sans Qt. Le dossier surveillé passe par `QFileSystemWatcher`, avec une attente de stabilisation de la taille du fichier, pour ne pas lire une copie en cours.

**Critère de succès.** 50 fichiers déposés d'un coup sont tous traités sans intervention, GPU occupé en continu.

---

## Phase 3 — Réunions

### 7. Capture de l'audio système

**Le problème.** Transcrire une réunion Teams/Zoom/Meet, un webinaire ou une vidéo YouTube est l'un des usages les plus demandés. Avec le micro seul, on ne capte qu'un côté de la conversation.

**Ce qu'on livre.**
- Une nouvelle source : **« Audio de l'ordinateur »** (ce qui sort des haut-parleurs), seule ou **mixée avec le micro**.
- Compatible avec l'enregistrement **et** le mode Direct (sous-titres en direct d'une vidéo ou d'un appel).
- Les deux sources sont enregistrées sur **deux pistes séparées** : on sait ainsi sans calcul ce qui vient de « Moi » (micro) et ce qui vient des « Autres » (système). C'est une première diarisation, gratuite et fiable, pour les appels.
- Un rappel visible sur le consentement des participants avant d'enregistrer une réunion.

**Ancrage technique.** Capture en **WASAPI loopback**. PortAudio/sounddevice ne l'expose pas de façon fiable sous Windows : prévoir `PyAudioWPatch` ou `soundcard`, derrière une interface commune avec `AudioRecorder` (`drain()`, niveau, rééchantillonnage vers 16 kHz). Le mixage et le rééchantillonnage existent déjà (`resample()`).

**Critère de succès.** Un appel Teams d'une heure transcrit avec les deux interlocuteurs, sans écho ni doublon.

### 8. Identification des locuteurs

**Le problème.** Une transcription de réunion ou d'entretien sans « qui parle » est difficile à lire et à citer.

**Ce qu'on livre.**
- Option « **Identifier les locuteurs** » à la transcription d'un fichier ou d'un enregistrement : chaque paragraphe est attribué à « Locuteur 1 », « Locuteur 2 »…
- **Renommage** des locuteurs (« Locuteur 1 » → « Claire »), répercuté partout.
- Nombre de locuteurs automatique ou imposé.
- Les locuteurs apparaissent dans tous les exports (`[Claire] …` en SRT/VTT, sections en DOCX/Markdown, champ `speaker` en JSON).

**Ancrage technique.** Éviter pyannote/PyTorch (lourd, et PyTorch ROCm sous Windows reste fragile). Préférer **sherpa-onnx** : segmentation pyannote et embeddings 3D-Speaker exportés en ONNX, sur CPU, quelques centaines de Mo. On attribue ensuite chaque **mot** au tour de parole qui le contient, puis on regroupe. Exécution après la transcription, dans le worker, pour ne pas toucher au chemin critique de la dictée.

**Critère de succès.** Sur un entretien à deux voix de 30 minutes, plus de 90 % des paragraphes sont attribués au bon locuteur.

---

## Phase 4 — Intelligence

### 9. Post-traitement par IA locale

**Le problème.** Une transcription brute n'est pas un livrable : hésitations (« euh », « du coup »), répétitions, phrases orales. Ce que veut l'utilisateur, c'est un texte propre, un compte rendu, une liste d'actions, et ce **sans envoyer ses données dans le cloud**, puisque c'est la raison pour laquelle il a choisi MyWhisper.

**Ce qu'on livre.**
- Des **actions en un clic** sur une transcription : *Nettoyer* (supprimer les tics de langage et corriger la ponctuation sans réécrire), *Résumer*, *Extraire les actions et décisions*, *Rédiger un e-mail*, *Transformer en notes structurées*.
- Des **modèles d'instructions personnalisables**, que l'utilisateur crée, nomme et réutilise.
- Pour la dictée universelle (n°1) : un **style de sortie** facultatif (« tel quel », « nettoyé », « formel ») appliqué avant le collage.
- Le résultat s'affiche à côté du texte d'origine, qu'il ne remplace jamais.

**Ancrage technique.** Ne pas embarquer de LLM dans l'application : se brancher sur un **serveur local compatible OpenAI** (Ollama, LM Studio, llama.cpp server), sur `localhost`, avec détection automatique. Ollama gère les GPU AMD sous Windows. Sur la RX 7800 XT (16 Go), turbo en float16 (~1,6 Go) et un modèle 7-8B quantifié en 4 bits (~5 Go) tiennent ensemble en VRAM. Si aucun serveur n'est détecté, la fonctionnalité est masquée : l'application reste entièrement utilisable sans.

**Critère de succès.** « Résumer » sur une transcription de 30 minutes rend un résultat en moins de 20 s, entièrement hors ligne.

### 10. Traduction et sous-titres bilingues

**Le problème.** Regarder une vidéo dans une langue qu'on maîtrise mal, préparer des sous-titres pour un public international, comprendre un message vocal reçu en espagnol.

**Ce qu'on livre.**
- **Vers l'anglais** depuis n'importe quelle langue, directement par Whisper (tâche `translate`), fichiers et mode Direct.
- **Vers les autres langues** (dont le français) grâce à l'IA locale (n°9).
- Export de **sous-titres bilingues** (langue d'origine + traduction, deux lignes par sous-titre) ou d'une piste traduite séparée.

**Ancrage technique.** Ajouter `task` à `TranscribeOptions` et le transmettre au moteur. Point d'attention : **large-v3-turbo n'a pas été entraîné pour la traduction** et la traduit mal. La traduction directe doit donc basculer automatiquement sur large-v3 et le signaler dans l'interface. La traduction par LLM se fait segment par segment, pour conserver les horodatages.

**Critère de succès.** Un SRT bilingue français/anglais d'une vidéo de 10 minutes, exploitable sans retouche majeure.

---

## Chantiers transverses (hors top 10, à mener en continu)

Ils n'apparaissent pas comme fonctionnalités, mais conditionnent l'adoption :

1. ✅ *(livré : PyInstaller + Inno Setup, accélération NVIDIA/AMD téléchargée selon la carte, repli processeur expliqué ; reste la signature)* **Installeur en un clic.** L'installation par script PowerShell exclut la plupart des utilisateurs non développeurs. Cible : un installeur unique (PyInstaller ou Briefcase + Inno Setup/MSIX) qui embarque le runtime ROCm et télécharge le modèle au premier lancement, avec une barre de progression.
2. **Écran de premier lancement.** Vérification du GPU, choix du micro avec test de niveau, téléchargement du modèle, essai du raccourci de dictée.
3. **Ouverture à d'autres GPU.** Le Protocol `TranscriptionEngine` permet d'ajouter un backend **whisper.cpp (Vulkan)** qui couvrirait NVIDIA, Intel Arc et les AMD non pris en charge par les wheels ROCm. Cela multiplie l'audience potentielle.
4. **Découpage de `main_window.py`.** Un contrôleur de session sans dépendance Qt Widgets, prérequis des n°1, 4 et 5, et plus facile à tester.
5. **Journal de diagnostic** dans `%LOCALAPPDATA%\MyWhisper\logs` et un bouton « Copier les informations de diagnostic ». Aujourd'hui, les erreurs GPU ne sont visibles que dans la console.

## Ce qui a été écarté (pour l'instant)

- **Synchronisation cloud et comptes utilisateurs** : contraire au positionnement 100 % local.
- **Synthèse vocale (texte vers parole)** : c'est un autre produit, sans synergie technique forte avec faster-whisper.
- **Application mobile** : la valeur de MyWhisper repose sur le GPU du poste de travail.
- **Modèles distillés supplémentaires (distil-large-v3…)** : faciles à ajouter (une entrée `ModelSpec`), mais turbo couvre déjà le besoin de vitesse. À reconsidérer si le backend CPU devient une cible.
