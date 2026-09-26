#!/usr/bin/env bash
# SSH-Härtung des Betreiberservers (M9-05), idempotent.
# Aufruf als root:  bash harden-ssh.sh "ssh-ed25519 AAAA... kommentar"
# Vorher eine Kontrollverbindung offen lassen, siehe docs/runbooks/server-recovery-und-haertung.md.
set -euo pipefail

readonly AUTH_DIR=/root/.ssh
readonly AUTH_FILE="${AUTH_DIR}/authorized_keys"
readonly DROPIN=/etc/ssh/sshd_config.d/10-mhvp-hardening.conf
readonly CLOUD_CFG=/etc/cloud/cloud.cfg.d/99-mhvp.cfg
readonly CLOUD_DISABLED=/etc/cloud/cloud-init.disabled

die() { echo "FEHLER: $*" >&2; exit 1; }

[[ $# -ge 1 && -n "${1:-}" ]] || die "Kein öffentlicher Schlüssel angegeben. Aufruf: $0 \"ssh-ed25519 AAAA... kommentar\""
[[ ${EUID} -eq 0 ]] || die "Bitte als root ausführen."

pubkey="$1"
case "${pubkey}" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*\ *|sk-ssh-ed25519@openssh.com\ *|sk-ecdsa-sha2-*\ *) ;;
  *) die "Argument sieht nicht wie ein öffentlicher SSH-Schlüssel aus." ;;
esac
if [[ "${pubkey}" == *"PRIVATE KEY"* ]]; then
  die "Das ist ein privater Schlüssel. Nur den öffentlichen Schlüssel übergeben."
fi

tmpkey="$(mktemp)"
trap 'rm -f "${tmpkey}"' EXIT
printf '%s\n' "${pubkey}" > "${tmpkey}"
ssh-keygen -lf "${tmpkey}" >/dev/null 2>&1 || die "Schlüssel ist ungültig (ssh-keygen -lf)."

# 1. Schlüssel eintragen (vor dem Abschalten der Passwortanmeldung)
install -d -m 700 "${AUTH_DIR}"
touch "${AUTH_FILE}"
chmod 600 "${AUTH_FILE}"
key_body="$(awk '{print $1" "$2}' "${tmpkey}")"
if grep -qF -- "${key_body}" "${AUTH_FILE}"; then
  echo "Schlüssel bereits in ${AUTH_FILE} vorhanden."
else
  printf '%s\n' "${pubkey}" >> "${AUTH_FILE}"
  echo "Schlüssel in ${AUTH_FILE} eingetragen."
fi

# 2. sshd-Drop-in schreiben
install -d -m 755 "$(dirname "${DROPIN}")"
backup=""
if [[ -f "${DROPIN}" ]]; then
  backup="$(mktemp)"
  cp -p "${DROPIN}" "${backup}"
fi
cat > "${DROPIN}" <<'CONF'
# Verwaltet durch scripts/server/harden-ssh.sh (M9-05). Nicht von Hand ändern.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
PubkeyAuthentication yes
CONF
chmod 644 "${DROPIN}"

# 3. Konfiguration prüfen, bei Fehler zurückrollen
if ! sshd -t; then
  if [[ -n "${backup}" ]]; then cp -p "${backup}" "${DROPIN}"; else rm -f "${DROPIN}"; fi
  die "sshd -t meldet Fehler, Drop-in zurückgerollt. sshd wurde nicht neu geladen."
fi
if [[ -n "${backup}" ]]; then rm -f "${backup}"; fi

# 4. sshd neu laden (Dienstname je nach Version ssh oder sshd)
if systemctl list-unit-files ssh.service >/dev/null 2>&1 && systemctl is-enabled ssh.service >/dev/null 2>&1; then
  systemctl reload ssh.service
elif systemctl list-unit-files sshd.service >/dev/null 2>&1; then
  systemctl reload sshd.service
else
  die "Weder ssh.service noch sshd.service gefunden."
fi
echo "sshd neu geladen."

# 5. cloud-init stilllegen
if [[ -d /etc/cloud ]]; then
  touch "${CLOUD_DISABLED}"
  install -d -m 755 "$(dirname "${CLOUD_CFG}")"
  cat > "${CLOUD_CFG}" <<'CFG'
# Verwaltet durch scripts/server/harden-ssh.sh (M9-05).
# Rückfallebene, falls /etc/cloud/cloud-init.disabled entfernt wird.
ssh_deletekeys: false
preserve_hostname: true
ssh_pwauth: false
chpasswd:
  expire: false
CFG
  echo "cloud-init deaktiviert (${CLOUD_DISABLED}, ${CLOUD_CFG})."
else
  echo "Kein /etc/cloud vorhanden, cloud-init wird übersprungen."
fi

cat <<'HINWEIS'

Prüfhinweise:
  1. Kontrollverbindung offen lassen.
  2. In einem zweiten Terminal: ssh -i <privater-schlüssel> root@<server-ip>
  3. Passwortanmeldung muss scheitern:
       ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password root@<server-ip>
  4. Wirksame Werte:
       sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication)'
  5. Erst danach die Kontrollverbindung schließen.
  6. IONOS-Firewall (nur 22, 80, 443) und Offsite-Backup: siehe Runbook, Abschnitte C4 und D.
HINWEIS
