# Roadmap DoYouCopy

*Révisée le 4 octobre 2026 pour la sortie de la **version 1.0**, publiée le soir même. Elle remplace la roadmap « 10 fonctionnalités » du même jour, dont six sont livrées.*

## 1. Le constat (design thinking)

### Pour qui ?

| Profil | Ce qu'il fait | Ce qui compte pour lui |
|---|---|---|
| **Le professionnel qui dicte** (médecin, avocat, consultant, développeur) | Dicte des e-mails, des notes, des prompts, plusieurs fois par heure, dans ses applications habituelles. | Que ce soit **instantané**, **fiable** sur son jargon, et que sa voix **ne quitte pas** son poste. |
| **Celui qui transcrit** (journaliste, chercheur, étudiant, créateur vidéo) | Transcrit des entretiens, réunions, cours, vidéos, en français, en anglais ou dans une autre langue. | Un texte **juste**, **corrigeable**, **exportable** (Word, sous-titres), et **retrouvable** plus tard. |

Dans les deux cas, le besoin profond est le même : **« Je parle (ou j'ai un enregistrement), je veux du texte, dans ma langue, sans rien envoyer à personne. »** Win + H, Google Docs ou les services en ligne répondent à la première moitié, pas à la seconde.

### La promesse de la 1.0

> **Dictez ou transcrivez dans votre langue, sur votre PC, sans cloud.**

Une 1.0 n'est pas la version qui fait tout : c'est celle qui tient sa promesse **à chaque fois**. Le critère de tri est donc simple : une tâche entre dans la 1.0 si, sans elle, un nouvel utilisateur **ne peut pas** installer, dicter, transcrire, retrouver, exporter ou désinstaller proprement. Tout le reste attend.

### Ce que la 1.0 couvre déjà

| Moment du parcours | Besoin | État |
|---|---|---|
| Installer | Un installeur, sans droits administrateur, qui choisit l'accélération GPU | ✅ Installeur Inno Setup, NVIDIA (CUDA) / AMD (ROCm) / repli processeur expliqué |
| Démarrer | Le modèle se télécharge seul, avec une progression lisible | ✅ (affichage corrigé pour les fichiers de plus de 2 Go) |
| Dicter | Dans n'importe quelle application, un raccourci | ✅ Dictée universelle, zone de notification, démarrage avec Windows |
| Transcrire | Micro, fichiers audio/vidéo, mode Direct, audio de l'ordinateur | ✅ |
| Multilingue | Détection automatique de la langue, traduction vers l'anglais | ✅ (Whisper, ~100 langues) |
| Être juste | Vocabulaire métier, remplacements, commandes vocales | ✅ |
| Retrouver | Historique local avec recherche | ✅ |
| Corriger | Réécouter, éditer, retranscrire un passage | ✅ Éditeur synchronisé |
| Livrer | TXT, SRT, VTT, Markdown, Word, JSON | ✅ |
| Partir | Désinstaller sans laisser de traces | ✅ Choix de garder ou supprimer historique, modèles et réglages |

**Conclusion : le périmètre fonctionnel de la 1.0 est atteint.** Il ne reste que du travail de **sortie** : rien de nouveau ne doit entrer ce soir.

## 2. Plan de sortie de la 1.0 (ce soir)

| # | Tâche | Pourquoi c'est bloquant | Durée |
|---|---|---|---|
| 1 | Commiter les correctifs en attente (progression > 2 Go, message de désinstallation) | Ils doivent faire partie de la 1.0 | 5 min |
| 2 | Passer la version à **1.0.0** (`src/doyoucopy/__init__.py`) | L'installeur, l'exécutable et « Ajout/Suppression de programmes » affichent encore 0.2.0 | 5 min |
| 3 | Mettre le README à jour : la désinstallation propose aussi de supprimer l'**historique** | La documentation doit dire ce qui est effacé | 5 min |
| 4 | Recompiler l'installeur 1.0.0, noter son SHA-256 | Livrable de la release | 10 min |
| 5 | **Recette manuelle** sur l'installeur final (liste ci-dessous) | Dernier filet avant publication | 30 min |
| 6 | Notes de version (`CHANGELOG.md`) : nouveautés, limites connues | Les utilisateurs doivent savoir ce qu'ils installent | 15 min |
| 7 | Fusionner `ameliorations-audit` dans `main`, tag `v1.0.0`, release GitHub avec l'installeur et son SHA-256 | Le README pointe vers la page Releases | 15 min |

### Recette de la 1.0 (étape 5)

À faire sur l'installeur final, dans cet ordre :

1. Installer : la version **1.0.0** est affichée ; l'accélération GPU se télécharge et la carte est testée.
2. Premier lancement : le modèle se télécharge, pourcentage entre 0 et 100, tailles cohérentes.
3. Dicter dans le Bloc-notes avec **Ctrl + Maj + Espace** (appui maintenu), en français puis en anglais.
4. Enregistrer 30 s au micro, puis transcrire un fichier MP3 ou MP4.
5. Mode Direct, puis audio de l'ordinateur (une vidéo YouTube).
6. Retrouver la session dans l'historique, corriger un mot, exporter en SRT et en Word.
7. Fermer la fenêtre : l'application reste dans la zone de notification ; Quitter : le processus disparaît.
8. Désinstaller en répondant **Non** : les données restent. Réinstaller, désinstaller en répondant **Oui** : `%LOCALAPPDATA%\DoYouCopy` et `%APPDATA%\DoYouCopy` ont disparu, ainsi que les raccourcis et le lancement au démarrage.

> ⚠️ Avant l'étape 8, copier `%LOCALAPPDATA%\DoYouCopy\history` si l'historique actuel doit être conservé.

### Limites connues, assumées pour la 1.0

À écrire dans les notes de version plutôt qu'à corriger ce soir :

- **Installeur non signé** : Windows SmartScreen affiche un avertissement (« Informations complémentaires » → « Exécuter quand même »). Un certificat de signature coûte de l'argent et des jours de validation.
- **Interface en français uniquement.** La reconnaissance vocale, elle, est multilingue.
- **Windows 10 / 11 64 bits uniquement.**
- **Pas de mise à jour automatique** : les nouvelles versions se téléchargent sur la page Releases.
- En réunion, les voix du micro et de l'ordinateur sont **mixées** : pas encore de « qui parle ».

## 3. Après la 1.0

Classement par valeur pour les deux profils ci-dessus, effort faible d'abord.

### 1.1 : élargir l'audience (quelques semaines)

| Tâche | Pourquoi | Effort |
|---|---|---|
| ✅ **Interface en anglais** (et choix de la langue d'interface) | Fait : français et anglais, la langue de Windows par défaut, réglable dans *Général*. Une autre langue = un fichier `locales/<code>.py`. | M |
| **Signature de l'installeur** | Supprime l'avertissement SmartScreen, principal motif d'abandon à l'installation. | S (+ délai du certificat) |
| **Transcription de plusieurs fichiers** (file d'attente, export automatique à côté de la source) | Le profil « celui qui transcrit » a souvent des dizaines de fichiers. | M |
| **Avis de nouvelle version**, désactivable, sans envoyer de données (lecture de la page Releases) | Sans lui, les correctifs n'atteignent pas les utilisateurs. Désactivé en mode hors ligne strict. | S |

### 1.2 : réunions

| Tâche | Pourquoi | Effort |
|---|---|---|
| **Identification des locuteurs** (sherpa-onnx, CPU, sans PyTorch), avec renommage et prise en charge dans tous les exports | « Qui a dit quoi » est indispensable pour citer un entretien ou relire une réunion. | L |
| **Pistes séparées « Moi » / « Les autres »** pour l'audio de l'ordinateur + micro | Première attribution des locuteurs, fiable et gratuite pour les appels. | M |

### Plus tard, si la demande se confirme

- **Post-traitement par IA locale** (nettoyer, résumer, extraire les actions) via un serveur local Ollama / LM Studio. Utile, mais dépend d'un outil tiers à installer : à réserver aux utilisateurs qui le demandent.
- **Backend whisper.cpp (Vulkan)** pour les cartes Intel Arc et les AMD non prises en charge par ROCm. À considérer si les retours montrent beaucoup d'utilisateurs en repli processeur.
- **Ligne de commande** (`doyoucopy transcribe *.mp3 --format srt`) : pour les automatisations, une minorité d'utilisateurs.

## 4. Ce qui est écarté

| Idée | Raison |
|---|---|
| Profils de vocabulaire multiples | Une seule liste suffit à la grande majorité ; complexité d'interface sans gain clair. |
| Sous-titres bilingues et traduction vers d'autres langues que l'anglais | Dépendent de l'IA locale ; usage de niche. La traduction vers l'anglais existe déjà. |
| Dossier surveillé | Couvert en pratique par la transcription de plusieurs fichiers (1.1). |
| Écran de premier lancement dédié | L'installeur choisit déjà l'accélération et le modèle se télécharge seul : un assistant de plus ralentirait l'arrivée au premier mot dicté. |
| Synchronisation cloud, comptes | Contraire à la promesse : rien ne quitte le poste. |
| Synthèse vocale, application mobile | Autres produits ; la valeur de DoYouCopy repose sur le poste de travail. |
| Modèles distillés supplémentaires | Turbo couvre déjà le besoin de vitesse. |
