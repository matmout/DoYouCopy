# Notes de version

## Prochaine version

### Microsoft Store

- DoYouCopy est aussi distribué sur le Microsoft Store (paquet MSIX signé par Microsoft), en plus de l'installeur.
- Depuis le Store, « Démarrer avec Windows » passe par les tâches de démarrage de Windows (*Paramètres → Applications → Démarrage*), et l'entrée du menu Démarrer est fournie par le paquet.

## 1.1.0

### Nouveau nom : DoYouCopy

L'application s'appelait MyWhisper. Elle devient **DoYouCopy** — *« I talk, you write. »* — avec une nouvelle icône.

- La mise à jour est automatique : l'installeur reprend vos modèles, votre historique (enregistrements audio compris), vos réglages et l'accélération graphique, puis désinstalle l'ancienne version.
- Le lancement au démarrage de Windows est conservé.

### Sécurité

- Les fichiers du modèle téléchargés ne peuvent plus être écrits en dehors de leur dossier, même si la réponse du serveur était falsifiée.
- La détection de la carte graphique lance PowerShell depuis le dossier système de Windows uniquement.

### Corrections

- Si le dossier de l'historique change de place, les enregistrements audio sont retrouvés au lieu d'être supprimés.

## 1.0.0 (4 octobre 2026)

Première version publique. Dictez ou transcrivez dans votre langue, sur votre PC, sans cloud.

### Fonctionnalités

- **Dictée dans n'importe quelle application** : maintenez **Ctrl + Maj + Espace**, parlez, relâchez, le texte est collé là où se trouve le curseur. L'application reste dans la zone de notification et peut démarrer avec Windows.
- **Transcription** du micro, de fichiers audio et vidéo (wav, mp3, m4a, flac, ogg, mp4…), en direct (le texte s'affiche pendant que vous parlez) et de l'**audio de l'ordinateur** (Teams, Zoom, YouTube…), seul ou mixé avec le micro.
- **Multilingue** : détection automatique de la langue parmi ~100, traduction vers l'anglais.
- **Trois modèles Whisper** : Léger (small), Turbo (large-v3-turbo, par défaut) et Précis (large-v3), téléchargés au premier usage.
- **Vocabulaire personnalisé** : mots à favoriser, remplacements, commandes vocales de ponctuation.
- **Historique local** de toutes les transcriptions et dictées, avec recherche plein texte et audio conservé.
- **Éditeur synchronisé** : réécoute avec surlignage du mot en cours, édition sans perte des horodatages, mots douteux soulignés, retranscription d'un passage avec le modèle Précis.
- **Exports** TXT, SRT, WebVTT, Markdown, Word (.docx) et JSON.
- **Installeur sans droits administrateur** : il détecte la carte graphique et télécharge l'accélération adaptée (NVIDIA CUDA 12, AMD ROCm 7.2), sinon bascule sur le processeur en expliquant pourquoi.
- **Désinstallation propre** : supprime l'application, ses raccourcis et l'accélération ; propose de supprimer aussi l'historique, les modèles et les réglages.
- **100 % local** : aucun compte, aucune télémétrie. Internet ne sert qu'à télécharger le modèle et l'accélération, une fois.

### Limites connues

- L'installeur n'est **pas signé** : Windows SmartScreen affiche « Windows a protégé votre ordinateur ». Cliquez sur **Informations complémentaires**, puis **Exécuter quand même**.
- L'interface est **en français uniquement** (la reconnaissance vocale, elle, est multilingue).
- Windows 10 / 11 64 bits uniquement.
- Pas de mise à jour automatique : les nouvelles versions sont publiées sur la page [Releases](https://github.com/matmout/DoYouCopy/releases).
- Pour l'audio de l'ordinateur mixé avec le micro, les voix ne sont pas encore attribuées à des personnes.
