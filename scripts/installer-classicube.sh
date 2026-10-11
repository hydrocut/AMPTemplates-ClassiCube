#!/bin/bash
# installer-classicube.sh - pose par le template AMP TeamKit (recree a chaque Update).
# Arguments : <dossier de l'instance (FullBaseDir cote AMP)> [version_dev : true/false] [compilateur : true/false]
#
# Telecharge le serveur MCGalaxy depuis le CDN officiel de ClassiCube :
#   - version stable : https://cdn.classicube.net/client/mcg/release/... (par defaut)
#   - version de developpement : https://cdn.classicube.net/client/mcg/latest/...
#     (case « Version de developpement » de l'onglet Configuration d'AMP)
# Deux formes du meme serveur, selon la case « Compilateur de plugins » :
#   - decochee (defaut) : linux64, binaire autonome (.NET embarque) enregistre sous le nom
#     MCGalaxy. Rien a installer, mais /pcompile et /compile n'existent pas dans cette forme.
#   - cochee : net40/MCGalaxy_.dll + net40/MCGalaxyCLI.exe, lances par Mono (paquets
#     mono-runtime et mono-mcs du conteneur, ExtraContainerPackages). Meme version, memes
#     fichiers de donnees, et /pcompile <nom> compile plugins/<nom>.cs sur place (mcs).
#
# Seuls MCGalaxy, MCGalaxy_.dll et MCGalaxyCLI.exe sont remplaces : levels/, ranks/,
# properties/, plugins/, MCGalaxy.db, blockdb/, text/, extra/ et logs/ ne sont jamais touches.
set -u
cd "$1" || { echo "ERREUR : dossier de l'instance introuvable : $1"; exit 1; }
DEV="${2:-}"
COMPIL="${3:-}"
MARQUE=.canal-mcgalaxy

# Les valeurs des cases arrivent normalement par la ligne de commande de l'Update. Si AMP ne
# les a pas remplacees, on prend celles du dernier demarrage (reglages-classicube.txt).
case_cochee() { # <valeur recue> <cle de reglages-classicube.txt> -> affiche true ou false
  local v="$1"
  case "${v,,}" in true|false) echo "${v,,}"; return ;; esac
  v=$(sed -n "s/^$2=\\(.*\\)\$/\\1/p" reglages-classicube.txt 2>/dev/null | head -n 1 | tr -d '\r[:space:]')
  case "${v,,}" in
    true|false) echo "Case $2 : valeur du dernier demarrage ($v)." >&2; echo "${v,,}" ;;
    *) echo false ;;
  esac
}
DEV=$(case_cochee "$DEV" version_dev)
COMPIL=$(case_cochee "$COMPIL" compilateur)
if [ "$DEV" = true ]; then CANAL=latest; NOM="de developpement (latest)"; else CANAL=release; NOM="stable (release)"; fi
BASE="https://cdn.classicube.net/client/mcg/$CANAL"

if ! command -v curl >/dev/null 2>&1; then
  echo "ERREUR : curl manque. Cette instance doit tourner en conteneur : curl est installe par ExtraContainerPackages."
  exit 1
fi

ANCIEN=$(cat "$MARQUE" 2>/dev/null)
if [ "$ANCIEN" = latest ] && [ "$CANAL" = release ] && { [ -f MCGalaxy ] || [ -f MCGalaxy_.dll ]; }; then
  echo "ATTENTION : retour de la version de developpement a la version stable. Si le serveur refuse de demarrer ou si des cartes ont disparu, restaure la sauvegarde AMP faite avant le passage en developpement."
fi

# telecharger <url> <fichier final> <signature hexa des 4 premiers octets ou 2> <taille minimale>
# Ecrit <fichier>.nouveau et le controle ; renvoie 0 (pret), 2 (CDN muet) ou 1 (fichier refuse).
telecharger() {
  rm -f "$2.nouveau"
  if ! curl -fsSL --retry 3 --connect-timeout 20 -R -o "$2.nouveau" "$1"; then
    rm -f "$2.nouveau"
    return 2
  fi
  local taille signature
  taille=$(stat -c %s "$2.nouveau" 2>/dev/null || echo 0)
  signature=$(head -c $(( ${#3} / 2 )) "$2.nouveau" | od -An -tx1 | tr -d ' \n')
  if [ "$signature" != "$3" ] || [ "$taille" -lt "$4" ]; then
    rm -f "$2.nouveau"
    echo "ERREUR : le fichier recu pour $2 n'est pas celui attendu ($taille octets). Rien n'a ete change."
    return 1
  fi
  return 0
}

# poser <fichier> : remplace le fichier par sa version .nouveau ; renvoie 0 si c'etait le meme.
poser() {
  if [ -f "$1" ] && cmp -s "$1" "$1.nouveau"; then rm -f "$1.nouveau"; return 0; fi
  mv -f "$1.nouveau" "$1" || { echo "ERREUR : remplacement de $1 impossible."; exit 1; }
  return 1
}

if [ "$COMPIL" = true ]; then
  # Forme Mono : la bibliotheque du serveur et son lanceur en console, toujours ensemble.
  echo "Telechargement de MCGalaxy $NOM avec compilateur de plugins (environ 1,6 Mo, cdn.classicube.net)..."
  echo "  Plugins : depose MonPlugin.cs dans plugins/, puis /pcompile MonPlugin et /pload MonPlugin dans la console."
  for f in MCGalaxy_.dll MCGalaxyCLI.exe; do
    case $f in MCGalaxy_.dll) min=500000 ;; *) min=4000 ;; esac
    telecharger "$BASE/net40/$f" "$f" 4d5a "$min"
    code=$?
    if [ "$code" != 0 ]; then
      rm -f MCGalaxy_.dll.nouveau MCGalaxyCLI.exe.nouveau
      [ "$code" = 1 ] && exit 1
      if [ -f MCGalaxy_.dll ] && [ -f MCGalaxyCLI.exe ]; then
        echo "ATTENTION : cdn.classicube.net ne repond pas : on garde le serveur deja installe. Relance Update plus tard."
        exit 0
      fi
      echo "ERREUR : telechargement impossible ($BASE/net40/$f). Relance Update dans quelques minutes."
      exit 1
    fi
  done
  DATE=$(date -r MCGalaxy_.dll.nouveau '+%d/%m/%Y' 2>/dev/null)
  poser MCGalaxy_.dll; MEME_DLL=$?
  poser MCGalaxyCLI.exe; MEME_CLI=$?
  echo "$CANAL" > "$MARQUE"
  if [ "$MEME_DLL" = 0 ] && [ "$MEME_CLI" = 0 ]; then
    echo "MCGalaxy $NOM avec compilateur deja a jour (publie le $DATE) : rien a faire."
  else
    echo "Serveur MCGalaxy $NOM avec compilateur installe (publie le $DATE). Numero de version : /serverinfo dans la console."
  fi
  if ! command -v mono >/dev/null 2>&1; then
    echo "ATTENTION : Mono n'est pas encore dans le conteneur. Il est installe a son prochain demarrage (paquets du template) : redemarre l'instance apres cet Update."
  fi
  exit 0
fi

echo "Telechargement de MCGalaxy, version $NOM (environ 20 Mo, cdn.classicube.net)..."
telecharger "$BASE/linux64" MCGalaxy 7f454c46 5000000
code=$?
if [ "$code" != 0 ]; then
  [ "$code" = 1 ] && exit 1
  if [ -f MCGalaxy ]; then
    echo "ATTENTION : cdn.classicube.net ne repond pas : on garde le serveur deja installe. Relance Update plus tard."
    exit 0
  fi
  echo "ERREUR : telechargement impossible ($BASE/linux64). Relance Update dans quelques minutes."
  exit 1
fi
chmod 755 MCGalaxy.nouveau
DATE=$(date -r MCGalaxy.nouveau '+%d/%m/%Y' 2>/dev/null)
if poser MCGalaxy; then
  chmod 755 MCGalaxy
  echo "$CANAL" > "$MARQUE"
  echo "MCGalaxy $NOM deja a jour (publie le $DATE) : rien a faire."
  exit 0
fi
echo "$CANAL" > "$MARQUE"
echo "Serveur MCGalaxy $NOM installe (publie le $DATE). Numero de version : /serverinfo dans la console."
