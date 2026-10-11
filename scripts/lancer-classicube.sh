#!/bin/bash
# lancer-classicube.sh - pose par le template AMP TeamKit (recree a chaque Update).
# Arguments : <port du jeu> <joueurs maximum> [port du relais]   (ligne de commande d'AMP)
#
# 1. lit les reglages ecrits par AMP (reglages-classicube.txt, une ligne cle=valeur) ;
# 2. les recopie dans properties/server.properties, A CHAQUE demarrage : MCGalaxy reecrit
#    ce fichier lui-meme (au demarrage et a chaque /server ou /main), l'onglet
#    Configuration d'AMP doit donc etre reapplique avant chaque lancement. Seules nos cles
#    sont touchees : une ligne existante est remplacee, une cle absente est ajoutee, le
#    fichier est cree s'il n'existe pas encore (MCGalaxy le complete au demarrage) ;
#    HeartbeatURL (classicube.net + service de connexion supplementaire eventuel) y est
#    ecrit aussi, et properties/authservices.properties est reecrit (suffixe des pseudos) ;
# 3. si la case « Relais pour un proxy web » est cochee : demarre socat, qui recoit sur le
#    port du relais et se reconnecte a 127.0.0.1:<port du jeu>. Un nginx de la meme machine
#    arrive ainsi en loopback, seule origine dont MCGalaxy croit l'en-tete X-Real-IP ;
# 4. remplace ce script par le serveur (exec), le binaire autonome MCGalaxy, ou Mono avec
#    MCGalaxyCLI.exe si la case « Compilateur de plugins » est cochee : la console d'AMP arrive directement sur
#    l'entree de MCGalaxy (/rank, /say, /save all...), et la commande d'arret d'AMP
#    (/shutdown) aussi.
#
# Aucune valeur n'est evaluee par le shell : elles ne passent que par perl, qui les lit
# dans le fichier et les ecrit dans un autre (aucune commande n'est construite avec elles).
cd "$(dirname "$0")" || exit 1
ICI="$PWD"
BIN="$ICI/MCGalaxy"
REGLAGES="$ICI/reglages-classicube.txt"
PROPS="$ICI/properties/server.properties"
AUTH="$ICI/properties/authservices.properties"
export LANG=C.UTF-8 LC_ALL=C.UTF-8

PORT="${1:-25565}"
JOUEURS="${2:-}"
RELAIS_PORT="${3:-}"
if ! [[ "$PORT" =~ ^[0-9]{1,5}$ ]] || [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
  echo "ERREUR : port du jeu invalide : $PORT"
  exit 1
fi
# Joueurs maximum : AMP remplace la variable MaxUsers dans la ligne de commande. Si elle
# arrive telle quelle (vu sur Urban Terror pour un fichier de reglages, le 10/10/2026),
# on lit App.MaxUsers dans le GenericModule.kvp de l'instance, sinon 32.
if ! [[ "$JOUEURS" =~ ^[0-9]{1,3}$ ]]; then
  TROUVE=""
  for kvp in "$ICI/../GenericModule.kvp" "$ICI/GenericModule.kvp"; do
    [ -r "$kvp" ] || continue
    TROUVE=$(sed -n 's/^App\.MaxUsers=\([0-9]\{1,3\}\)\r\{0,1\}$/\1/p' "$kvp" | head -n 1)
    [ -n "$TROUVE" ] && break
  done
  JOUEURS="${TROUVE:-32}"
  echo "TeamKit : joueurs maximum lus dans les reglages de l'instance : $JOUEURS"
fi
JOUEURS=$((10#$JOUEURS))
if [ "$JOUEURS" -lt 1 ] || [ "$JOUEURS" -gt 256 ]; then
  echo "TeamKit : joueurs maximum $JOUEURS hors limites (1 a 256), 32 utilise."
  JOUEURS=32
fi

# ── Forme du serveur (case compilateur) ──────────────────────────────────────────
# La valeur de la case est seulement comparee a « true » : jamais executee.
COMPIL=$(sed -n 's/^compilateur=\(.*\)$/\1/p' "$REGLAGES" 2>/dev/null | head -n 1 | tr -d '\r[:space:]')
MONO=0
if [ "${COMPIL,,}" = true ]; then
  if [ ! -f "$ICI/MCGalaxyCLI.exe" ] || [ ! -f "$ICI/MCGalaxy_.dll" ]; then
    echo "TeamKit : compilateur de plugins coche, mais MCGalaxyCLI.exe et MCGalaxy_.dll ne sont pas encore installes : lance Update dans AMP."
  elif ! command -v mono >/dev/null 2>&1; then
    echo "TeamKit : compilateur de plugins coche, mais Mono manque dans le conteneur (paquets du template, installes a son demarrage) : recupere la derniere version du template (Fetch dans ADS) puis redemarre l'instance."
  else
    MONO=1
  fi
  if [ "$MONO" = 0 ] && [ -f "$BIN" ]; then
    echo "TeamKit : en attendant, demarrage du serveur autonome (sans /pcompile)."
  fi
fi
if [ -z "$TK_ESSAI_REGLAGES" ] && [ "$MONO" = 0 ] && [ ! -f "$BIN" ]; then
  echo "ERREUR : le serveur MCGalaxy n'est pas installe dans ce dossier. Lance Update dans AMP."
  exit 1
fi
if [ ! -f "$REGLAGES" ]; then
  echo "TeamKit : $(basename "$REGLAGES") absent (AMP l'ecrit au demarrage) : seuls le port et les joueurs maximum sont appliques."
fi
mkdir -p "$ICI/properties" || exit 1

# ── Recopie des reglages d'AMP dans properties/server.properties ─────────────────
PERL_REGLAGES='
use strict;
use warnings;
my ($fichier, $props, $port, $joueurs, $auth) = @ARGV;

# cle du modele AMP => [cle de server.properties, genre, choix possibles]
# version_dev ne sert qu a l Update (installer-classicube.sh), compilateur a l Update et au
# script bash (forme du serveur a lancer), relais_web au script bash
# (demarrage de socat) : rien a ecrire. service_connexion et suffixe_service sont traites
# a part (HeartbeatURL et properties/authservices.properties), apres les autres.
my %TABLE = (
  version_dev          => [undef,                     "bool"],
  compilateur          => [undef,                     "bool"],
  relais_web           => [undef,                     "bool"],
  service_connexion    => ["HeartbeatURL",            "service"],
  suffixe_service      => [undef,                     "suffixe"],
  liste_publique       => ["public",                  "bool"],
  verifier_pseudos     => ["verify-names",            "bool"],
  places_invites       => ["max-guests",              "entier"],
  rang_defaut          => ["default-rank",            "choix", "guest advbuilder builder"],
  accepter_reglement   => ["agree-to-rules-on-entry", "bool"],
  theme_carte          => ["default-mapgen-theme",    "choix",
                           "flat classic forest island mountains ocean desert hell archipelago atoll bay dunes hills ice lake peninsula river streams space rainbow pixel empty"],
  filtre_grossieretes  => ["profanity-filter",        "bool"],
  proprietaire_affiche => ["server-owner",            "texte"],
  message_accueil      => ["motd",                    "texte"],
  nom_serveur          => ["server-name",             "nom"],
);
my $NOM_DEFAUT = "[FR] TeamKit - ClassiCube";

# Lettres accentuees et symboles courants => ASCII (server-name n accepte que l ASCII :
# un seul autre caractere et MCGalaxy remplace le nom entier par « [MCGalaxy] Default »).
my %ASCII;
my @PAIRES = (
  "\x{e0}\x{e1}\x{e2}\x{e3}\x{e4}\x{e5}" => "a", "\x{c0}\x{c1}\x{c2}\x{c3}\x{c4}\x{c5}" => "A",
  "\x{e8}\x{e9}\x{ea}\x{eb}" => "e", "\x{c8}\x{c9}\x{ca}\x{cb}" => "E",
  "\x{ec}\x{ed}\x{ee}\x{ef}" => "i", "\x{cc}\x{cd}\x{ce}\x{cf}" => "I",
  "\x{f2}\x{f3}\x{f4}\x{f5}\x{f6}\x{f8}" => "o", "\x{d2}\x{d3}\x{d4}\x{d5}\x{d6}\x{d8}" => "O",
  "\x{f9}\x{fa}\x{fb}\x{fc}" => "u", "\x{d9}\x{da}\x{db}\x{dc}" => "U",
  "\x{fd}\x{ff}" => "y", "\x{dd}\x{178}" => "Y", "\x{e7}" => "c", "\x{c7}" => "C",
  "\x{f1}" => "n", "\x{d1}" => "N", "\x{d7}" => "x",
  "\x{b7}\x{2022}\x{2013}\x{2014}\x{2212}" => "-",
  "\x{ab}\x{bb}\x{201c}\x{201d}\x{201e}" => "\x22", "\x{2018}\x{2019}\x{201a}\x{b4}" => "\x27",
  "\x{a0}\x{202f}\x{2009}" => " ",
);
while (my ($car, $rempl) = splice(@PAIRES, 0, 2)) { $ASCII{$_} = $rempl for split //, $car }
$ASCII{"\x{153}"} = "oe"; $ASCII{"\x{152}"} = "OE"; $ASCII{"\x{e6}"} = "ae"; $ASCII{"\x{c6}"} = "AE";
$ASCII{"\x{df}"} = "ss"; $ASCII{"\x{2026}"} = "...";

sub texte_vers_caracteres { my $v = shift; my $c = $v; return utf8::decode($c) ? $c : $v; }
sub longueur { return length(texte_vers_caracteres(shift)); }

# 1. lecture du fichier rendu par AMP. Une ligne qui ne commence pas par une de nos cles
#    est la suite de la valeur precedente (retour a la ligne dans un reglage) : recollee
#    avec une espace, elle ne peut jamais devenir une autre cle de server.properties.
my (%valeurs, $courant);
if (-e $fichier) {
  open(my $f, "<:raw", $fichier) or die "ERREUR : lecture de $fichier impossible\n";
  while (my $l = <$f>) {
    $l =~ s/\r?\n\z//;
    if ($l =~ /^([a-z_]+)=(.*)\z/s && exists $TABLE{$1}) {
      if (exists $valeurs{$1}) { print "TeamKit : $1 apparait deux fois dans les reglages : seule la premiere valeur compte.\n"; $courant = undef; next }
      $valeurs{$1} = $2; $courant = $1; next;
    }
    next if !defined $courant && ($l =~ /^#/ || $l !~ /\S/);
    if (defined $courant) { $valeurs{$courant} .= " " . $l; next }
  }
  close $f;
  # Variable laissee telle quelle par AMP (instance creee avant l ajout du reglage) :
  # comme absente, la valeur actuelle est gardee.
  for my $k (keys %valeurs) { delete $valeurs{$k} if $valeurs{$k} =~ /^\x7b\x7b[a-z_]+\x7d\x7d\s*\z/ }
  my @absentes = grep { !exists $valeurs{$_} } sort keys %TABLE;
  print "TeamKit : reglages absents de reglages-classicube.txt (valeur actuelle gardee) : @absentes\n" if @absentes;
}

# 2. controle et mise en forme de chaque valeur
my %ecrire;
for my $cle (sort keys %valeurs) {
  my ($prop, $genre, $choix) = @{$TABLE{$cle}};
  next unless defined $prop;
  next if $genre eq "service";
  my $v = $valeurs{$cle};
  $v =~ s/[\x00-\x1f\x7f]+/ /g;          # caracteres de controle (dont retours a la ligne)
  $v =~ s/^\s+//; $v =~ s/\s+\z//;
  if ($genre eq "bool") {
    if ($v =~ /^(true|false)\z/i) { $ecrire{$prop} = lc $v }
    else { print "TeamKit : $cle doit valoir true ou false, pas \"$v\" : valeur actuelle gardee.\n" }
  } elsif ($genre eq "entier") {
    if ($v =~ /^\d{1,3}\z/ && $v >= 1 && $v <= 256) { $ecrire{$prop} = $v + 0 }
    else { print "TeamKit : $cle doit etre un nombre de 1 a 256, pas \"$v\" : valeur actuelle gardee.\n" }
  } elsif ($genre eq "choix") {
    my ($bon) = grep { $_ eq lc $v } split / /, $choix;
    if (defined $bon) { $ecrire{$prop} = $bon }
    else { print "TeamKit : $cle ne peut pas valoir \"$v\" (choix : $choix) : valeur actuelle gardee.\n" }
  } elsif ($genre eq "nom") {
    my $c = texte_vers_caracteres($v);
    my $avant = $c;
    my $retires = 0;
    $c =~ s/([^\x20-\x7e])/exists $ASCII{$1} ? $ASCII{$1} : do { $retires++; "" }/ge;
    $c =~ s/ {2,}/ /g; $c =~ s/^ //; $c =~ s/ \z//;
    if ($c eq "") {
      print "TeamKit : nom du serveur vide : \"$NOM_DEFAUT\" utilise.\n";
      $c = $NOM_DEFAUT;
    } elsif ($c ne $avant) {
      print "TeamKit : nom du serveur converti en ASCII (seul accepte par MCGalaxy) : \"$c\"" . ($retires ? " ($retires caractere(s) retire(s))" : "") . ".\n";
    }
    print "TeamKit : ATTENTION, le nom du serveur fait " . length($c) . " caracteres : le jeu n en affiche que 64.\n" if length($c) > 64;
    $ecrire{$prop} = $c;
  } else {
    print "TeamKit : $cle vide : MCGalaxy mettra sa valeur par defaut.\n" if $v eq "" && $prop eq "motd";
    my $n = longueur($v);
    print "TeamKit : ATTENTION, $cle fait $n caracteres : le jeu n en affiche que 64.\n" if $prop eq "motd" && $n > 64;
    $ecrire{$prop} = $v;
  }
}

# 2b. service de connexion supplementaire (comptes d un autre site, TeamKit par exemple).
#     MCGalaxy envoie son heartbeat a chaque adresse de HeartbeatURL (separees par des
#     virgules), avec un sel propre a chacune ; un joueur est verifie si son mppass vaut
#     md5(sel + pseudo) pour l une d elles, et le name-suffix de ce service (fichier
#     properties/authservices.properties) est alors ajoute a son pseudo.
#     MCGalaxy 1.9.5.3 n accepte dans HeartbeatURL que lettres, chiffres et : / . ,
#     (ServerConfig.cs, ConfigString ... ":/.,") : un seul autre caractere et il remet
#     l adresse de classicube.net seule. On refuse donc ici tout le reste.
my $CCNET = "http://www.classicube.net/heartbeat.jsp";
my ($service, $suffixe, $ecrire_auth) = ("", "+", 0);
sub nettoyer { my $v = shift; $v =~ s/[\x00-\x1f\x7f]+/ /g; $v =~ s/^\s+//; $v =~ s/\s+\z//; return $v; }
sub montrer {
  my $c = shift;
  return ($c =~ /^[\x21-\x7e]\z/) ? "\x22$c\x22" : ($c eq " " ? "espace" : sprintf("U+%04X", ord $c));
}
if (exists $valeurs{service_connexion}) {
  $ecrire_auth = 1;
  my $s = texte_vers_caracteres(nettoyer($valeurs{service_connexion}));
  if ($s ne "") {
    my $refus;
    my ($hote, $port_s) = $s =~ m{^https://([A-Za-z0-9](?:[A-Za-z0-9.]*[A-Za-z0-9])?)(?::([0-9]{1,5}))?(?:/[A-Za-z0-9./]*)?\z};
    if (length($s) > 200) {
      $refus = "adresse trop longue (" . length($s) . " caracteres, 200 au plus)";
    } elsif ($s !~ m{^https://}) {
      $refus = "l adresse doit commencer par https://";
    } elsif ($s =~ m{([^A-Za-z0-9:/.])}) {
      $refus = "caractere " . montrer($1) . " interdit : MCGalaxy n accepte dans HeartbeatURL que les lettres sans accent, les chiffres, : / et . (ni tiret, ni _, ni ?, =, &, %, virgule ou espace ; sinon il oublie le service)";
    } elsif (!defined $hote || index($hote, ".") < 0 || $hote =~ /\.\./
             || (defined $port_s && ($port_s < 1 || $port_s > 65535))) {
      $refus = "adresse mal formee (attendu : https://nom.de.domaine/chemin)";
    } elsif ($hote =~ /(?:^|\.)classicube\.net\z/i) {
      $refus = "c est deja le service de classicube.net, toujours actif";
    }
    if (defined $refus) {
      print "TeamKit : service de connexion supplementaire IGNORE : $refus. Seuls les comptes classicube.net sont acceptes.\n";
    } else {
      $service = $s;
    }
  }
  if ($service ne "") {
    my $x = exists $valeurs{suffixe_service} ? texte_vers_caracteres(nettoyer($valeurs{suffixe_service})) : "+";
    if ($x =~ /^[A-Za-z0-9+~_.-]{1,3}\z/ && $x =~ /[+~-]/) {
      $suffixe = $x;
    } else {
      utf8::encode($x) if utf8::is_utf8($x);
      print "TeamKit : suffixe des pseudos \x22$x\x22 refuse (1 a 3 caracteres parmi lettres, chiffres, + ~ _ . -, dont au moins un + ~ ou - : les pseudos classicube.net ne peuvent pas en contenir, un compte de l autre site ne peut donc jamais prendre le pseudo d un joueur classicube.net) : \x22+\x22 utilise.\n";
      $suffixe = "+";
    }
    print "TeamKit : service de connexion supplementaire : $service (pseudos de ce service suivis de \x22$suffixe\x22, par exemple Pseudo$suffixe ; les joueurs classicube.net gardent leur pseudo).\n";
    if (exists $ecrire{"verify-names"} && $ecrire{"verify-names"} eq "false") {
      print "TeamKit : ATTENTION, verification des pseudos coupee : le service supplementaire ne sert a rien, tout le monde entre sans compte.\n";
    }
  }
  $ecrire{"HeartbeatURL"} = $service ne "" ? "$CCNET,$service" : $CCNET;
}

# Imposes par le template : port et joueurs maximum viennent d AMP (onglet Reseau et Joueurs maximum).
$ecrire{"port"} = $port;
$ecrire{"max-players"} = $joueurs;
# verify-lan-ips : MCGalaxy ne verifie PAS le pseudo d une connexion venant du loopback
# ou d un reseau prive (172.16/12, 10/8, 192.168/16) si cette cle vaut false (defaut).
# En conteneur ponte, c est le cas du relais (127.0.0.1), d un proxy de l hote passe par
# docker-proxy (172.17.0.1) et des autres conteneurs : n importe lequel pourrait entrer
# sous le pseudo du proprietaire. Toujours true ici.
$ecrire{"verify-lan-ips"} = "true";
if (exists $ecrire{"max-guests"} && $ecrire{"max-guests"} > $joueurs) {
  print "TeamKit : places invites ($ecrire{q{max-guests}}) ramenees a joueurs maximum ($joueurs).\n";
  $ecrire{"max-guests"} = $joueurs;
}
if (exists $ecrire{"verify-names"} && $ecrire{"verify-names"} eq "false") {
  print "TeamKit : ATTENTION, verification des pseudos COUPEE : n importe qui peut se connecter sous le pseudo d un admin.\n";
}

# 3. ecriture : on ne remplace que nos lignes, le reste du fichier (commentaires, autres
#    cles, ordre, fins de ligne) est garde tel quel.
my $texte = "";
if (-e $props) {
  open(my $x, "<:raw", $props) or die "ERREUR : lecture de $props impossible\n";
  local $/; $texte = <$x>; close $x;
  $texte = "" unless defined $texte;
}
my @lignes = split /(?<=\n)/, $texte;
for my $cle (sort keys %ecrire) {
  my $val = $ecrire{$cle};
  utf8::encode($val) if utf8::is_utf8($val);
  my $trouve = 0;
  for my $l (@lignes) {
    next if $l =~ /^\s*#/;
    next unless $l =~ /^\s*\Q$cle\E\s*=/i;
    my ($fin) = $l =~ /(\r?\n)\z/;
    $l = "$cle = $val" . (defined $fin ? $fin : "");
    $trouve++;
  }
  next if $trouve;
  if (@lignes && $lignes[-1] !~ /\n\z/) { $lignes[-1] .= "\n" }
  push @lignes, "$cle = $val\n";
}
my $nouveau = join("", @lignes);
if ($nouveau ne $texte) {
  open(my $o, ">:raw", "$props.tmp") or die "ERREUR : ecriture de $props impossible\n";
  print $o $nouveau; close $o or die "ERREUR : ecriture de $props impossible\n";
  rename("$props.tmp", $props) or die "ERREUR : remplacement de $props impossible\n";
}

# 4. properties/authservices.properties, reecrit entierement (meme format que
#    AuthService.SaveServices de MCGalaxy) : un bloc pour classicube.net, sans suffixe,
#    et un pour le service supplementaire. Le sel n y est pas : MCGalaxy en tire un neuf
#    pour chaque service a chaque demarrage.
if ($ecrire_auth) {
  my @blocs = ([$CCNET, ""]);
  push @blocs, [$service, $suffixe] if $service ne "";
  my $texte_auth = join("", map { "$_\n" } (
    "# Authentication services configuration",
    "#   There is no reason to modify these configuration settings, unless the server has been configured",
    "#    to send heartbeats to multiple authentication services (e.g. both ClassiCube.net and BetaCraft.uk)",
    "#   DO NOT EDIT THIS FILE UNLESS YOU KNOW WHAT YOU ARE DOING",
    "#   TeamKit : rewritten by lancer-classicube.sh at every start, from the AMP settings",
    "#    (Connexion par un autre site). Change them in AMP, not here.",
    "",
    "#URL = string",
    "#   URL of the authentication service the following settings apply to",
    "#   (this should be the same as one of the heartbeat URLs specified in server.properties)",
    "#name-suffix = string",
    "#   Characters that are appended to usernames of players that login through the authentication service",
    "#   (used to prevent username collisions between authentication services that would otherwise occur)",
    "#skin-prefix = string",
    "#   Characters that are prefixed to skin name of players that login through the authentication service",
    "#   (used to ensure players from other authentication services see the correct skin)",
    "#mojang-auth = boolean",
    "#   Whether to try verifying users using Mojang\x27s authentication servers if mppass verification fails",
    "#   NOTE: This should only be used for the Betacraft.uk authentication service",
    "",
    map { ("URL = $_->[0]", "name-suffix = $_->[1]", "skin-prefix = ", "mojang-auth = False", "") } @blocs,
  ));
  my $avant = "";
  if (-e $auth) {
    open(my $x, "<:raw", $auth) or die "ERREUR : lecture de $auth impossible\n";
    local $/; $avant = <$x>; close $x;
    $avant = "" unless defined $avant;
  }
  if ($texte_auth ne $avant) {
    open(my $o, ">:raw", "$auth.tmp") or die "ERREUR : ecriture de $auth impossible\n";
    print $o $texte_auth; close $o or die "ERREUR : ecriture de $auth impossible\n";
    rename("$auth.tmp", $auth) or die "ERREUR : remplacement de $auth impossible\n";
  }
}
my $pub = (exists $ecrire{public} && $ecrire{public} eq "false") ? "serveur non liste (lien dans la console)" : "liste publique classicube.net";
print "TeamKit : reglages d AMP recopies dans properties/server.properties (port $port, $joueurs joueurs au plus, $pub).\n";
'
perl -e "$PERL_REGLAGES" "$REGLAGES" "$PROPS" "$PORT" "$JOUEURS" "$AUTH" || exit 1

# ── Relais pour un proxy web (case relais_web) ───────────────────────────────────
# La valeur de la case est seulement comparee a « true » : jamais executee.
RELAIS=$(sed -n 's/^relais_web=\(.*\)$/\1/p' "$REGLAGES" 2>/dev/null | head -n 1 | tr -d '\r[:space:]')
RELAIS_ACTIF=0
if [ "${RELAIS,,}" = true ]; then
  if ! [[ "$RELAIS_PORT" =~ ^[0-9]{1,5}$ ]] || [ "$((10#$RELAIS_PORT))" -lt 1 ] || [ "$((10#$RELAIS_PORT))" -gt 65535 ]; then
    echo "TeamKit : relais pour un proxy web NON demarre : le port du relais (RelayPort) n'est pas arrive sur la ligne de commande. Une instance creee avant l'ajout de ce port ne l'a pas : recree l'instance (le monde se garde par une sauvegarde AMP)."
  elif [ "$((10#$RELAIS_PORT))" -eq "$((10#$PORT))" ]; then
    echo "TeamKit : relais pour un proxy web NON demarre : son port ($RELAIS_PORT) est celui du jeu. Donne-lui un autre port dans l'onglet Reseau d'AMP."
  else
    RELAIS_PORT=$((10#$RELAIS_PORT))
    RELAIS_ACTIF=1
  fi
fi
# Utilise seulement par verifier.py : applique les reglages sans lancer le serveur.
[ -n "$TK_ESSAI_REGLAGES" ] && exit 0

if [ "$RELAIS_ACTIF" = 1 ]; then
  if ! command -v socat >/dev/null 2>&1; then
    echo "TeamKit : relais pour un proxy web NON demarre : socat manque. Il est installe par ExtraContainerPackages a la creation du conteneur : recree l'instance."
  else
    # Ecoute sur le port du relais, une connexion vers 127.0.0.1:<port du jeu> par client
    # (fork). MCGalaxy voit donc 127.0.0.1 et croit l'en-tete X-Real-IP envoye par nginx.
    # --pdeathsig : socat recoit SIGTERM quand son parent s'arrete. Ce parent est ce
    # processus, qui devient MCGalaxy a l'exec plus bas : le relais vit et meurt avec le
    # serveur (un /restart de MCGalaxy garde le meme processus, donc le relais).
    if command -v setpriv >/dev/null 2>&1; then
      setpriv --pdeathsig TERM -- socat TCP-LISTEN:"$RELAIS_PORT",fork,reuseaddr,nodelay TCP:127.0.0.1:"$PORT",nodelay </dev/null &
    else
      echo "TeamKit : setpriv absent de l'image : le relais ne s'arretera qu'avec le conteneur."
      socat TCP-LISTEN:"$RELAIS_PORT",fork,reuseaddr,nodelay TCP:127.0.0.1:"$PORT",nodelay </dev/null &
    fi
    RELAIS_PID=$!
    sleep 1
    if kill -0 "$RELAIS_PID" 2>/dev/null; then
      echo "TeamKit : relais pour un proxy web actif : port $RELAIS_PORT -> 127.0.0.1:$PORT. A ne JAMAIS ouvrir au monde : seul un proxy (nginx) de cette machine doit le joindre (voir le README du template)."
    else
      echo "TeamKit : relais pour un proxy web NON demarre : socat s'est arrete (port $RELAIS_PORT deja pris ?). Le serveur demarre quand meme."
    fi
  fi
fi

# TERM=dumb : le serveur n'ecrit alors aucun code couleur ANSI dans la console d'AMP
# (la console n'est pas un terminal ; les regex du template les tolerent quand meme).
export TERM=dumb
if [ "$MONO" = 1 ]; then
  echo "TeamKit : demarrage de MCGalaxy avec compilateur de plugins (Mono). Plugin : plugins/MonPlugin.cs, puis /pcompile MonPlugin et /pload MonPlugin ici. Pour devenir proprietaire : /rank <ton pseudo ClassiCube> owner."
  # Meme processus (exec) : la console d'AMP arrive sur l'entree du serveur, et le relais
  # (setpriv --pdeathsig) s'arrete avec lui comme avec le binaire autonome.
  exec mono "$ICI/MCGalaxyCLI.exe"
fi
[ -x "$BIN" ] || chmod +x "$BIN"
echo "TeamKit : demarrage de MCGalaxy. Pour devenir proprietaire : /rank <ton pseudo ClassiCube> owner (ici, dans la console)."
exec "$BIN"
