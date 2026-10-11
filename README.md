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

`/bin/bash lancer-classicube.sh <port> <max players> <relay port>`:

1. reads `reglages-classicube.txt` (rendered by AMP from `scripts/AMP_reglages-classicube.txt`, one
   `key=value` per line);
2. **at every start**, copies the settings into `properties/server.properties` (MCGalaxy rewrites
   that file itself on start and on `/server`, `/main`…). Only our keys are touched: an existing
   line is replaced (key matched without case, comment lines skipped, line ending kept), a missing
   key is appended, the file is created if it does not exist yet (MCGalaxy completes it with its
   defaults on first start). Done by a small embedded **perl** script (perl-base modules only)
   that receives file paths as arguments: **no value ever goes through the shell** (no `eval`, no
   command built from a value). Control characters and line breaks inside a value become spaces,
   so a value can never create another key. `HeartbeatURL` is written there too, and
   `properties/authservices.properties` is rewritten (see *Play from your own web page*), both
   through a temporary file and a rename;
3. if *Relais pour un proxy web* is ticked: starts
   `setpriv --pdeathsig TERM -- socat TCP-LISTEN:<relay>,fork,reuseaddr,nodelay TCP:127.0.0.1:<port>,nodelay`
   in the background (stdin `/dev/null`, so it never eats AMP's console input), checks one second
   later that it is still alive and says so in the console. Its parent is the script's process,
   which becomes MCGalaxy at the `exec` below: the relay lives and dies with the server
   (`--pdeathsig`), and survives MCGalaxy's `/restart` (same process);
4. `exec` MCGalaxy with `TERM=dumb` (the embedded Mono then writes no ANSI colour codes): AMP's
   console is wired straight to the server's stdin, so `/rank`, `/say`, `/save all`… work from AMP,
   and AMP stops the server with **`/shutdown`** (10 s countdown shown to players, then every map
   is saved; `ExitTimeout` 60 s). `/restart` re-executes the server in the same process.

Port and max players come from AMP (`{{$GamePort}}`, `{{$MaxUsers}}` on the command line, where
AMP substitutes them; never inside the rendered settings file, where it does not). If `MaxUsers`
arrives unsubstituted, the script reads `App.MaxUsers` from the instance's `GenericModule.kvp`,
else uses 32.

**One port to open: 25565/TCP.** The classicube.net browser client goes through classicube.net's
websocket relay (already trusted by MCGalaxy, `allow-ip-forwarding`): nothing else to open. The
second port, **`RelayPort` 25566/TCP (*Relais du proxy web*)**, is only used by the optional relay
below and must **never** be opened to the world.

## Settings (AMP → Configuration)

| Setting | Default | `server.properties` |
|---|---|---|
| Nom du serveur | `[FR] TeamKit - ClassiCube` | `server-name`. MCGalaxy only accepts ASCII letters, digits and ASCII punctuation here and replaces the **whole** name by `[MCGalaxy] Default` otherwise (`ConfigStringAttribute.Constrain`). The script converts accents and common symbols (`é`→`e`, `·`/`–`→`-`, `« »`→`"`, `œ`→`oe`…) and drops the rest, with a console note: the default becomes `[FR] TeamKit - ClassiCube` |
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
| Service de connexion supplémentaire (adresse) | empty | `HeartbeatURL` = classicube.net alone, or classicube.net + this address |
| Suffixe des pseudos de ce service | `+` | `name-suffix` of that service in `properties/authservices.properties` |
| Relais pour un proxy web | unticked | none: starts `socat` on `RelayPort` |

Invalid values (wrong boolean, rank, theme, number) are reported in the console and the current
value is kept. `port`, `max-players` are always written from AMP, and **`verify-lan-ips = true`**
is always written: with MCGalaxy's default (`false`), a connection from loopback or a private
network (`10/8`, `172.16/12`, `192.168/16`) is let in **without name verification**
(`LoginAuthenticator.VerifyLogin`, `IPUtil.IsPrivate`). In a bridged Docker container that covers
the relay (`127.0.0.1`), a proxy on the host reaching the game port through `docker-proxy`
(`172.17.0.1`) and every other container on the bridge: any of them could log in as the owner.
With `true`, everyone needs a valid mppass, whatever their address.

## Play from your own web page

Goal: a page on your own site (TeamKit for us) that runs the ClassiCube web client and lets people
play **with an account of your site**, on top of classicube.net accounts. Two independent settings,
both off by default (nothing changes until you fill them in). Checked against MCGalaxy 1.9.5.3.

### 1. A second authentication service (*Service de connexion supplémentaire*)

- `HeartbeatURL` (server.properties) accepts several comma-separated addresses. MCGalaxy sends its
  heartbeat to **each** of them (POST `application/x-www-form-urlencoded`, every 30 s and right at
  start), each with **its own salt** (`AuthService.GetOrCreate`, a new random salt at every start).
  A player is verified when `mppass = md5(salt + name)` for **one** of the services
  (`MppassAuthenticator`).
- The script writes `HeartbeatURL = http://www.classicube.net/heartbeat.jsp` alone when the setting
  is empty, else `http://www.classicube.net/heartbeat.jsp,<your address>`, and rewrites
  `properties/authservices.properties` (same layout and header as MCGalaxy's `SaveServices`): one
  block for classicube.net with an empty `name-suffix`, one for your service with the chosen suffix.
- **The suffix is appended to the names of players verified by your service**
  (`AuthService.AcceptPlayer`): `Kevin` from your site becomes `Kevin+`, a different player from
  `Kevin` of classicube.net (own rank, maps, bans; `/rank Kevin+ builder`). It must be 1–3
  characters among letters, digits, `+ ~ _ . -`, **with at least one `+`, `~` or `-`**: classicube.net
  names cannot contain those, so an account of your site can never take the name of a
  classicube.net player (staff included). Anything else is refused and `+` is used. `+` is the
  recommended value (MCGalaxy already knows it, e.g. in `ValidPlayerName`).
- **Address rules.** It must start with `https://`, contain no comma or space, and — stricter than
  you may expect — only **letters, digits, `:`, `/` and `.`**: MCGalaxy declares `HeartbeatURL` with
  the allowed characters `":/.,"` (`ServerConfig.cs`) and, on any other character (`-`, `_`, `?`,
  `=`, `&`, `%`…), silently replaces the **whole** value by classicube.net alone. So
  `https://teamkit.fr/classicube/heartbeat` works, `https://team-kit.fr/…` or `…/heartbeat.php?x=1`
  do not. A refused address is reported in the console and ignored (classicube.net only).

**What your site must do** (the server side is done):

1. receive the heartbeat at that address: fields `port`, `max`, `name`, `public`, `version` (7),
   `salt`, `users`, `software`, `web`. Keep the latest `salt`. **Accept heartbeats only from the
   game server's IP**: anyone can POST a fake salt, which would at least lock your players out;
2. answer **HTTP 200 with an empty body**. MCGalaxy ignores an empty answer; a non-empty one is
   printed as `Server URL found: …` and written to `text/externalurl.txt`;
3. for a logged-in user, compute `mppass = md5(salt + name)` (hex) for **their own name only**, a
   name made of `A-Z a-z 0-9 _ .`, 1 to 16 characters (MCGalaxy's `USERNAME_ALPHABET`, checked
   before any verification) and **without** the suffix. Never show the salt;
4. serve the web client (`hosting-webclient.md` of the ClassiCube repository: `ClassiCube.js` from
   `cs.classicube.net/client/latest/`, `default.zip`) on an **https** page, with
   `Module.arguments = [name, mppass, 'play.example.org/classicube', '443']`. The client builds
   `wss://<host>:<port>/<path>` from the third and fourth arguments (`interop_web.js`: `wss://`
   when the page is https-only), here `wss://play.example.org:443/classicube`.

### 2. The relay for a web proxy (*Relais pour un proxy web*)

The page connects with `wss://`, so something must terminate TLS: an **nginx on the same machine**.
MCGalaxy then sees nginx as the client. It only trusts the `X-Real-IP` header (the player's real
address) from **loopback** or from classicube.net's own proxy (`Sockets.cs`,
`IsTrustedForwarderIP`), and the instance is a bridged Docker container: nginx would arrive from
the bridge gateway (`172.17.0.1`), not from loopback. Hence the relay: ticked, the start script
runs `socat` **inside the container**, listening on `RelayPort` (25566 by default, *Relais du proxy
web* in AMP's Network tab) and reconnecting to `127.0.0.1:<game port>`. nginx → host port 25566 →
container → socat → `127.0.0.1:25565`: MCGalaxy sees loopback and uses `X-Real-IP` (bans, `/whois`,
`users` count all see the real address). Port checks: integer 1–65535, different from the game
port, else a console message and no relay (the server still starts). `socat` comes from
`Meta.ExtraContainerPackages`; `setpriv` is already in `cubecoders/ampbase:debian` (util-linux,
also used by the TeamKit PokerTH, Cockatrice, Wesnoth, LMP and PyChess templates).

nginx, inside the `server { listen 443 ssl; … }` block of the site serving the page:

```nginx
location = /classicube {
    proxy_pass http://127.0.0.1:25566;          # RelayPort of the instance (host side)
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header X-Real-IP $remote_addr;    # exact spelling: MCGalaxy compares it as is
    proxy_read_timeout 1h;
    proxy_send_timeout 1h;
}
```

MCGalaxy ignores the request path, so any `location` works as long as it matches the path given to
the client. `allow-ip-forwarding` must stay `true` (MCGalaxy's default, not touched here).

**Firewall: never open the relay to the world.** Every connection coming through the relay is
trusted for its `X-Real-IP`: open, anyone could choose the address the server sees (dodge IP bans,
fake the player count). AMP publishes the port with Docker, and **Docker-published ports bypass
ufw / INPUT rules**. Block it in the `DOCKER-USER` chain (it only sees traffic forwarded to the
container; nginx on the host itself is not affected), and make the rule persistent:

```sh
iptables  -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 25566 --ctdir ORIGINAL -j DROP
ip6tables -I DOCKER-USER -p tcp -m conntrack --ctorigdstport 25566 --ctdir ORIGINAL -j DROP
```

Then check from **another** machine that `nc -vz <public IP> 25566` fails, and that the web page
still connects. If AMP opened 25566 in its own firewall integration, close it there too. (If an
instance ever runs with host networking instead, nginx can reach `127.0.0.1:25565` directly and
the relay is not needed; a relay there would be blocked with a plain INPUT rule.) Even if the relay
leaked, names stay verified: the template forces `verify-lan-ips = true` (see *Settings*).

**Existing instances**: AMP copies the ports and the `App.*` keys when an instance is created. An
instance created before this version has no `RelayPort` and starts the script without the third
argument: the relay refuses to start and says so (the server still starts). **Recreate the
instance** to get the second port, the new command line and the three new settings (keep the world
with an AMP backup, or copy `levels/`, `ranks/`, `properties/`, `MCGalaxy.db`, `blockdb/`, `text/`,
`extra/`). Until then, an Update brings the new script, which keeps working with the old settings
(missing keys are left as they are).

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
server data untouched); console regexes on 16 lines and 17 traps. Mutation-tested (the checks fail
when the script is broken on purpose).

Authentication service and relay (11 Oct 2026, same script): 25 runs of the real launcher reading
back `HeartbeatURL` and `authservices.properties` the way MCGalaxy does (`PropertiesFile.Read`,
`AuthService.UpdateList`, `ConfigStringAttribute.Constrain`): empty service, valid ones (port,
sub-domain, `.php`, spaces around), service removed, old instance with unsubstituted variables,
no settings file, and refused ones (`?`, `&`, `$( )`, backticks, `-`, `_`, `http://`, comma, space,
accent, line break with fake keys, classicube.net itself, no dot, port 99999, too long; suffixes
`_`, too long, empty, accented, with a line break). Relay: 11 port checks (same as game port, 0,
65536, unsubstituted, missing, injected, leading zeros) and real starts with a fake server, fake
`setpriv` and fake `socat`: exact `socat` arguments under `setpriv --pdeathsig TERM`, its stdin is
not AMP's console, the server still replaces the script (`exec`) and gets `/shutdown`, no relay when
unticked, a dying `socat` is reported.

**Not tested yet**: AMP itself (Update, rendering of the checkbox in the Update command line,
`$MaxUsers` / `$RelayPort` on the command line, user list), a real MCGalaxy start under AMP, real
players, real `socat` in the container, the nginx block and the `DOCKER-USER` rule on the host, a
heartbeat received by a real second service.

## Files

| File | Role |
|---|---|
| `classicube.kvp`, `classicube*.json`, `manifest.json` | the AMP template |
| `scripts/installer-classicube.sh` | download and check of MCGalaxy (Update) |
| `scripts/lancer-classicube.sh` | start script (settings → `server.properties` and `authservices.properties`, optional relay, then `exec`) |
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
aucun paquet pour le serveur. Un seul port à ouvrir, **25565 en TCP** (le 2e, 25566, sert au relais facultatif et ne s'ouvre jamais).

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
- **Jouer depuis votre propre page web** (sous-catégorie « Connexion par un autre site », tout est
  désactivé par défaut) :
  - *Service de connexion supplémentaire* : adresse `https://…` de votre site, ajoutée après
    classicube.net dans `HeartbeatURL`. Le serveur lui envoie son heartbeat avec un sel propre ;
    votre site donne à ses membres `mppass = md5(sel + pseudo)`. Seuls lettres, chiffres, `:`, `/`
    et `.` sont acceptés dans l'adresse (limite de MCGalaxy : pas de tiret, `_`, `?`, `=`, `&`).
    Le site doit n'accepter le heartbeat que depuis l'IP du serveur et répondre vide.
  - *Suffixe des pseudos* (`+` par défaut) : ajouté au pseudo des joueurs venus par votre site
    (`Kevin` devient `Kevin+`), avec au moins un `+`, `~` ou `-` pour qu'aucun compte de votre site
    ne puisse prendre le pseudo d'un joueur classicube.net.
  - *Relais pour un proxy web* : un `socat` dans le conteneur reçoit sur le port **25566**
    (« Relais du proxy web ») et renvoie vers `127.0.0.1:25565`, pour que le nginx de la même
    machine (wss://) arrive en local et que le serveur voie la vraie IP (en-tête `X-Real-IP`).
    **Ce port ne doit jamais être ouvert au monde** : règle `DOCKER-USER` dans le README (les ports
    Docker passent avant ufw). Exemple de bloc nginx dans la section *Play from your own web page*.
  - Le template impose aussi `verify-lan-ips = true` : sinon MCGalaxy laisse entrer sans
    vérification toute connexion venue du local ou du réseau Docker, sous n'importe quel pseudo.
  - **Instance existante** : elle n'a ni le port 25566 ni la nouvelle ligne de commande ni les
    nouveaux réglages : il faut **recréer l'instance** (garder le monde par une sauvegarde AMP).
- Avant de pousser : `python verifier.py` doit répondre « Tout est bon. ».
