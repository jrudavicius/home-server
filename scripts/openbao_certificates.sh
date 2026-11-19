#!/bin/sh
# Run on the operator's signing machine. Output only the files needed on the Pi.
set -eu
umask 077
[ "$#" = 3 ] || { echo 'Usage: sh openbao_certificates.sh CA_CERT CA_KEY NEW_OUTPUT_DIR' >&2; exit 2; }
ca=$1
signer=$2
out=$3
[ -f "$ca" ] && [ -f "$signer" ] || { echo 'Both CA files are required.' >&2; exit 1; }
mkdir "$out"  # Refuse to replace an existing release.
cp "$ca" "$out/ca.crt"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
trap 'exit 1' HUP INT TERM
issue() {
  name=$1 cn=$2 eku=$3 san=$4
  openssl req -new -newkey rsa:3072 -nodes -subj "/CN=$cn" \
    -keyout "$out/$name.key" -out "$tmp/request"
  cat > "$tmp/extensions" <<EXT
basicConstraints=critical,CA:FALSE
subjectKeyIdentifier=hash
authorityKeyIdentifier=keyid:always,issuer
keyUsage=critical,digitalSignature,keyEncipherment
extendedKeyUsage=$eku
subjectAltName=$san
EXT
  openssl x509 -req -sha256 -days 365 -in "$tmp/request" -CA "$ca" -CAkey "$signer" \
    -set_serial "0x$(openssl rand -hex 16)" -extfile "$tmp/extensions" -out "$out/$name.crt"
}
issue server openbao-server serverAuth DNS:openbao-server,DNS:localhost,IP:127.0.0.1
issue backup openbao-backup clientAuth DNS:openbao-backup
