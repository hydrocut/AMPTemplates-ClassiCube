#!/bin/bash
# installer-classicube.sh - pose par le template AMP TeamKit (recree a chaque Update).
# Arguments : <dossier de l'instance (FullBaseDir cote AMP)> [version_dev : true/false]
#
# Telecharge le serveur MCGalaxy pour Linux depuis le CDN officiel de ClassiCube :
#   - version stable : https://cdn.classicube.net/client/mcg/release/linux64 (par defaut)
#   - version de developpement : https://cdn.classicube.net/client/mcg/latest/linux64
#     (case « Version de developpement » de l'onglet Configuration d'AMP)
# C'est un binaire autonome (Mono embarque) : rien a installer ni a compiler. Il est
# enregistre sous le nom MCGalaxy et rendu executable.
#
# Seul le fichier MCGalaxy est remplace : levels/, ranks/, properties/, plugins/,
# MCGalaxy.db, blockdb/, text/, extra/ et logs/ ne sont jamais touches.
set -u
cd "$1" || { echo "ERREUR : dossier de l'instance introuvable : $1"; exit 1; }
DEV="${2:-}"
MARQUE=.canal-mcgalaxy

# La valeur de la case arrive normalement par la ligne de commande de l'Update. Si AMP ne
# l'a pas remplacee, on prend celle du dernier demarrage (reglages-classicube.txt).
case "${DEV,,}" in
  true|false) ;;
  *)
    DEV=$(sed -n 's/^version_dev=\(.*\)$/\1/p' reglages-classicube.txt 2>/dev/null | head -n 1 | tr -d '\r[:space:]')
    case "${DEV,,}" in
      true|false) echo "Version de developpement : valeur du dernier demarrage ($DEV)." ;;
      *) DEV=false ;;
    esac ;;
esac
if [ "${DEV,,}" = true ]; then CANAL=latest; NOM="de developpement (latest)"; else CANAL=release; NOM="stable (release)"; fi
URL="https://cdn.classicube.net/client/mcg/$CANAL/linux64"

if ! command -v curl >/dev/null 2>&1; then
  echo "ERREUR : curl manque. Cette instance doit tourner en conteneur : curl est installe par ExtraContainerPackages."
  exit 1
fi

ANCIEN=$(cat "$MARQUE" 2>/dev/null)
if [ "$ANCIEN" = latest ] && [ "$CANAL" = release ] && [ -f MCGalaxy ]; then
  echo "ATTENTION : retour de la version de developpement a la version stable. Si le serveur refuse de demarrer ou si des cartes ont disparu, restaure la sauvegarde AMP faite avant le passage en developpement."
fi

echo "Telechargement de MCGalaxy, version $NOM (environ 20 Mo, cdn.classicube.net)..."
rm -f MCGalaxy.nouveau
if ! curl -fsSL --retry 3 --connect-timeout 20 -R -o MCGalaxy.nouveau "$URL"; then
  rm -f MCGalaxy.nouveau
  if [ -f MCGalaxy ]; then
    echo "ATTENTION : cdn.classicube.net ne repond pas : on garde le serveur deja installe. Relance Update plus tard."
    exit 0
  fi
  echo "ERREUR : telechargement impossible ($URL). Relance Update dans quelques minutes."
  exit 1
fi

# Controle : un vrai executable Linux (ELF) d'au moins 5 Mo, pas une page d'erreur.
TAILLE=$(stat -c %s MCGalaxy.nouveau 2>/dev/null || echo 0)
SIGNATURE=$(head -c 4 MCGalaxy.nouveau | od -An -tx1 | tr -d ' \n')
if [ "$SIGNATURE" != 7f454c46 ] || [ "$TAILLE" -lt 5000000 ]; then
  rm -f MCGalaxy.nouveau
  echo "ERREUR : le fichier recu n'est pas le serveur MCGalaxy pour Linux ($TAILLE octets). Rien n'a ete change."
  exit 1
fi
chmod 755 MCGalaxy.nouveau
DATE=$(date -r MCGalaxy.nouveau '+%d/%m/%Y' 2>/dev/null)
if [ -f MCGalaxy ] && cmp -s MCGalaxy MCGalaxy.nouveau; then
  rm -f MCGalaxy.nouveau
  chmod 755 MCGalaxy
  echo "$CANAL" > "$MARQUE"
  echo "MCGalaxy $NOM deja a jour (publie le $DATE) : rien a faire."
  exit 0
fi
mv -f MCGalaxy.nouveau MCGalaxy || { echo "ERREUR : remplacement de MCGalaxy impossible."; exit 1; }
echo "$CANAL" > "$MARQUE"
echo "Serveur MCGalaxy $NOM installe (publie le $DATE). Numero de version : /serverinfo dans la console."
