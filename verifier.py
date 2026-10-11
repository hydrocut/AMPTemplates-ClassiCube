# -*- coding: utf-8 -*-
"""
Contrôle du template avant de le pousser (même rôle que ceux de PokerTH, LMP, Urban Terror).

    python verifier.py

1. tous les JSON se parsent ;
2. le .kvp ne référence que des fichiers présents, le port principal existe et arrive au
   lanceur avec les joueurs maximum, le bloc Console.* / Limits.* est complet, arrêt par
   la commande /shutdown, AppConfigId et id du manifest = UUID neufs ;
3. chaque réglage exposé dans AMP est écrit une fois dans scripts/AMP_reglages-classicube.txt
   (rendu par AMP en reglages-classicube.txt) ET lu par le lanceur avec la bonne clé de
   server.properties, et inversement ; choix des listes = valeurs du code de MCGalaxy ;
4. aller-retour réel : on rend le modèle comme AMP (remplacement brut), on fait tourner le
   vrai lanceur (bash + perl) et on relit properties/server.properties comme MCGalaxy le lit
   (PropertiesFile.cs) : fichier absent, clé existante, clé absente, fichier de MCGalaxy
   complet en CRLF, valeurs avec espaces, &, apostrophe, $( ), backticks, retour à la ligne,
   accents, valeurs invalides, joueurs maximum non remplacé par AMP ; puis lancement d'un
   faux serveur (exec, TERM=dumb, console d'AMP sur son entrée) ;
4b. service de connexion supplémentaire : l'adresse et le suffixe arrivent dans HeartbeatURL
   et properties/authservices.properties (relus comme MCGalaxy : PropertiesFile.cs,
   AuthService.cs, ConfigStringAttribute.Constrain), valeurs piégées refusées ; relais pour
   un proxy web : port validé, socat lancé sous setpriv --pdeathsig avant l'exec du serveur
   (faux setpriv et faux socat), jamais lancé quand la case est décochée ;
5. les fichiers téléchargés à l'Update existent dans scripts/, à l'URL du dépôt du manifest,
   fins de ligne LF, `bash -n`, `perl -c`, aucun {{$...}} ni eval dans les fichiers livrés ;
6. l'installeur, avec un faux curl : bonne adresse (stable / développement / valeur du
   dernier démarrage), contrôle ELF, données du serveur jamais touchées, échec sans dégât ;
7. les regex de console reconnaissent les lignes du serveur (format relevé sur MCGalaxy
   1.9.5.3 : Logger.Log + préfixe « (HH:mm:ss) » de CLI/Program.cs) et pas les autres.
"""
import glob
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ICI = os.path.dirname(os.path.abspath(__file__))
NOM = 'classicube'
MODELE = 'scripts/AMP_reglages-classicube.txt'
LANCEUR = 'scripts/lancer-classicube.sh'
INSTALLEUR = 'scripts/installer-classicube.sh'
soucis = []

# Réglage AMP -> clé de server.properties (None = utilisé seulement par l'Update).
CORRESPONDANCE = {
    'version_dev': None,
    'compilateur': None,                  # Update (forme Mono) + script bash (mono MCGalaxyCLI.exe)
    'liste_publique': 'public',
    'verifier_pseudos': 'verify-names',
    'places_invites': 'max-guests',
    'rang_defaut': 'default-rank',
    'accepter_reglement': 'agree-to-rules-on-entry',
    'theme_carte': 'default-mapgen-theme',
    'filtre_grossieretes': 'profanity-filter',
    'proprietaire_affiche': 'server-owner',
    'message_accueil': 'motd',
    'nom_serveur': 'server-name',
    'relais_web': None,                   # lu par le script bash (socat)
    'service_connexion': 'HeartbeatURL',  # + properties/authservices.properties
    'suffixe_service': None,              # name-suffix de properties/authservices.properties
}
CCNET = 'http://www.classicube.net/heartbeat.jsp'
NOUVEAUX = ('relais_web', 'service_connexion', 'suffixe_service')
# Thèmes enregistrés par MCGalaxy 1.9.5.3 sans droit Admin (SimpleGen, RealisticMapGen,
# ClassicGenerator, fCraftMapGen ; « Random » de fCraft et les thèmes « Advanced » exclus).
THEMES = {'flat', 'classic', 'forest', 'island', 'mountains', 'ocean', 'desert', 'hell', 'archipelago',
          'atoll', 'bay', 'dunes', 'hills', 'ice', 'lake', 'peninsula', 'river', 'streams', 'space',
          'rainbow', 'pixel', 'empty'}
RANGS = {'guest', 'builder', 'advbuilder'}   # Group.cs ; operator et au-dessus : jamais par défaut


def lire(nom, binaire=False):
    chemin = os.path.join(ICI, nom)
    if binaire:
        with open(chemin, 'rb') as f:
            return f.read()
    with io.open(chemin, encoding='utf-8') as f:
        return f.read()


def py(motif):
    # AMP est en C# : (?<nom>...) ; Python veut (?P<nom>...).
    return re.compile(re.sub(r'\(\?<(?=[A-Za-z])', '(?P<', motif))


def est_uuid(v):
    try:
        return str(uuid.UUID(v)) == v.lower()
    except Exception:
        return False


# ── 1. JSON ──────────────────────────────────────────────────────────────────
data = {}
for nom in ('manifest.json', NOM + 'config.json', NOM + 'metaconfig.json', NOM + 'ports.json', NOM + 'updates.json'):
    try:
        data[nom] = json.loads(lire(nom))
        print('ok   %-28s JSON valide' % nom)
    except Exception as e:
        soucis.append('%s : JSON invalide (%s)' % (nom, e))
if soucis:
    print('\n'.join('NON  ' + s for s in soucis))
    sys.exit(1)
config = data[NOM + 'config.json']
updates = data[NOM + 'updates.json']
ports = data[NOM + 'ports.json']
manifest = data['manifest.json']

# ── 2. kvp ───────────────────────────────────────────────────────────────────
kvp = lire(NOM + '.kvp')
if '\r' in kvp:
    soucis.append(NOM + '.kvp : fins de ligne CRLF')
cles = dict(l.split('=', 1) for l in kvp.splitlines() if '=' in l)
for ref in re.findall(r'@IncludeJson\[([^\]]+)\]', kvp):
    if not os.path.isfile(os.path.join(ICI, ref)):
        soucis.append('@IncludeJson[%s] : fichier absent' % ref)
for cle in ('Meta.ConfigManifest', 'Meta.MetaConfigManifest', 'Meta.ConfigRoot'):
    if not os.path.isfile(os.path.join(ICI, cles.get(cle, '?'))):
        soucis.append('%s pointe sur un fichier absent' % cle)
refs = {p['Ref'] for p in ports}
if cles.get('App.PrimaryApplicationPortRef') not in refs:
    soucis.append('PrimaryApplicationPortRef ne correspond à aucun port')
cmd = cles.get('App.CommandLineArgs', '')
if cmd != '"{{$FullBaseDir}}lancer-classicube.sh" {{$%s}} {{$MaxUsers}} {{$RelayPort}}' % cles.get('App.PrimaryApplicationPortRef'):
    soucis.append('ligne de commande inattendue : %s' % cmd)
if [(p['Ref'], p['Port'], p['Protocol']) for p in ports] != [('GamePort', 25565, 'TCP'), ('RelayPort', 25566, 'TCP')]:
    soucis.append('ports attendus : GamePort 25565/TCP puis RelayPort 25566/TCP')
elif 'JAMAIS' not in ports[1]['Description'] or 'X-Real-IP' not in ports[1]['Description'] \
        or 'DOCKER-USER' not in ports[1]['Description'] or ports[1]['Name'] != 'Relais du proxy web':
    soucis.append('RelayPort : nom « Relais du proxy web » et description « JAMAIS ouvert au monde » (X-Real-IP, DOCKER-USER) attendus')
print('ok   ports                        %s' % ', '.join('%s %s/%s' % (p['Ref'], p['Port'], p['Protocol']) for p in ports))
ATTENDUES = ['App.SupportsUniversalSleep', 'App.WakeupMode', 'App.ApplicationReadyMode', 'Console.FilterMatchRegex',
             'Console.FilterMatchReplacement', 'Console.ThrowawayMessageRegex', 'Console.AppReadyRegex',
             'Console.UserJoinRegex', 'Console.UserLeaveRegex', 'Console.UserChatRegex', 'Console.UpdateAvailableRegex',
             'Console.PreConnectRegex', 'Console.ConnectIPRegex', 'Console.MetricsRegex', 'Console.HideFromConsoleRegex',
             'Console.SuppressLogAtStart', 'Console.UserActions', 'Limits.SleepMode', 'Limits.SleepOnStart',
             'Limits.SleepDelayMinutes', 'Limits.DozeDelay', 'Limits.AutoRetryCount', 'Limits.SleepStartThresholdSeconds']
absentes = [c for c in ATTENDUES if c not in cles]
if absentes:
    soucis.append('clés absentes du .kvp : ' + ', '.join(absentes))
else:
    print('ok   kvp complet                  les %d clés Console/Limits sont là' % len(ATTENDUES))
if cles.get('App.ApplicationReadyMode') != 'RegexMatch' or not cles.get('Console.AppReadyRegex'):
    soucis.append('RegexMatch avec une AppReadyRegex non vide attendue (sinon l’instance n’est jamais prête)')
if cles.get('Console.UserChatRegex'):
    soucis.append('pas de UserChatRegex : le format du chat n’est pas sûr (faux joueurs)')
if (cles.get('App.ExitMethod'), cles.get('App.ExitString')) != ('String', '/shutdown'):
    soucis.append('arrêt attendu : ExitMethod=String, ExitString=/shutdown')
if not cles.get('App.ExitTimeout', '0').isdigit() or int(cles['App.ExitTimeout']) < 30:
    soucis.append('ExitTimeout trop court : /shutdown attend 10 s puis enregistre les cartes')
if (cles.get('App.HasWriteableConsole'), cles.get('App.AdminMethod')) != ('True', 'STDIO'):
    soucis.append('console d’AMP sur l’entrée de MCGalaxy : HasWriteableConsole=True, AdminMethod=STDIO')
if cles.get('Meta.URL') != manifest['url']:
    soucis.append('Meta.URL et manifest.json ne désignent pas le même dépôt')
if cles.get('Meta.SpecificDockerImage') != 'cubecoders/ampbase:debian' or cles.get('Meta.ContainerPolicy') != 'Required':
    soucis.append('conteneur cubecoders/ampbase:debian obligatoire')
paquets = json.loads(cles.get('Meta.ExtraContainerPackages', '[]'))
PAQUETS = ['ca-certificates', 'curl', 'libmono-system-data4.0-cil', 'libmono-system-runtime-serialization4.0-cil',
           'libsqlite3-0', 'mono-mcs', 'mono-runtime', 'socat']
if sorted(paquets) != PAQUETS:
    soucis.append('ExtraContainerPackages : curl, ca-certificates (Update), socat (relais) et Mono (compilateur) seulement : %r' % paquets)
# Identifiants neufs : jamais celui d'un autre template TeamKit.
if not est_uuid(cles.get('Meta.AppConfigId', '')) or not est_uuid(manifest.get('id', '')):
    soucis.append('Meta.AppConfigId et l’id du manifest doivent être des UUID')
autres_ids = set()
for autre in glob.glob(os.path.join(ICI, '..', 'AMPTemplates-*')):
    if os.path.samefile(autre, ICI):
        continue
    for f in glob.glob(os.path.join(autre, '*.kvp')) + glob.glob(os.path.join(autre, 'manifest.json')):
        with io.open(f, encoding='utf-8', errors='replace') as h:
            autres_ids.update(re.findall(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', h.read().lower()))
if cles.get('Meta.AppConfigId', '').lower() in autres_ids or manifest.get('id', '').lower() in autres_ids:
    soucis.append('AppConfigId ou id du manifest déjà utilisé par un autre template')
print('ok   identifiants                 UUID neufs (%d identifiants des autres templates comparés)' % len(autres_ids))

# ── 3. réglages ↔ modèle ↔ lanceur ───────────────────────────────────────────
modele = lire(MODELE)
lanceur = lire(LANCEUR)
m = re.search(r"^PERL_REGLAGES='\n(.*?)\n'$", lanceur, re.S | re.M)
perl = m.group(1) if m else ''
if not perl or "'" in perl:
    soucis.append('code perl du lanceur introuvable, ou avec une apostrophe (il est entre apostrophes pour bash)')
table = dict(re.findall(r'^\s+([a-z_]+)\s+=>\s+\[(undef|"[A-Za-z-]+")', perl, re.M))
table = {k: (None if v == 'undef' else v.strip('"')) for k, v in table.items()}
dans_modele = re.findall(r'\{\{([^}]*)\}\}', modele)
params = {}
for c in config:
    f, p = c['FieldName'], c['ParamFieldName']
    if f == '$MaxUsers':
        if c['DefaultValue'] != cles.get('App.MaxUsers') or (c.get('MinValue'), c.get('MaxValue')) != ('1', '256'):
            soucis.append('Joueurs maximum : défaut = App.MaxUsers (%s) et limites 1 à 256 attendus' % cles.get('App.MaxUsers'))
        continue
    if p in params:
        soucis.append('réglage en double : %s' % p)
    params[p] = c
    if f != p:
        soucis.append('%s : FieldName et ParamFieldName différents' % p)
    if dans_modele.count(p) != 1 or not re.search(r'^%s=\{\{%s\}\}$' % (p, p), modele, re.M):
        soucis.append('%s doit s’écrire %s={{%s}}, une seule fois, seul sur sa ligne' % (p, p, p))
    if p not in CORRESPONDANCE:
        soucis.append('%s : réglage inconnu de verifier.py' % p)
    elif table.get(p, '?') != CORRESPONDANCE[p]:
        soucis.append('le lanceur écrit %s dans %r au lieu de %r' % (p, table.get(p, '(rien)'), CORRESPONDANCE[p]))
    if c['InputType'] == 'enum' and str(c.get('DefaultValue')) not in c.get('EnumValues', {}):
        soucis.append('%s : valeur par défaut absente des choix' % p)
    if c['InputType'] == 'checkbox' and (c['EnumValues'] != {'False': 'false', 'True': 'true'} or c['DefaultValue'] not in ('true', 'false')):
        soucis.append('%s : case à cocher attendue en true/false' % p)
    if c.get('IncludeInCommandLine') is not False:
        soucis.append('%s : IncludeInCommandLine doit être false (lu dans le fichier rendu)' % p)
if set(CORRESPONDANCE) - set(params):
    soucis.append('réglages attendus absents de la configuration : %s' % ', '.join(sorted(set(CORRESPONDANCE) - set(params))))
if set(table) != set(CORRESPONDANCE):
    soucis.append('la table du lanceur ne correspond pas aux réglages : %s' % sorted(set(table) ^ set(CORRESPONDANCE)))
orphelins = set(dans_modele) - set(params)
if orphelins:
    soucis.append('{{...}} sans réglage dans AMP (ou variable AMP non remplacée dans un fichier) : %s' % ', '.join(sorted(orphelins)))
for l in modele.splitlines():
    if l.startswith('#') and '{{' in l:
        soucis.append('{{ dans un commentaire du modèle : AMP le remplacerait')
if set(params['theme_carte']['EnumValues']) != THEMES or not all(t in perl for t in THEMES):
    soucis.append('thèmes : la liste doit être celle de MCGalaxy 1.9.5.3 (AMP et lanceur)')
if set(params['rang_defaut']['EnumValues']) != RANGS:
    soucis.append('rang par défaut : guest, builder, advbuilder seulement')
if params['verifier_pseudos']['DefaultValue'] != 'true' or 'N\'IMPORTE QUI' not in params['verifier_pseudos']['Description']:
    soucis.append('vérification des pseudos : cochée par défaut, avec l’avertissement')
if params['version_dev']['DefaultValue'] != 'false' or params['liste_publique']['DefaultValue'] != 'true'         or params['compilateur']['DefaultValue'] != 'false':
    soucis.append('défauts attendus : version stable, liste publique, serveur autonome (compilateur décoché)')
lignes_modele = [l.split('=', 1)[0] for l in modele.splitlines() if '=' in l and not l.startswith('#')]
for p in NOUVEAUX:
    c = params.get(p, {})
    if not c.get('Subcategory', '').startswith('Connexion par un autre site:') or c.get('Required', False):
        soucis.append('%s : sous-catégorie « Connexion par un autre site », jamais obligatoire' % p)
    # Avant tout champ texte libre dans le modèle : une ligne « cle=... » glissée dans un
    # texte sur plusieurs lignes ne peut pas passer avant la vraie (la première compte).
    if p in lignes_modele and any(lignes_modele.index(p) > lignes_modele.index(x)
                                  for x in params if params[x]['InputType'] == 'text' and x not in NOUVEAUX):
        soucis.append('%s doit venir avant les champs texte dans le modèle' % p)
if (params.get('service_connexion', {}).get('DefaultValue'), params.get('suffixe_service', {}).get('DefaultValue'),
        params.get('relais_web', {}).get('DefaultValue')) != ('', '+', 'false'):
    soucis.append('défauts attendus : service vide, suffixe « + », relais décoché')
if 'JAMAIS' not in params.get('relais_web', {}).get('Description', ''):
    soucis.append('relais_web : dire que le port ne doit JAMAIS être ouvert au monde')
readme = lire('README.md')
for besoin in ('## Play from your own web page', 'proxy_http_version 1.1;', 'proxy_set_header Upgrade $http_upgrade;',
               'proxy_set_header Connection "upgrade";', 'proxy_set_header X-Real-IP $remote_addr;',
               'proxy_read_timeout 1h;', 'proxy_pass http://127.0.0.1:25566;', 'DOCKER-USER', 'never** be opened',
               'Recreate the\ninstance', 'recréer l\'instance', 'verify-lan-ips = true'):
    if besoin not in readme:
        soucis.append('README : %r absent (web page, nginx, pare-feu, instance à recréer)' % besoin)
if '/rank' not in params['proprietaire_affiche']['Description'] or '/rank' not in cles.get('Meta.Description', ''):
    soucis.append('expliquer « /rank <pseudo> owner » (champ propriétaire et description du template)')
meta = data[NOM + 'metaconfig.json'][0]
racine = cles['App.RootDir'].strip('./').strip('/')
if meta.get('ConfigType') != 'template' or meta.get('ConfigFileTemplate') != racine + '/AMP_reglages-classicube.txt':
    soucis.append('metaconfig : ConfigFileTemplate devrait être %s/AMP_reglages-classicube.txt' % racine)
if meta.get('ConfigFile') != 'reglages-classicube.txt' or 'REGLAGES="$ICI/reglages-classicube.txt"' not in lanceur:
    soucis.append('le fichier rendu par AMP (ConfigFile) n’est pas celui que lit le lanceur')
print('ok   correspondance               %d réglages : AMP -> %s -> server.properties' % (len(params) + 1, MODELE))


# ── 4. aller-retour réel avec le lanceur ─────────────────────────────────────
def rendre(valeurs):
    t = modele
    for p, v in valeurs.items():
        t = t.replace('{{%s}}' % p, v)
    return t


def lire_props(chemin):
    """Lecture comme MCGalaxy (PropertiesFile.Read + ConfigElement.Parse) : commentaires #,
    premier '=', clé et valeur rognées, clé sans casse, la dernière ligne l'emporte."""
    vals = {}
    with io.open(chemin, encoding='utf-8', newline='') as f:
        for ligne in f.read().splitlines():
            if not ligne or ligne[0] == '#' or '=' not in ligne:
                continue
            k, v = ligne.split('=', 1)
            vals[k.strip().lower()] = v.strip()
    return vals


bash = shutil.which('bash')
defauts = {p: str(c.get('DefaultValue', '')) for p, c in params.items()}
DEF_PROPS = {'public': 'true', 'verify-names': 'true', 'verify-lan-ips': 'true', 'heartbeaturl': CCNET,
             'max-guests': '30', 'default-rank': 'guest',
             'agree-to-rules-on-entry': 'false', 'default-mapgen-theme': 'flat', 'profanity-filter': 'false',
             'server-owner': 'TeamKit', 'motd': defauts['message_accueil'],
             'server-name': '[FR] TeamKit - ClassiCube', 'port': '25565', 'max-players': '32'}
# Un server.properties tel que MCGalaxy l'écrit (extrait), en CRLF, dernière ligne sans fin.
MCG = ('# Edit the settings below to modify how your server operates.\r\n#\r\n'
       '#   server-name                   = The name which displays on classicube.net\r\n'
       '#   motd                          = The message which displays when a player connects\r\n'
       '#   port                          = The port to list for connections on\r\n'
       '\r\n# Server settings\r\nserver-name = Ancien nom\r\nMotd = ancien message\r\nmax-players = 16\r\n'
       'max-guests = 14\r\nport = 25565\r\npublic = false\r\nverify-names = true\r\ndefault-rank = guest\r\n'
       'server-owner = the owner\r\nirc = false\r\nirc-nick = ForgeBot\r\nHeartbeatURL = http://www.classicube.net/heartbeat.jsp\r\n'
       'public=false\r\nport-extra = 7\r\npublic-note = x\r\ncheck-updates = false\r\nlisten-ip = 0.0.0.0')
PIRATE = '$(touch pirate1) `touch pirate2` ; touch pirate3 | $HOME'
ESSAIS = [
    # (nom, valeurs changées (None = pas de fichier rendu), server.properties de départ, args, attendu)
    ('fichier absent, défauts', {}, None, ['25565', '32'], dict(DEF_PROPS)),
    ('pas de reglages-classicube.txt', None, None, ['25570', '20'], {'port': '25570', 'max-players': '20'}),
    ('fichier MCGalaxy existant (CRLF, Motd, doublon)', {}, MCG, ['25565', '32'], dict(DEF_PROPS, **{'irc-nick': 'ForgeBot', 'listen-ip': '0.0.0.0', 'port-extra': '7', 'public-note': 'x'})),
    ('valeurs piégées', {'proprietaire_affiche': "L'équipe\t& co\r" + PIRATE,
                         'message_accueil': '  Salut à tous & bienvenue !\nmax-players=999\nport=1',
                         'nom_serveur': "Serveur «Kévin» d'Œuvre · No 1 – test ☃ & $(id)"},
     MCG, ['25565', '32'],
     {'server-owner': "L'équipe & co " + PIRATE, 'motd': 'Salut à tous & bienvenue ! max-players=999 port=1',
      'server-name': 'Serveur "Kevin" d\'OEuvre - No 1 - test & $(id)', 'max-players': '32', 'port': '25565'}),
    ('valeurs invalides : valeurs actuelles gardées', {'liste_publique': 'oui', 'places_invites': 'abc', 'rang_defaut': 'owner',
                                                       'theme_carte': 'hell2', 'verifier_pseudos': '1', 'nom_serveur': '☃☃'},
     MCG, ['25565', '32'], {'public': 'false', 'max-guests': '14', 'default-rank': 'guest',
                            'default-mapgen-theme': None, 'verify-names': 'true', 'server-name': '[FR] TeamKit - ClassiCube'}),
    ('choix en majuscules, invités > joueurs', {'rang_defaut': 'AdvBuilder', 'theme_carte': 'Forest', 'places_invites': '200',
                                                'verifier_pseudos': 'False', 'liste_publique': 'FALSE', 'version_dev': 'true'},
     None, ['25565', '50'], {'default-rank': 'advbuilder', 'default-mapgen-theme': 'forest', 'max-guests': '50',
                             'max-players': '50', 'verify-names': 'false', 'public': 'false'}),
    ('clé absente du fichier existant', {}, 'server-name = Ancien\nirc = true\n', ['25565', '32'],
     dict(DEF_PROPS, irc='true')),
    ('MaxUsers non remplacé, GenericModule.kvp', {}, None, ['25565', '{{$MaxUsers}}'], {'max-players': '48'}),
    ('MaxUsers non remplacé, sans kvp', {}, None, ['25565', '{{$MaxUsers}}', 'sans-kvp'], {'max-players': '32'}),
    ('MaxUsers hors limites', {}, None, ['25565', '300'], {'max-players': '32'}),
]
n = 0
if bash:
    for nom_essai, valeurs, depart, args, attendu in ESSAIS:
        dossier = tempfile.mkdtemp(prefix='tk-classicube-')
        try:
            inst = os.path.join(dossier, 'classicube')
            os.makedirs(inst)
            with io.open(os.path.join(inst, 'lancer-classicube.sh'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(lanceur)
            if valeurs is not None:
                vals = dict(defauts)
                vals.update(valeurs)
                with io.open(os.path.join(inst, 'reglages-classicube.txt'), 'w', encoding='utf-8', newline='\n') as f:
                    f.write(rendre(vals))
            if depart is not None:
                os.makedirs(os.path.join(inst, 'properties'))
                with io.open(os.path.join(inst, 'properties', 'server.properties'), 'w', encoding='utf-8', newline='') as f:
                    f.write(depart)
            if 'sans-kvp' not in args:
                with io.open(os.path.join(dossier, 'GenericModule.kvp'), 'w', encoding='utf-8', newline='\r\n') as f:
                    f.write('App.DisplayName=ClassiCube\nApp.MaxUsers=48\n')
            env = dict(os.environ, TK_ESSAI_REGLAGES='1')
            r = subprocess.run([bash, os.path.join(inst, 'lancer-classicube.sh')] + [a for a in args if a != 'sans-kvp'],
                               capture_output=True, timeout=60, env=env, cwd=dossier)
            sortie = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
            n += 1
            if r.returncode != 0:
                soucis.append('aller-retour « %s » : code %d : %s' % (nom_essai, r.returncode, sortie.strip()))
                continue
            chemin = os.path.join(inst, 'properties', 'server.properties')
            props = lire_props(chemin)
            for cle, v in attendu.items():
                if props.get(cle) != v:
                    soucis.append('aller-retour « %s » : %s = %r au lieu de %r' % (nom_essai, cle, props.get(cle), v))
            for p in glob.glob(os.path.join(dossier, '**', 'pirate*'), recursive=True):
                soucis.append('aller-retour « %s » : une valeur a été exécutée par le shell (%s)' % (nom_essai, p))
            brut = io.open(chemin, encoding='utf-8', newline='').read()
            if depart is not None:
                # Les lignes qui ne sont pas à nous (commentaires, irc, listen-ip...) sont intactes,
                # fins de ligne comprises.
                nos_cles = set(DEF_PROPS)
                for l in depart.splitlines(True):
                    k = l.split('=', 1)[0].strip().lower() if '=' in l and not l.startswith('#') else None
                    if k not in nos_cles and l.rstrip('\r\n') and l.rstrip('\r\n') not in brut:
                        soucis.append('aller-retour « %s » : ligne perdue : %r' % (nom_essai, l))
                    if k not in nos_cles and l.endswith('\r\n') and l not in brut:
                        soucis.append('aller-retour « %s » : fin de ligne changée : %r' % (nom_essai, l))
            # Une seule ligne par valeur : un retour à la ligne ne crée jamais une autre clé.
            for ligne in brut.splitlines():
                if ligne.lower().startswith('max-players') and ligne.split('=', 1)[1].strip() == '999':
                    soucis.append('aller-retour « %s » : un retour à la ligne a injecté max-players' % nom_essai)
            if any(ord(ch) > 126 for ch in props.get('server-name', '')):
                soucis.append('aller-retour « %s » : server-name non ASCII (MCGalaxy le jetterait)' % nom_essai)
        except Exception as e:
            soucis.append('aller-retour « %s » : %s' % (nom_essai, e))
        finally:
            shutil.rmtree(dossier, ignore_errors=True)
    print('ok   aller-retour réel            %d rendus AMP -> lanceur -> server.properties relu comme MCGalaxy' % n)

    # Lancement d'un faux serveur : exec, TERM=dumb, entrée = console d'AMP, réglages écrits avant.
    dossier = tempfile.mkdtemp(prefix='tk-classicube-')
    try:
        with io.open(os.path.join(dossier, 'lancer-classicube.sh'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(lanceur)
        with io.open(os.path.join(dossier, 'MCGalaxy'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('#!/bin/bash\nIFS= read -r cmd\necho "faux:$TERM:$(cat properties/server.properties | grep -c "^port = 25599$"):$cmd:$$"\n')
        with io.open(os.path.join(dossier, 'reglages-classicube.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(rendre(defauts))
        r = subprocess.run([bash, '-c', 'echo "lanceur:$$"; exec bash "$0" 25599 16', os.path.join(dossier, 'lancer-classicube.sh')],
                           input=b'/shutdown\n', capture_output=True, timeout=60, cwd=dossier)
        sortie = r.stdout.decode('utf-8', 'replace')
        mf = re.search(r'faux:([^:]*):(\d):([^:]*):(\d+)', sortie)
        ml = re.search(r'lanceur:(\d+)', sortie)
        if r.returncode or not mf or mf.group(1) != 'dumb' or mf.group(2) != '1' or mf.group(3) != '/shutdown':
            soucis.append('lancement : le faux serveur n’a pas reçu TERM=dumb, le port, ou /shutdown sur son entrée : %r' % sortie)
        elif not ml or ml.group(1) != mf.group(4):
            soucis.append('lancement : le serveur doit remplacer le lanceur (exec), pas tourner à côté')
        else:
            print('ok   lancement                    exec, TERM=dumb, réglages écrits avant, /shutdown arrive au serveur')
        os.remove(os.path.join(dossier, 'MCGalaxy'))
        r = subprocess.run([bash, os.path.join(dossier, 'lancer-classicube.sh'), '25565', '32'], capture_output=True, timeout=60)
        if r.returncode != 1 or b'Lance Update' not in r.stdout:
            soucis.append('sans serveur installé, le lanceur doit s’arrêter en demandant un Update')
        r = subprocess.run([bash, os.path.join(dossier, 'lancer-classicube.sh'), '99999', '32'], capture_output=True, timeout=60,
                           env=dict(os.environ, TK_ESSAI_REGLAGES='1'))
        if r.returncode != 1:
            soucis.append('port invalide accepté')
    finally:
        shutil.rmtree(dossier, ignore_errors=True)
else:
    print('--   aller-retour réel            pas de bash ici, non vérifié')

# ── 4b. service de connexion supplémentaire et relais pour un proxy web ──────
# HeartbeatURL n'accepte que lettres, chiffres et : / . , (ServerConfig.cs, 1.9.5.3) :
# MCGalaxy remet l'adresse de classicube.net seule au moindre autre caractère.
PERMIS_HB = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:/.,')
TK = 'https://teamkit.fr/classicube/heartbeat'


def lire_auth(chemin):
    """Lecture comme MCGalaxy (AuthService.UpdateList + PropertiesFile.Read) : lignes vides
    et # ignorées, premier '=', clé et valeur rognées ; une ligne URL ouvre un service
    (GetOrCreate : même adresse sans casse = même service)."""
    services, cur = {}, None
    with io.open(chemin, encoding='utf-8', newline='') as f:
        for ligne in f.read().split('\n'):
            if not ligne or ligne[0] == '#' or '=' not in ligne:
                continue
            k, v = ligne.split('=', 1)
            k, v = k.strip().lower(), v.strip()
            if k == 'url':
                cur = services.setdefault(v.lower(), {'url': v, 'name-suffix': '', 'skin-prefix': '', 'mojang-auth': 'False'})
            elif cur is not None and k in ('name-suffix', 'skin-prefix', 'mojang-auth'):
                cur[k] = v
    return list(services.values())


def lancer(valeurs, args, depart=None, depart_auth=None, essai=True, outils=None, env_plus=None, fichiers=None):
    """Lance le vrai lanceur dans un dossier jetable ; valeurs=None : pas de fichier rendu."""
    dossier = tempfile.mkdtemp(prefix='tk-classicube-')
    inst = os.path.join(dossier, 'classicube')
    os.makedirs(os.path.join(inst, 'properties'))
    with io.open(os.path.join(inst, 'lancer-classicube.sh'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(lanceur)
    if valeurs is not None:
        vals = dict(defauts)
        vals.update(valeurs)
        with io.open(os.path.join(inst, 'reglages-classicube.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(rendre(vals))
    if depart is not None:
        with io.open(os.path.join(inst, 'properties', 'server.properties'), 'w', encoding='utf-8', newline='') as f:
            f.write(depart)
    if depart_auth is not None:
        with io.open(os.path.join(inst, 'properties', 'authservices.properties'), 'w', encoding='utf-8', newline='') as f:
            f.write(depart_auth)
    for nom_f, contenu in (fichiers or {}).items():
        with io.open(os.path.join(inst, nom_f), 'w', encoding='utf-8', newline='\n') as f:
            f.write(contenu)
    env = dict(os.environ)
    env.pop('TK_ESSAI_REGLAGES', None)
    if essai:
        env['TK_ESSAI_REGLAGES'] = '1'
    if outils:
        env['PATH'] = outils + os.pathsep + env.get('PATH', '')
    env.update(env_plus or {})
    r = subprocess.run([bash, '-c', 'echo "lanceur:$$"; exec bash "$0" "$@"', os.path.join(inst, 'lancer-classicube.sh')] + args,
                       input=b'/shutdown\n', capture_output=True, timeout=60, env=env, cwd=dossier)
    return dossier, inst, r.returncode, r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')


# Un authservices.properties laissé par MCGalaxy, avec un ancien service et un réglage à la main.
AUTH_MCG = ('# Authentication services configuration\n\nURL = http://www.classicube.net/heartbeat.jsp\nname-suffix = \n'
            'skin-prefix = \nmojang-auth = False\n\nURL = https://ancien.example/hb\nname-suffix = ~\nskin-prefix = x\n'
            'mojang-auth = True\n\n')
REFUS = 'service de connexion supplementaire IGNORE'
ESSAIS_SERVICE = [
    # (nom, valeurs, server.properties de départ, authservices de départ, HeartbeatURL attendu,
    #  services attendus [(adresse, suffixe)] (None = fichier jamais écrit), texte attendu dans la console)
    ('service vide (défaut)', {}, None, None, CCNET, [(CCNET, '')], None),
    ('service TeamKit, suffixe +', {'service_connexion': TK}, None, None,
     CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'pseudos de ce service suivis de "+"'),
    ('port, sous-domaine, .php, suffixe ~tk', {'service_connexion': 'https://Play.TeamKit.fr:8443/cc/hb.php', 'suffixe_service': '~tk'},
     None, None, CCNET + ',https://Play.TeamKit.fr:8443/cc/hb.php', [(CCNET, ''), ('https://Play.TeamKit.fr:8443/cc/hb.php', '~tk')], None),
    ('espaces autour, CRLF de MCGalaxy, ancien service retiré', {'service_connexion': '  ' + TK + ' \t', 'suffixe_service': ' - '},
     MCG, AUTH_MCG, CCNET + ',' + TK, [(CCNET, ''), (TK, '-')], None),
    ('service vidé : l’ancien disparaît', {'service_connexion': ''}, MCG.replace(CCNET, CCNET + ',' + TK), AUTH_MCG,
     CCNET, [(CCNET, '')], None),
    ('ancienne instance : variables laissées par AMP', {p: '{{%s}}' % p for p in NOUVEAUX},
     'HeartbeatURL = ' + CCNET + ',' + TK + '\n', AUTH_MCG, CCNET + ',' + TK, None, 'reglages absents'),
    ('pas de reglages-classicube.txt : rien touché', None, 'HeartbeatURL = ' + CCNET + ',' + TK + '\n', AUTH_MCG,
     CCNET + ',' + TK, None, None),
    ('piégé : ? & $( )', {'service_connexion': 'https://teamkit.fr/hb?x=1&y=$(touch pirate1)`touch pirate2`'}, MCG, None,
     CCNET, [(CCNET, '')], REFUS),
    ('tiret dans le nom de domaine', {'service_connexion': 'https://team-kit.fr/hb'}, None, None, CCNET, [(CCNET, '')], 'caractere "-" interdit'),
    ('soulignement', {'service_connexion': 'https://teamkit.fr/classicube_hb'}, None, None, CCNET, [(CCNET, '')], 'caractere "_" interdit'),
    ('http:// au lieu de https://', {'service_connexion': 'http://teamkit.fr/hb'}, None, None, CCNET, [(CCNET, '')], 'commencer par https://'),
    ('deux adresses (virgule)', {'service_connexion': TK + ',https://autre.example/hb'}, None, None, CCNET, [(CCNET, '')], 'caractere "," interdit'),
    ('espace au milieu', {'service_connexion': 'https://teamkit.fr/a b'}, None, None, CCNET, [(CCNET, '')], 'caractere espace interdit'),
    ('accent', {'service_connexion': 'https://téamkit.fr/hb'}, None, None, CCNET, [(CCNET, '')], 'U+00E9'),
    ('retour à la ligne + fausse clé', {'service_connexion': TK + '\nHeartbeatURL=https://pirate.example/hb\nverify-names=false'},
     None, None, CCNET, [(CCNET, '')], REFUS),
    ('classicube.net en double', {'service_connexion': 'https://www.classicube.net/heartbeat.jsp'}, None, None, CCNET, [(CCNET, '')],
     'deja le service de classicube.net'),
    ('domaine sans point', {'service_connexion': 'https://localhost/hb'}, None, None, CCNET, [(CCNET, '')], 'mal formee'),
    ('port 99999', {'service_connexion': 'https://teamkit.fr:99999/hb'}, None, None, CCNET, [(CCNET, '')], 'mal formee'),
    ('trop longue', {'service_connexion': 'https://teamkit.fr/' + 'a' * 200}, None, None, CCNET, [(CCNET, '')], 'trop longue'),
    ('suffixe _ (pseudo classicube.net possible)', {'service_connexion': TK, 'suffixe_service': '_'}, None, None,
     CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'suffixe des pseudos "_" refuse'),
    ('suffixe trop long', {'service_connexion': TK, 'suffixe_service': '+abc'}, None, None, CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'refuse'),
    ('suffixe vide', {'service_connexion': TK, 'suffixe_service': ''}, None, None, CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'refuse'),
    ('suffixe accentué', {'service_connexion': TK, 'suffixe_service': 'é+'}, None, None, CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'refuse'),
    ('suffixe piégé', {'service_connexion': TK, 'suffixe_service': '+\nverify-names=false\n$(touch pirate3)'}, None, None,
     CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'refuse'),
    ('vérification coupée : avertissement', {'service_connexion': TK, 'verifier_pseudos': 'false'}, None, None,
     CCNET + ',' + TK, [(CCNET, ''), (TK, '+')], 'le service supplementaire ne sert a rien'),
]
if bash:
    n = 0
    for nom_essai, valeurs, depart, depart_auth, hb, blocs, message in ESSAIS_SERVICE:
        dossier = None
        try:
            dossier, inst, code, sortie = lancer(valeurs, ['25565', '32', '25566'], depart, depart_auth)
            n += 1
            if code != 0:
                soucis.append('service « %s » : code %d : %s' % (nom_essai, code, sortie.strip()))
                continue
            chemin = os.path.join(inst, 'properties', 'server.properties')
            props = lire_props(chemin)
            brut = io.open(chemin, encoding='utf-8', newline='').read()
            if props.get('heartbeaturl') != hb:
                soucis.append('service « %s » : HeartbeatURL = %r au lieu de %r' % (nom_essai, props.get('heartbeaturl'), hb))
            if sum(1 for l in brut.splitlines() if l.strip().lower().startswith('heartbeaturl')) != 1:
                soucis.append('service « %s » : une seule ligne HeartbeatURL attendue' % nom_essai)
            if set(props.get('heartbeaturl', '')) - PERMIS_HB:
                soucis.append('service « %s » : HeartbeatURL contient un caractère que MCGalaxy refuse' % nom_essai)
            if props.get('verify-names') == 'false' and valeurs and valeurs.get('verifier_pseudos') != 'false':
                soucis.append('service « %s » : verify-names coupé par une valeur glissée' % nom_essai)
            auth = os.path.join(inst, 'properties', 'authservices.properties')
            if blocs is None:
                if depart_auth is not None and io.open(auth, encoding='utf-8', newline='').read() != depart_auth:
                    soucis.append('service « %s » : authservices.properties modifié sans réglages' % nom_essai)
            elif not os.path.isfile(auth):
                soucis.append('service « %s » : authservices.properties absent' % nom_essai)
            else:
                texte = io.open(auth, encoding='utf-8', newline='').read()
                lus = lire_auth(auth)
                if [(s['url'], s['name-suffix']) for s in lus] != blocs:
                    soucis.append('service « %s » : authservices = %r au lieu de %r' % (nom_essai, [(s['url'], s['name-suffix']) for s in lus], blocs))
                if any((s['skin-prefix'], s['mojang-auth']) != ('', 'False') for s in lus):
                    soucis.append('service « %s » : skin-prefix vide et mojang-auth = False attendus' % nom_essai)
                if {s['url'].lower() for s in lus} != {u.lower() for u in props.get('heartbeaturl', '').split(',')}:
                    soucis.append('service « %s » : adresses de HeartbeatURL et de authservices.properties différentes' % nom_essai)
                if not texte.startswith('# Authentication services configuration\n') or '\r' in texte \
                        or '#mojang-auth = boolean' not in texte or "Mojang's" not in texte:
                    soucis.append('service « %s » : en-tête de MCGalaxy attendu, fins de ligne LF' % nom_essai)
                if os.path.exists(auth + '.tmp'):
                    soucis.append('service « %s » : fichier temporaire laissé' % nom_essai)
            if message and message not in sortie:
                soucis.append('service « %s » : message attendu « %s » absent : %r' % (nom_essai, message, sortie))
            if not message and REFUS in sortie:
                soucis.append('service « %s » : refusé à tort : %r' % (nom_essai, sortie))
            for p in glob.glob(os.path.join(dossier, '**', 'pirate*'), recursive=True):
                soucis.append('service « %s » : une valeur a été exécutée par le shell (%s)' % (nom_essai, p))
        except Exception as e:
            soucis.append('service « %s » : %s' % (nom_essai, e))
        finally:
            if dossier:
                shutil.rmtree(dossier, ignore_errors=True)
    print('ok   service de connexion         %d essais : HeartbeatURL + authservices.properties relus comme MCGalaxy' % n)

    # Relais : contrôle du port (mode essai, socat jamais lancé).
    PAS_ARRIVE = "n'est pas arrive sur la ligne de commande"
    ESSAIS_RELAIS = [
        ('coché, bon port', 'true', ['25565', '32', '25566'], None),
        ('coché, port du jeu', 'true', ['25565', '32', '25565'], 'est celui du jeu'),
        ('coché, port du jeu écrit 08080', 'true', ['8080', '32', '08080'], 'est celui du jeu'),
        ('coché, port 0', 'true', ['25565', '32', '0'], PAS_ARRIVE),
        ('coché, port 65536', 'true', ['25565', '32', '65536'], PAS_ARRIVE),
        ('coché, RelayPort non remplacé', 'true', ['25565', '32', '{{$RelayPort}}'], PAS_ARRIVE),
        ('coché, instance ancienne (pas de 3e argument)', 'true', ['25565', '32'], PAS_ARRIVE),
        ('coché, port piégé', 'true', ['25565', '32', '25566;touch pirate5'], PAS_ARRIVE),
        ('coché en majuscules', 'True', ['25565', '32', '25565'], 'est celui du jeu'),
        ('décoché, port absent', 'false', ['25565', '32'], None),
        ('valeur piégée', '$(touch pirate6)', ['25565', '32', '25565'], None),
    ]
    for nom_essai, valeur, args, message in ESSAIS_RELAIS:
        dossier = None
        try:
            dossier, inst, code, sortie = lancer({'relais_web': valeur}, args)
            if code != 0:
                soucis.append('relais « %s » : code %d : %s' % (nom_essai, code, sortie))
            if message and message not in sortie:
                soucis.append('relais « %s » : message attendu « %s » absent : %r' % (nom_essai, message, sortie))
            if not message and 'relais pour un proxy web' in sortie:
                soucis.append('relais « %s » : message inattendu : %r' % (nom_essai, sortie))
            for p in glob.glob(os.path.join(dossier, '**', 'pirate*'), recursive=True):
                soucis.append('relais « %s » : une valeur a été exécutée par le shell (%s)' % (nom_essai, p))
        finally:
            if dossier:
                shutil.rmtree(dossier, ignore_errors=True)

    # Relais : vrai démarrage avec un faux serveur, un faux setpriv et un faux socat.
    def outils_relais(dossier, avec_socat=True):
        outils = os.path.join(dossier, 'outils')
        os.makedirs(outils)
        scripts = {'setpriv': '#!/bin/bash\nprintf "%s\\n" "$@" > "$TK_JOURNAL_RELAIS.setpriv"\n'
                              'while [ "$1" != "--" ]; do shift; done\nshift\nexec "$@"\n'}
        if avec_socat:
            # L'entrée du relais doit être /dev/null : s'il lisait la console d'AMP, il
            # volerait les commandes (/shutdown) du serveur.
            scripts['socat'] = ('#!/bin/bash\nprintf "%s\\n" "$@" > "$TK_JOURNAL_RELAIS.socat"\n'
                                '[ "$TK_SOCAT" = meurt ] && exit 1\n'
                                'if IFS= read -r x; then echo "$x" > "$TK_JOURNAL_RELAIS.entree"; fi\n'
                                'cd / && exec sleep 3 </dev/null >/dev/null 2>&1\n')
        for nom_outil, contenu in scripts.items():
            with io.open(os.path.join(outils, nom_outil), 'w', encoding='utf-8', newline='\n') as f:
                f.write(contenu)
            os.chmod(os.path.join(outils, nom_outil), 0o755)
        return outils

    def demarrer(relais, args, socat='vit', avec_socat=True):
        base = tempfile.mkdtemp(prefix='tk-classicube-outils-')
        journal = os.path.join(base, 'relais')
        outils = outils_relais(base, avec_socat)
        try:
            # Le faux serveur est posé avant le lancement (le lanceur le cherche dans son dossier).
            vals = dict(defauts, relais_web=relais)
            d = tempfile.mkdtemp(prefix='tk-classicube-')
            inst = os.path.join(d, 'classicube')
            os.makedirs(inst)
            with io.open(os.path.join(inst, 'lancer-classicube.sh'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(lanceur)
            with io.open(os.path.join(inst, 'reglages-classicube.txt'), 'w', encoding='utf-8', newline='\n') as f:
                f.write(rendre(vals))
            with io.open(os.path.join(inst, 'MCGalaxy'), 'w', encoding='utf-8', newline='\n') as f:
                f.write('#!/bin/bash\nIFS= read -r cmd\necho "faux:$cmd:$$"\n')
            env = dict(os.environ, TK_JOURNAL_RELAIS=journal, TK_SOCAT=socat)
            env.pop('TK_ESSAI_REGLAGES', None)
            env['PATH'] = outils + os.pathsep + env.get('PATH', '')
            r = subprocess.run([bash, '-c', 'echo "lanceur:$$"; exec bash "$0" "$@"', os.path.join(inst, 'lancer-classicube.sh')] + args,
                               input=b'/shutdown\n', capture_output=True, timeout=60, env=env, cwd=d)
            sortie = r.stdout.decode('utf-8', 'replace') + r.stderr.decode('utf-8', 'replace')
            lu = {}
            for suffixe in ('setpriv', 'socat', 'entree'):
                if os.path.exists(journal + '.' + suffixe):
                    lu[suffixe] = io.open(journal + '.' + suffixe, encoding='utf-8').read().splitlines()
            mf = re.search(r'faux:([^:]*):(\d+)', sortie)
            ml = re.search(r'lanceur:(\d+)', sortie)
            serveur_ok = bool(mf and ml and mf.group(1) == '/shutdown' and mf.group(2) == ml.group(1))
            shutil.rmtree(d, ignore_errors=True)
            return r.returncode, sortie, lu, serveur_ok
        finally:
            shutil.rmtree(base, ignore_errors=True)

    SOCAT = ['socat', 'TCP-LISTEN:25600,fork,reuseaddr,nodelay', 'TCP:127.0.0.1:25599,nodelay']
    code, sortie, lu, serveur_ok = demarrer('true', ['25599', '16', '25600'])
    if code or not serveur_ok:
        soucis.append('relais coché : le serveur doit toujours remplacer le lanceur (exec) et recevoir /shutdown : %r' % sortie)
    if lu.get('setpriv') != ['--pdeathsig', 'TERM', '--'] + SOCAT or lu.get('socat') != SOCAT[1:]:
        soucis.append('relais coché : socat attendu sous setpriv --pdeathsig TERM : %r' % lu)
    if 'entree' in lu:
        soucis.append('relais coché : socat a lu la console d’AMP (%r) : son entrée doit être /dev/null' % lu['entree'])
    if 'relais pour un proxy web actif : port 25600 -> 127.0.0.1:25599' not in sortie:
        soucis.append('relais coché : message « relais actif » absent : %r' % sortie)
    code, sortie, lu, serveur_ok = demarrer('true', ['25599', '16', '02560'])
    if lu.get('socat') != ['TCP-LISTEN:2560,fork,reuseaddr,nodelay', SOCAT[2]]:
        soucis.append('relais, port écrit 02560 : 2560 attendu (pas d’octal) : %r' % lu)
    code, sortie, lu, serveur_ok = demarrer('false', ['25599', '16', '25600'])
    if code or not serveur_ok or lu or 'relais' in sortie:
        soucis.append('relais décoché : socat ne doit pas être lancé : %r %r' % (lu, sortie))
    code, sortie, lu, serveur_ok = demarrer('true', ['25599', '16', '25599'])
    if code or not serveur_ok or lu:
        soucis.append('relais sur le port du jeu : socat ne doit pas être lancé, le serveur démarre : %r %r' % (lu, sortie))
    code, sortie, lu, serveur_ok = demarrer('true', ['25599', '16', '25600'], socat='meurt')
    if code or not serveur_ok or "socat s'est arrete" not in sortie:
        soucis.append('relais, socat qui s’arrête : message attendu et serveur démarré : %r' % sortie)
    if not shutil.which('socat'):
        code, sortie, lu, serveur_ok = demarrer('true', ['25599', '16', '25600'], avec_socat=False)
        if code or not serveur_ok or 'socat manque' not in sortie:
            soucis.append('relais sans socat : message « socat manque » attendu, serveur démarré : %r' % sortie)
    print('ok   relais pour un proxy web     %d contrôles du port, socat sous setpriv avant exec, entrée /dev/null' % len(ESSAIS_RELAIS))


# ── 4c. case « Compilateur de plugins » : mono MCGalaxyCLI.exe, sinon le serveur autonome ──
if bash:
    outils_mono = tempfile.mkdtemp(prefix='tk-classicube-mono-')
    try:
        with io.open(os.path.join(outils_mono, 'mono'), 'w', encoding='utf-8', newline='\n') as f:
            f.write('#!/bin/bash\nIFS= read -r cmd\necho "faux-mono:$1:$cmd:$$"\n')
        os.chmod(os.path.join(outils_mono, 'mono'), 0o755)
        AUTONOME = {'MCGalaxy': '#!/bin/bash\nIFS= read -r cmd\necho "faux:$cmd:$$"\n'}
        NET = {'MCGalaxy_.dll': 'MZ', 'MCGalaxyCLI.exe': 'MZ'}
        def essai_mono(compil, fichiers, avec_mono=True):
            d, inst, code, sortie = lancer({'compilateur': compil}, ['25599', '16'], essai=False,
                                           outils=outils_mono if avec_mono else None, fichiers=fichiers)
            shutil.rmtree(d, ignore_errors=True)
            ml = re.search(r'lanceur:(\d+)', sortie)
            mm = re.search(r'faux-mono:([^:]*):([^:]*):(\d+)', sortie)
            ma = re.search(r'faux:([^:]*):(\d+)', sortie)
            return code, sortie, ml, mm, ma
        code, sortie, ml, mm, ma = essai_mono('true', dict(AUTONOME, **NET))
        if code or not (ml and mm and mm.group(1).endswith('/MCGalaxyCLI.exe') and mm.group(2) == '/shutdown' and mm.group(3) == ml.group(1)):
            soucis.append('compilateur coché : exec mono MCGalaxyCLI.exe attendu (même processus, /shutdown reçu) : %r' % sortie)
        code, sortie, ml, mm, ma = essai_mono('false', dict(AUTONOME, **NET))
        if code or mm or not (ma and ma.group(1) == '/shutdown'):
            soucis.append('compilateur décoché : le serveur autonome doit démarrer : %r' % sortie)
        code, sortie, ml, mm, ma = essai_mono('true', AUTONOME)
        if code or mm or not ma or 'lance Update' not in sortie or 'sans /pcompile' not in sortie:
            soucis.append('compilateur coché sans MCGalaxyCLI.exe : message + serveur autonome attendus : %r' % sortie)
        if not shutil.which('mono'):
            code, sortie, ml, mm, ma = essai_mono('true', dict(AUTONOME, **NET), avec_mono=False)
            if code or mm or not ma or 'Mono manque' not in sortie:
                soucis.append('compilateur coché sans Mono : message + serveur autonome attendus : %r' % sortie)
        code, sortie, ml, mm, ma = essai_mono('true', NET, avec_mono=False)
        if shutil.which('mono') is None and (code != 1 or 'pas installe' not in sortie):
            soucis.append('compilateur coché, ni Mono ni serveur autonome : erreur attendue : %r' % sortie)
        code, sortie, ml, mm, ma = essai_mono('$(touch pirate)', dict(AUTONOME, **NET))
        if code or mm or not ma:
            soucis.append('compilateur piégé : comparé à true seulement, serveur autonome : %r' % sortie)
        print('ok   compilateur de plugins       mono MCGalaxyCLI.exe en exec, repli sur le serveur autonome, valeur jamais exécutée')
    finally:
        shutil.rmtree(outils_mono, ignore_errors=True)


# ── 5. fichiers téléchargés à l'Update, scripts ──────────────────────────────
depot = manifest['url'].replace('https://github.com/', '')
fetch = [e for e in updates if e['UpdateSource'] == 'FetchURL']
for e in fetch:
    attendu = 'https://raw.githubusercontent.com/%s/main/scripts/%s' % (depot, e['UpdateSourceArgs'])
    if e['UpdateSourceData'] != attendu:
        soucis.append('URL inattendue pour %s : %s' % (e['UpdateSourceArgs'], e['UpdateSourceData']))
    elif not os.path.isfile(os.path.join(ICI, 'scripts', e['UpdateSourceArgs'])):
        soucis.append('scripts/%s absent du dépôt' % e['UpdateSourceArgs'])
    else:
        print('ok   téléchargé à l’Update        scripts/%s' % e['UpdateSourceArgs'])
if {e['UpdateSourceArgs'] for e in fetch} != {'AMP_reglages-classicube.txt', 'lancer-classicube.sh', 'installer-classicube.sh'}:
    soucis.append('l’Update doit déposer les deux scripts et le modèle des réglages')
dernier = updates[-1]
if dernier['UpdateSource'] != 'Executable' or dernier['UpdateSourceArgs'] != '"{{$FullBaseDir}}installer-classicube.sh" "{{$FullBaseDir}}" "{{version_dev}}" "{{compilateur}}"':
    soucis.append('la dernière étape de l’Update doit lancer installer-classicube.sh avec les cases version_dev et compilateur')
for nom in sorted(glob.glob(os.path.join(ICI, 'scripts', '*'))):
    rel = os.path.relpath(nom, ICI).replace('\\', '/')
    contenu = lire(rel)
    if b'\r' in lire(rel, binaire=True):
        soucis.append('%s : fins de ligne Windows (CRLF)' % rel)
    if '{{$' in contenu:
        soucis.append('%s contient {{$...}} : AMP ne remplace pas ses variables dans les fichiers livrés' % rel)
    if rel.endswith('.sh'):
        if '{{' in contenu:
            soucis.append('%s contient {{ : AMP pourrait le remplacer' % rel)
        if re.search(r'\beval\b', contenu):
            soucis.append('%s : eval interdit (les valeurs viennent de l’onglet Configuration)' % rel)
        if not contenu.startswith('#!/bin/bash\n'):
            soucis.append('%s : doit commencer par #!/bin/bash' % rel)
        if bash:
            r = subprocess.run([bash, '-n', nom], capture_output=True, text=True)
            if r.returncode:
                soucis.append('bash -n %s : %s' % (rel, r.stderr.strip()))
            else:
                print('ok   bash -n                      %s' % rel)
perl_bin = shutil.which('perl')
if perl and perl_bin:
    with tempfile.NamedTemporaryFile('w', suffix='.pl', delete=False, encoding='utf-8', newline='\n') as f:
        f.write(perl)
    r = subprocess.run([perl_bin, '-c', f.name], capture_output=True, text=True)
    os.remove(f.name)
    if r.returncode:
        soucis.append('perl -c : %s' % r.stderr.strip())
    else:
        print('ok   perl -c                      code perl du lanceur')
if re.search(r'^\s*use (?!strict|warnings)', perl, re.M):
    soucis.append('perl : aucun module hors strict/warnings (seul perl-base est garanti)')
for besoin, pourquoi in [
    ('export TERM=dumb', 'pas de codes couleur dans la console d’AMP'),
    ('exec "$BIN"', 'la console d’AMP doit arriver sur l’entrée du serveur'),
    ('exec mono "$ICI/MCGalaxyCLI.exe"', 'forme Mono : même processus, la console d’AMP arrive sur l’entrée du serveur'),
    ('perl -e "$PERL_REGLAGES" "$REGLAGES" "$PROPS" "$PORT" "$JOUEURS" "$AUTH"', 'valeurs passées en arguments, jamais dans du code'),
    ('rename("$auth.tmp", $auth)', 'authservices.properties remplacé en une fois'),
    ('$ecrire{"verify-lan-ips"} = "true"', 'pseudos vérifiés aussi depuis le loopback et le réseau Docker'),
    ('setpriv --pdeathsig TERM -- socat TCP-LISTEN:"$RELAIS_PORT",fork,reuseaddr', 'le relais meurt avec le serveur'),
    ('TCP:127.0.0.1:"$PORT"', 'le relais doit arriver en loopback (seule origine dont MCGalaxy croit X-Real-IP)'),
    # bash non interactif donne déjà /dev/null aux tâches de fond ; on l'écrit quand même.
    (',nodelay </dev/null &', 'entrée du relais = /dev/null, jamais la console d’AMP'),
    ('App\\.MaxUsers=', 'repli si AMP ne remplace pas MaxUsers'),
    ('rename("$props.tmp", $props)', 'remplacement en une fois'),
]:
    if besoin not in lanceur:
        soucis.append('lanceur : %s absent (%s)' % (besoin, pourquoi))


# ── 6. installeur (faux curl) ────────────────────────────────────────────────
FAUX_CURL = r'''#!/bin/bash
sortie=""; url=""
while [ $# -gt 0 ]; do
  case "$1" in
    -o) sortie="$2"; shift 2 ;;
    --retry|--connect-timeout) shift 2 ;;
    -*) shift ;;
    *) url="$1"; shift ;;
  esac
done
echo "$url" >> "$TK_JOURNAL_CURL"
case "$TK_FAUX_CURL" in
  echec) exit 22 ;;
  html) printf '<html>404</html>' > "$sortie" ;;
  zero) head -c 6000000 /dev/zero > "$sortie" ;;
  pe|pe2) { printf 'MZ'; head -c 600000 /dev/zero; [ "$TK_FAUX_CURL" = pe2 ] && printf 'v2'; } > "$sortie" ;;
  elf|elf2) { printf '\177ELF'; head -c 6000000 /dev/zero; [ "$TK_FAUX_CURL" = elf2 ] && printf 'v2'; } > "$sortie" ;;
esac
exit 0
'''


def installer(dossier, args, mode, reglages=None):
    outils = os.path.join(dossier, 'outils')
    os.makedirs(outils, exist_ok=True)
    with io.open(os.path.join(outils, 'curl'), 'w', encoding='utf-8', newline='\n') as f:
        f.write(FAUX_CURL)
    os.chmod(os.path.join(outils, 'curl'), 0o755)
    inst = os.path.join(dossier, 'classicube')
    if reglages is not None:
        with io.open(os.path.join(inst, 'reglages-classicube.txt'), 'w', encoding='utf-8', newline='\n') as f:
            f.write(reglages)
    journal = os.path.join(dossier, 'curl.txt')
    if os.path.exists(journal):
        os.remove(journal)
    env = dict(os.environ, TK_FAUX_CURL=mode, TK_JOURNAL_CURL=journal)
    env['PATH'] = outils + os.pathsep + env.get('PATH', '')
    r = subprocess.run([bash, os.path.join(ICI, INSTALLEUR), inst + '/'] + args, capture_output=True, timeout=60, env=env)
    urls = io.open(journal, encoding='utf-8').read().split() if os.path.exists(journal) else []
    return r.returncode, r.stdout.decode('utf-8', 'replace'), urls


def empreintes(dossier):
    res = {}
    for racine, _, fichiers in os.walk(dossier):
        for f in fichiers:
            if f in ('MCGalaxy', 'MCGalaxy_.dll', 'MCGalaxyCLI.exe', '.canal-mcgalaxy', 'reglages-classicube.txt'):
                continue
            with open(os.path.join(racine, f), 'rb') as h:
                res[os.path.relpath(os.path.join(racine, f), dossier)] = hashlib.md5(h.read()).hexdigest()
    return res


STABLE = 'https://cdn.classicube.net/client/mcg/release/linux64'
DEV = 'https://cdn.classicube.net/client/mcg/latest/linux64'
if bash:
    dossier = tempfile.mkdtemp(prefix='tk-classicube-')
    try:
      try:
        inst = os.path.join(dossier, 'classicube')
        for d, contenu in (('levels/main.lvl', b'carte'), ('ranks/owner.txt', b'Kevin'), ('properties/server.properties', b'port = 25565\n'),
                           ('MCGalaxy.db', b'SQLite format 3'), ('plugins/x.dll', b'MZ'), ('blockdb/main.cbdb', b'db'), ('text/rules.txt', b'r')):
            os.makedirs(os.path.dirname(os.path.join(inst, d)), exist_ok=True)
            with open(os.path.join(inst, d), 'wb') as f:
                f.write(contenu)
        avant = empreintes(inst)
        bin_ = os.path.join(inst, 'MCGalaxy')
        code, out, urls = installer(dossier, ['false'], 'elf')
        if code or urls != [STABLE] or not os.path.isfile(bin_) or not os.access(bin_, os.X_OK) \
                or io.open(os.path.join(inst, '.canal-mcgalaxy')).read().strip() != 'release':
            soucis.append('installeur, version stable : code %d, %r, %r' % (code, urls, out))
        code, out, urls = installer(dossier, ['false'], 'elf')
        if code or 'deja a jour' not in out:
            soucis.append('installeur, même fichier : « deja a jour » attendu : %r' % out)
        code, out, urls = installer(dossier, ['True'], 'elf2')
        if code or urls != [DEV] or not open(bin_, 'rb').read().endswith(b'v2') \
                or io.open(os.path.join(inst, '.canal-mcgalaxy')).read().strip() != 'latest':
            soucis.append('installeur, version de développement : code %d, %r, %r' % (code, urls, out))
        code, out, urls = installer(dossier, ['{{version_dev}}'], 'elf', reglages='version_dev=false\r\n')
        if code or urls != [STABLE] or 'retour de la version de developpement' not in out:
            soucis.append('installeur, case non remplacée + reglages false + retour en stable : %r %r' % (urls, out))
        code, out, urls = installer(dossier, ['{{version_dev}}'], 'elf', reglages='version_dev=true\n')
        if code or urls != [DEV]:
            soucis.append('installeur, case non remplacée : la valeur du dernier démarrage doit compter : %r' % urls)
        code, out, urls = installer(dossier, [], 'elf', reglages='rien\n')
        if code or urls != [STABLE]:
            soucis.append('installeur sans argument : version stable attendue : %r' % urls)
        garde = open(bin_, 'rb').read()
        code, out, urls = installer(dossier, ['false'], 'html')
        if code != 1 or open(bin_, 'rb').read() != garde or os.path.exists(bin_ + '.nouveau'):
            soucis.append('installeur, page HTML reçue : refus attendu, serveur gardé : %r' % out)
        code, out, urls = installer(dossier, ['false'], 'zero')
        if code != 1 or open(bin_, 'rb').read() != garde:
            soucis.append('installeur, gros fichier qui n’est pas un exécutable Linux : refus attendu : %r' % out)
        code, out, urls = installer(dossier, ['false'], 'echec')
        if code != 0 or open(bin_, 'rb').read() != garde:
            soucis.append('installeur, CDN injoignable avec un serveur installé : on le garde (code 0) : %r' % out)
        os.remove(bin_)
        code, out, urls = installer(dossier, ['false'], 'echec')
        if code != 1:
            soucis.append('installeur, CDN injoignable sans serveur : échec attendu')
        # Forme Mono (case compilateur) : la bibliothèque et le lanceur console, signature MZ.
        NET40 = [STABLE.replace('linux64', 'net40/' + f) for f in ('MCGalaxy_.dll', 'MCGalaxyCLI.exe')]
        dll, cli = os.path.join(inst, 'MCGalaxy_.dll'), os.path.join(inst, 'MCGalaxyCLI.exe')
        code, out, urls = installer(dossier, ['false', 'true'], 'pe')
        if code or urls != NET40 or not os.path.isfile(dll) or not os.path.isfile(cli) or 'avec compilateur installe' not in out                 or os.path.exists(bin_):
            soucis.append('installeur, compilateur coché : code %d, %r, %r' % (code, urls, out))
        code, out, urls = installer(dossier, ['false', 'True'], 'pe')
        if code or 'avec compilateur deja a jour' not in out:
            soucis.append('installeur, compilateur, mêmes fichiers : « deja a jour » attendu : %r' % out)
        code, out, urls = installer(dossier, ['true', 'true'], 'pe2')
        if code or urls != [u.replace('/release/', '/latest/') for u in NET40] or not open(dll, 'rb').read().endswith(b'v2'):
            soucis.append('installeur, compilateur + développement : %r %r' % (urls, out))
        code, out, urls = installer(dossier, ['{{version_dev}}', '{{compilateur}}'], 'pe', reglages='version_dev=false\ncompilateur=true\r\n')
        if code or urls != NET40:
            soucis.append('installeur, cases non remplacées : la valeur du dernier démarrage doit compter (compilateur) : %r' % urls)
        garde = open(dll, 'rb').read()
        code, out, urls = installer(dossier, ['false', 'true'], 'elf')
        if code != 1 or open(dll, 'rb').read() != garde or os.path.exists(dll + '.nouveau') or os.path.exists(cli + '.nouveau'):
            soucis.append('installeur, compilateur, fichier non .NET reçu : refus attendu, serveur gardé : %r' % out)
        code, out, urls = installer(dossier, ['false', 'true'], 'echec')
        if code != 0 or open(dll, 'rb').read() != garde:
            soucis.append('installeur, compilateur, CDN injoignable avec un serveur installé : on le garde (code 0) : %r' % out)
        os.remove(dll)
        code, out, urls = installer(dossier, ['false', 'true'], 'echec')
        if code != 1:
            soucis.append('installeur, compilateur, CDN injoignable sans serveur : échec attendu')
        if empreintes(inst) != avant:
            soucis.append('installeur : des données du serveur ont été modifiées : %r' % (set(empreintes(inst).items()) ^ set(avant.items())))
        print('ok   installeur                   stable / dev / dernier démarrage, contrôle ELF et MZ, compilateur, données intactes')
      except Exception as e:
        soucis.append('installeur : essai interrompu (%s)' % e)
    finally:
        shutil.rmtree(dossier, ignore_errors=True)

# ── 7. regex de console ──────────────────────────────────────────────────────
# Lignes au format de MCGalaxy 1.9.5.3 : Logger.Log(...) précédé de « (HH:mm:ss) »
# (CLI/Program.cs) ; Player.Login.cs l.144 (arrivée), Player.cs l.308 et 312 (départs).
ESC = '\x1b[0m'
ESSAIS = [
    ('Console.AppReadyRegex', '(15:43:55) Finished setting up server', {}),
    ('Console.AppReadyRegex', ESC + '(15:43:55) Finished setting up server' + ESC, {}),
    ('Console.UserJoinRegex', '(15:44:10) Kevin_TK [203.0.113.7] connected using ClassiCube 1.3.7.', {'username': 'Kevin_TK'}),
    ('Console.UserJoinRegex', '(09:01:02) hydro.cut [::ffff:203.0.113.7] connected using ClassiCube 1.3.7 web + mobile.', {'username': 'hydro.cut'}),
    ('Console.UserJoinRegex', '(23:59:59) a [127.0.0.1] connected using ClassiCube 1.3.6.', {'username': 'a'}),
    ('Console.UserJoinRegex', ESC + '(23:59:59) Abcdefghijklmnop [127.0.0.1] connected using ClassiCube 1.3.6.' + ESC, {'username': 'Abcdefghijklmnop'}),
    ('Console.UserLeaveRegex', '(15:50:02) Kevin_TK disconnected (Disconnected).', {'username': 'Kevin_TK'}),
    ('Console.UserLeaveRegex', '(15:50:02) Kevin_TK disconnected (Disconnected&S).', {'username': 'Kevin_TK'}),
    ('Console.UserLeaveRegex', '(15:50:02) hydro.cut disconnected (Server shutdown. Rejoin in 10 seconds.).', {'username': 'hydro.cut'}),
    ('Console.UserLeaveRegex', '(15:50:02) Bob_42 kicked (Kicked by (console): spam (ok)&S).', {'username': 'Bob_42'}),
    ('Console.UserLeaveRegex', ESC + '(15:50:02) Bob_42 kicked (' + ESC + 'You were kicked' + ESC + ').' + ESC, {'username': 'Bob_42'}),
    # Joueurs entrés par le service supplémentaire : suffixe ajouté au pseudo (AuthService.AcceptPlayer).
    ('Console.UserJoinRegex', '(15:44:10) Kevin+ [203.0.113.7] connected using ClassiCube 1.3.7 web.', {'username': 'Kevin+'}),
    ('Console.UserJoinRegex', '(15:44:10) Abcdefghijklmnop~tk [203.0.113.7] connected using ClassiCube 1.3.7.', {'username': 'Abcdefghijklmnop~tk'}),
    ('Console.UserLeaveRegex', '(15:50:02) Kevin+ disconnected (Disconnected).', {'username': 'Kevin+'}),
    ('Console.UserLeaveRegex', '(15:50:02) hydro.cut-1 kicked (spam).', {'username': 'hydro.cut-1'}),
    ('Console.UpdateAvailableRegex', 'MCGalaxy update available! Update by replacing with the files from https://github.com/ClassiCube/MCGalaxy/tree/master/Uploads', {}),
]
for cle, ligne, attendu in ESSAIS:
    m = py(cles.get(cle) or '^$').search(ligne)
    if not m or any(m.group(k) != v for k, v in attendu.items()):
        soucis.append('%s ne reconnaît pas : %r' % (cle, ligne))
PIEGES = [
    ('Console.AppReadyRegex', '(15:43:55) Started listening on port 25565... '),
    ('Console.AppReadyRegex', '(15:43:55) Starting Server'),
    ('Console.AppReadyRegex', '(15:44:00) Bob: Finished setting up server'),
    ('Console.UserJoinRegex', '(15:43:58) Server URL found: http://www.classicube.net/server/play/0123456789abcdef/'),
    ('Console.UserJoinRegex', '(15:44:00) Bob: Kevin [1.2.3.4] connected using ClassiCube.'),
    ('Console.UserJoinRegex', '(15:44:00) Kevin_TK disconnected (Disconnected).'),
    ('Console.UserJoinRegex', '(15:44:00) Abcdefghijklmnopqrst [127.0.0.1] connected using ClassiCube 1.3.6.'),
    ('Console.UserJoinRegex', '(15:44:00) 127.0.0.1 is forwarding a connection from 203.0.113.7'),
    ('Console.UserLeaveRegex', '(15:44:00) 127.0.0.1 is forwarding a connection from 203.0.113.7'),
    ('Console.UserJoinRegex', '(15:44:00) Kévin [127.0.0.1] connected using ClassiCube 1.3.6.'),
    ('Console.UserLeaveRegex', '(15:44:00) 203.0.113.7 disconnected.'),
    # Session jamais connectée (pseudo non vérifié, peut-être usurpé) : pas un départ.
    ('Console.UserLeaveRegex', '(15:44:00) Kevin_TK (203.0.113.7) disconnected. (Login failed! Close the game and sign in again.)'),
    ('Console.UserLeaveRegex', '(15:44:00) Bob: Kevin_TK disconnected (lol).'),
    ('Console.UserLeaveRegex', '(15:44:00) Server shutting down (Server shutdown. Rejoin in 10 seconds.)'),
    ('Console.UserLeaveRegex', '(15:44:10) Kevin_TK [203.0.113.7] connected using ClassiCube 1.3.7.'),
    ('Console.UserLeaveRegex', '(15:44:00) * Bob kicked (pour rire).'),
    ('Console.UpdateAvailableRegex', '(15:44:00) No update found!'),
]
for cle, ligne in PIEGES:
    if py(cles[cle]).search(ligne):
        soucis.append('%s attrape une ligne qui n’est pas pour lui : %r' % (cle, ligne))
print('ok   console                      %d lignes du serveur, %d pièges' % (len(ESSAIS), len(PIEGES)))

print()
if soucis:
    print('%d problème(s) :' % len(soucis))
    print('\n'.join('  NON  ' + s for s in soucis))
    sys.exit(1)
print('Tout est bon.')
