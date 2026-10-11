# AMPTemplates-ClassiCube — ClassiCube server (MCGalaxy) for AMP

**AMP Generic Module** template for a **ClassiCube** server running **MCGalaxy**, the most used
server software for ClassiCube (the free Minecraft Classic compatible game, playable in a browser
on classicube.net or with the ClassiCube game for Windows, macOS, Linux, Android and iOS).
Written for TeamKit, a free French game host, on 11 Oct 2026.

> Résumé en français à la fin du fichier.

## Install and Update (`scripts/installer-classicube.sh`)

MCGalaxy publishes a **self-contained Linux build** (Mono embedded) on the ClassiCube CDN:

| Channel | URL | Notes |
|---|---|---|
| stable (default) | `https://cdn.classicube.net/client/mcg/release/linux64` | 1.9.5.3, 20.7 MB, 18 Mar 2025 |
| development | `https://cdn.classicube.net/client/mcg/latest/linux64` | rebuilt on every commit (17.2 MB, 2 Oct 2026) |

Each Update downloads the channel chosen with the *Version de développement* checkbox, checks that
the file is a Linux ELF executable of at least 5 MB (not an error page), saves it as `MCGalaxy`
(`chmod 755`) and remembers the channel in `.canal-mcgalaxy`. If the CDN does not answer and a
server is already installed, it is kept. **Only the `MCGalaxy` file is ever replaced**: `levels/`,
`ranks/`, `properties/`, `plugins/`, `MCGalaxy.db`, `blockdb/`, `text/`, `extra/`, `logs/` are never
touched. Going back from development to stable prints a warning (newer files may not load in an
older build: take an AMP backup first).

The binary runs as is in `cubecoders/ampbase:debian` (checked in a disposable container, no extra
package). `curl` and `ca-certificates` are added by `ExtraContainerPackages` for the download only.

The checkbox value reaches the installer through the Update command line (`{{version_dev}}`). If
AMP does not substitute it there, the installer reads the value rendered at the last start
(`reglages-classicube.txt`), else uses the stable channel.

## Start (`scripts/lancer-classicube.sh`)

`/bin/bash lancer-classicube.sh <port> <max players>`:

1. reads `reglages-classicube.txt` (rendered by AMP from `scripts/AMP_reglages-classicube.txt`, one
   `key=value` per line);
2. **at every start**, copies the settings into `properties/server.properties` (MCGalaxy rewrites
   that file itself on start and on `/server`, `/main`…). Only our keys are touched: an existing
   line is replaced (key matched without case, comment lines skipped, line ending kept), a missing
   key is appended, the file is created if it does not exist yet (MCGalaxy completes it with its
   defaults on first start). Done by a small embedded **perl** script (perl-base modules only)
   that receives file paths as arguments: **no value ever goes through the shell** (no `eval`, no
   command built from a value). Control characters and line breaks inside a value become spaces,
   so a value can never create another key;
3. `exec` MCGalaxy with `TERM=dumb` (the embedded Mono then writes no ANSI colour codes): AMP's
   console is wired straight to the server's stdin, so `/rank`, `/say`, `/save all`… work from AMP,
   and AMP stops the server with **`/shutdown`** (10 s countdown shown to players, then every map
   is saved; `ExitTimeout` 60 s). `/restart` re-executes the server in the same process.

Port and max players come from AMP (`{{$GamePort}}`, `{{$MaxUsers}}` on the command line, where
AMP substitutes them; never inside the rendered settings file, where it does not). If `MaxUsers`
arrives unsubstituted, the script reads `App.MaxUsers` from the instance's `GenericModule.kvp`,
else uses 32.

**One port: 25565/TCP.** The classicube.net browser client goes through classicube.net's websocket
relay (already trusted by MCGalaxy, `allow-ip-forwarding`): nothing else to open.

## Settings (AMP → Configuration)

| Setting | Default | `server.properties` |
|---|---|---|
| Nom du serveur | `[FR] TeamKit · ClassiCube` | `server-name`. MCGalaxy only accepts ASCII letters, digits and ASCII punctuation here and replaces the **whole** name by `[MCGalaxy] Default` otherwise (`ConfigStringAttribute.Constrain`). The script converts accents and common symbols (`é`→`e`, `·`/`–`→`-`, `« »`→`"`, `œ`→`oe`…) and drops the rest, with a console note: the default becomes `[FR] TeamKit - ClassiCube` |
| Message d'accueil | `Bienvenue sur TeamKit ! Infos et Discord : teamkit.fr` | `motd` (64 characters shown; `+hax`/`-fly`… words have a meaning) |
| Nom du propriétaire (affiché) | `TeamKit` | `server-owner`: display text only, gives no rights |
| Visible dans la liste classicube.net | ticked | `public` |
| Joueurs maximum | 32 (1–256) | `max-players` (AMP's `$MaxUsers`) |
| Places invités | 30 | `max-guests`, capped to max players |
| Vérifier les pseudos ClassiCube | ticked | `verify-names`. **Unticked = anyone can log in with an admin's name.** The script prints a warning |
| Rang par défaut | guest | `default-rank`: guest, builder or advbuilder |
| Accepter le règlement à l'arrivée | unticked | `agree-to-rules-on-entry` (rules in `text/rules.txt`) |
| Filtre de grossièretés | unticked | `profanity-filter` (English list in `text/badwords.txt`) |
| Thème des nouvelles cartes | flat | `default-mapgen-theme`: theme used by `/newlvl` without a theme. The 22 values offered are the non-admin themes registered by MCGalaxy 1.9.5.3 (`SimpleGen`, `RealisticMapGen`, `ClassicGenerator`, `fCraftMapGen`). **It does not change the main map**: MCGalaxy always generates `main` flat, 128×64×128 (`Server.Init.cs`, `GenerateMain`) |
| Version de développement | unticked | none: used by the Update |

Invalid values (wrong boolean, rank, theme, number) are reported in the console and the current
value is kept. `port`, `max-players` are always written from AMP. `HeartbeatURL` is never exposed.

## Becoming owner

The *Nom du propriétaire* field is only text. To get the **Owner** rank:

1. join the server once with your ClassiCube account;
2. in AMP's console: `/rank YourClassiCubeName owner`;
3. on your next join, MCGalaxy asks staff ranks for a verification password
   (`admin-verification`, default on): `/setpass <password>` once, then `/pass <password>` at each
   join. Choose a password different from your classicube.net one.

## Player side

- **Browser**: open the server page on classicube.net (public list, or the link printed in the
  console at start: `Server URL found: http://www.classicube.net/server/play/<hash>/`).
- **Game**: ClassiCube → *Sign in* → *Servers* → search the name. With `verify-names` on, direct IP
  connection needs the mppass from classicube.net: use the server list or the link.
- **Unlisted** (*Visible…* unticked): only the link works; names are still verified.

## Console

| | Regex (.NET) on |
|---|---|
| ready | `(HH:mm:ss) Finished setting up server` |
| join | `(HH:mm:ss) Name [ip] connected using Client.` (`Player.Login.cs`) |
| leave | `(HH:mm:ss) Name disconnected (reason).` / `Name kicked (reason).` (`Player.cs`) |
| update | `MCGalaxy update available!` (only when `check-updates` is on, every 2 h) |

The `Name (ip) disconnected. (reason)` line is **not** a leave: it is written for sessions that
never completed login (wrong mppass, ban, full server), whose name may be an unverified, borrowed
one; it would remove the real player from AMP's list. Names: `A-Za-z0-9._`, 1–16 characters
(`USERNAME_ALPHABET`). The regexes tolerate ANSI colour codes. No chat regex (format not reliable).

## Tested here (11 Oct 2026, `python verifier.py`)

JSON, `@IncludeJson`, port refs, settings ↔ template ↔ script ↔ `server.properties` key, theme and
rank lists against MCGalaxy's source; the real launcher (bash + perl) on 10 rendered setting sets:
no file, no settings file, a full MCGalaxy-style file in CRLF with comments/duplicates/other keys,
missing key appended, values with spaces, `&`, apostrophes, `$( )`, backticks, `;`, `|`, tab, CR
and line breaks, accents and symbols in the name, invalid values, guests > players, `MaxUsers` not
substituted with and without `GenericModule.kvp`; `exec` + `TERM=dumb` + stdin with a fake server;
the installer with a fake `curl` (stable, development, last-start fallback, ELF check, CDN down,
server data untouched); console regexes on 12 lines and 15 traps. Mutation-tested (the checks fail
when the script is broken on purpose).

**Not tested yet**: AMP itself (Update, rendering of the checkbox in the Update command line,
`$MaxUsers` on the command line, user list), a real MCGalaxy start under AMP, real players.

## Files

| File | Role |
|---|---|
| `classicube.kvp`, `classicube*.json`, `manifest.json` | the AMP template |
| `scripts/installer-classicube.sh` | download and check of MCGalaxy (Update) |
| `scripts/lancer-classicube.sh` | start script (settings → `server.properties`, then `exec`) |
| `scripts/AMP_reglages-classicube.txt` | settings model rendered by AMP |
| `verifier.py` | pre-push checks, must print `Tout est bon.` |

The three `scripts/` files are fetched from this repository (raw.githubusercontent.com, branch
`main`) at each Update, so **the repository must be public**.

## Credits

MCGalaxy © the MCGalaxy team, dual-licensed ECL-2.0 / GPL-3.0 (github.com/ClassiCube/MCGalaxy).
ClassiCube © UnknownShadow200 and contributors. This repository only contains the template; the
server binary is downloaded from cdn.classicube.net.

---

## Résumé en français

Template AMP d'un **serveur ClassiCube** (le Minecraft Classic libre, jouable dans le navigateur
sur classicube.net) avec **MCGalaxy**. L'Update télécharge le binaire Linux autonome officiel
(version stable 1.9.5.3, ou version de développement si la case est cochée) : rien à compiler,
aucun paquet pour le serveur. Un seul port, **25565 en TCP**.

- **Réglages en français**, recopiés dans `properties/server.properties` **à chaque démarrage**
  (MCGalaxy réécrit ce fichier lui-même) : nom, message d'accueil, propriétaire affiché, liste
  publique, joueurs et invités, vérification des pseudos (à laisser cochée), rang par défaut,
  règlement, filtre de grossièretés, thème des nouvelles cartes, version de développement.
- **Nom du serveur** : MCGalaxy refuse tout caractère non ASCII (il remplacerait le nom entier) :
  accents et symboles sont convertis, le « · » du nom par défaut devient « - ».
- **Devenir propriétaire** : `/rank <pseudo ClassiCube> owner` dans la console d'AMP, puis
  `/setpass` et `/pass` à la connexion.
- **Console d'AMP** branchée sur le serveur, arrêt par `/shutdown` (10 s de compte à rebours),
  joueurs visibles dans AMP.
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
