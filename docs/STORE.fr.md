# Publier DoYouCopy sur le Microsoft Store

DoYouCopy est publié sur le Store sous forme de paquet **MSIX**, à côté de l'installeur
Inno Setup. Le Store signe lui-même les paquets : cette version n'a donc pas besoin de
certificat de signature de code, et Windows SmartScreen ne l'avertit pas.

| | |
|---|---|
| Nom réservé | DoYouCopy |
| `Package/Identity/Name` | `TrachselLabs.DoYouCopy` |
| `Package/Identity/Publisher` | `CN=B9E47065-60AA-4882-A69C-DB710C0BD38A` |
| `PublisherDisplayName` | Trachsel Labs |
| Package Family Name | `TrachselLabs.DoYouCopy_7zb5jdp1hfh86` |
| Store ID | `9NJXGZFJ0V64` (page : `https://apps.microsoft.com/detail/9NJXGZFJ0V64`, une fois publiée) |

Ces valeurs viennent de Partner Center (*Gestion des produits → Identité du produit*).
Elles sont dans [`packaging/msix/identity.json`](../packaging/msix/identity.json) ;
le manifeste est [`packaging/msix/AppxManifest.template.xml`](../packaging/msix/AppxManifest.template.xml).

## Construire le paquet

GitHub Actions le construit à chaque push sur `main`, à chaque pull request et à la
demande (*Actions → Build → Run workflow*) : artefact **msix**,
`DoYouCopy-<version>-x64.msix`. Sur un tag `v*`, il est aussi joint à la release brouillon.

En local (Windows SDK requis, `winget install Microsoft.WindowsSDK.10.0.26100`) :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1 -SkipInstaller
powershell -ExecutionPolicy Bypass -File scripts\build_msix.ps1
```

- `-DevSign` : signe le paquet avec un certificat de test (sujet = Publisher), approuvé
  pour l'utilisateur courant, pour l'installer avec `Add-AppxPackage` et l'essayer avant
  la soumission. **Ne pas déposer ce paquet-là** dans Partner Center.
- `-Wack` : lance le Windows App Certification Kit, les tests que le Store passe à la
  soumission (terminal administrateur). Le rapport est écrit à côté du paquet.

La version du paquet est `doyoucopy.__version__` suivie de `.0` (`1.1.0` → `1.1.0.0`) :
le Store réserve le 4ᵉ nombre. Chaque soumission doit avoir une version plus grande que
la précédente.

## Ce qui change dans le paquet

L'application détecte qu'elle tourne depuis le paquet (`doyoucopy.desktop.packaging`) :

- **Démarrage avec Windows** : tâche de démarrage déclarée dans le manifeste
  (`DoYouCopyStartup`, désactivée par défaut), activée depuis les réglages. Si
  l'utilisateur l'a coupée dans *Paramètres → Applications → Démarrage*, seul ce panneau
  peut la rallumer : l'application le lui dit.
- **Raccourcis** : la section disparaît des réglages, puisque le paquet a sa propre
  entrée dans le menu Démarrer.
- **Données** : Windows range les nouveaux fichiers de `%LOCALAPPDATA%\DoYouCopy` et
  `%APPDATA%\DoYouCopy` dans
  `%LOCALAPPDATA%\Packages\TrachselLabs.DoYouCopy_7zb5jdp1hfh86\LocalCache`, et les
  supprime à la désinstallation. Les boutons « Ouvrir le dossier » ouvrent ce dossier réel.
- **Accélération graphique** : pas d'installeur pour la proposer ; le bandeau « plus lent
  sur ce PC » de la fenêtre principale la propose au premier lancement.
- **MyWhisper** : les données de l'ancien nom sont reprises au premier lancement, comme
  avec l'installeur.

> Ne pas installer la version Store et la version Inno Setup en même temps : elles
> partagent le même nom et se marcheraient dessus. Désinstaller l'une avant l'autre.

## Soumettre

1. Partner Center → *Apps et jeux* → DoYouCopy → *Démarrer la soumission*.
2. **Tarification et disponibilité** : gratuit, tous les marchés (ou la sélection voulue).
3. **Propriétés** : catégorie *Productivité*. URL de la politique de confidentialité :
   `https://github.com/matmout/DoYouCopy#privacy-policy`. Site web :
   `https://github.com/matmout/DoYouCopy`.
4. **Classification par âge** : questionnaire IARC (pas de contenu généré par d'autres
   utilisateurs, pas d'achats, pas de partage de position).
5. **Packages** : déposer `DoYouCopy-<version>-x64.msix`, **non signé**, venant de
   l'artefact GitHub Actions.
6. **Description du Store** (fr-FR) : description, captures d'écran (au moins une,
   1366×768 ou plus ; `docs/apercu-*.png`), logo du Store 300×300
   (`docs/icon.png` agrandi, ou `Square150x150Logo.scale-200.png` de `build\msix\Assets`).
7. **Options de soumission → Notes pour la certification** : coller le texte ci-dessous.
8. *Soumettre au Store*. La certification prend en général de quelques heures à 3 jours
   ouvrés.

### Notes pour la certification

> DoYouCopy is a local, offline speech-to-text app (open source, GPL-3.0:
> https://github.com/matmout/DoYouCopy). It is a Win32 desktop app (Python, Qt), hence
> **runFullTrust**.
>
> - **Push-to-talk dictation**: a low-level keyboard hook (WH_KEYBOARD_LL) watches only
>   the user-configured hotkey (default Ctrl+Shift+Space). While it is held, the
>   microphone records; on release, the transcribed text is pasted into the focused app
>   (clipboard + SendInput Ctrl+V, the previous clipboard content is restored).
>   Keystrokes are never recorded or sent anywhere.
> - **Microphone**: recording, live transcription and dictation. Audio is processed on
>   the device; nothing is uploaded.
> - **internetClient**: only downloads, on user action: Whisper speech models from
>   huggingface.co and, optionally, the GPU acceleration libraries for the user's card
>   (NVIDIA CUDA libraries from PyPI, AMD ROCm libraries from repo.radeon.com and the
>   CTranslate2 GitHub releases). Versions are pinned and every file is verified against
>   a SHA-256 hash embedded in the app. These libraries only accelerate the existing
>   transcription engine on the GPU; they add no feature, and the app works without
>   them (CPU). A strict offline mode blocks every download.
> - **Startup task**: disabled by default; enabled only if the user turns on "Démarrer
>   avec Windows" in the settings.
>
> To test: launch the app, let the "Turbo" model download (~1.6 GB) or pick "Léger"
> (small) in Settings → Transcription, then press Record, or hold Ctrl+Shift+Space in
> Notepad and speak. The interface is in French.

## Si la certification refuse le téléchargement de l'accélération graphique

La règle 10.2.2 du Store interdit le code téléchargé qui change les fonctionnalités de
l'application. Les notes ci-dessus expliquent que ces bibliothèques n'ajoutent aucune
fonction. Si Microsoft refuse quand même, la solution de repli est une version Store qui
fonctionne uniquement sur le processeur : il faudra masquer le bandeau et la section
*Matériel → Accélération* en mode paquet.
