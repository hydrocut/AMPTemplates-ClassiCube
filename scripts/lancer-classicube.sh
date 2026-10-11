#!/bin/bash
# lancer-classicube.sh - pose par le template AMP TeamKit (recree a chaque Update).
# Arguments : <port du jeu> <joueurs maximum>   (ligne de commande d'AMP)
#
# 1. lit les reglages ecrits par AMP (reglages-classicube.txt, une ligne cle=valeur) ;
# 2. les recopie dans properties/server.properties, A CHAQUE demarrage : MCGalaxy reecrit
#    ce fichier lui-meme (au demarrage et a chaque /server ou /main), l'onglet
#    Configuration d'AMP doit donc etre reapplique avant chaque lancement. Seules nos cles
#    sont touchees : une ligne existante est remplacee, une cle absente est ajoutee, le
#    fichier est cree s'il n'existe pas encore (MCGalaxy le complete au demarrage) ;
# 3. remplace ce script par le serveur (exec) : la console d'AMP arrive directement sur
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
export LANG=C.UTF-8 LC_ALL=C.UTF-8

PORT="${1:-25565}"
JOUEURS="${2:-}"
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

if [ -z "$TK_ESSAI_REGLAGES" ] && [ ! -f "$BIN" ]; then
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
my ($fichier, $props, $port, $joueurs) = @ARGV;

# cle du modele AMP => [cle de server.properties, genre, choix possibles]
# version_dev ne sert qu a l Update (installer-classicube.sh) : rien a ecrire.
my %TABLE = (
  version_dev          => [undef,                     "bool"],
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
  my @absentes = grep { !exists $valeurs{$_} } sort keys %TABLE;
  print "TeamKit : reglages absents de reglages-classicube.txt (valeur actuelle gardee) : @absentes\n" if @absentes;
}

# 2. controle et mise en forme de chaque valeur
my %ecrire;
for my $cle (sort keys %valeurs) {
  my ($prop, $genre, $choix) = @{$TABLE{$cle}};
  next unless defined $prop;
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

# Imposes par le template : port et joueurs maximum viennent d AMP (onglet Reseau et Joueurs maximum).
$ecrire{"port"} = $port;
$ecrire{"max-players"} = $joueurs;
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
my $pub = (exists $ecrire{public} && $ecrire{public} eq "false") ? "serveur non liste (lien dans la console)" : "liste publique classicube.net";
print "TeamKit : reglages d AMP recopies dans properties/server.properties (port $port, $joueurs joueurs au plus, $pub).\n";
'
perl -e "$PERL_REGLAGES" "$REGLAGES" "$PROPS" "$PORT" "$JOUEURS" || exit 1
# Utilise seulement par verifier.py : applique les reglages sans lancer le serveur.
[ -n "$TK_ESSAI_REGLAGES" ] && exit 0

[ -x "$BIN" ] || chmod +x "$BIN"
echo "TeamKit : demarrage de MCGalaxy. Pour devenir proprietaire : /rank <ton pseudo ClassiCube> owner (ici, dans la console)."
# TERM=dumb : le Mono embarque n'ecrit alors aucun code couleur ANSI dans la console d'AMP
# (la console n'est pas un terminal ; les regex du template les tolerent quand meme).
export TERM=dumb
exec "$BIN"
