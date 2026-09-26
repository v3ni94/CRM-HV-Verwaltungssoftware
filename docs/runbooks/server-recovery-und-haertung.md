# Server: Zugang wiederherstellen, Ursache prüfen, Härtung, Backup

Stand 26.09.2026. Betreiberserver: IONOS Dedicated Server, Ubuntu 26.04, cloud-init, Docker,
Traefik. Anlass: Nach einem Neustart waren die SSH-Hostschlüssel neu erzeugt, das Root-Passwort
ungültig und der SSH-Dienst zeitweise nicht erreichbar ("connection refused"), die Container liefen
weiter. Vermutete Ursache: cloud-init hat den Neustart wie einen Erststart behandelt
(`ssh_deletekeys`, `set_passwords`). Offener Punkt: M9-05 in `docs/OPEN_QUESTIONS.md`.

Keine Passwörter, privaten Schlüssel oder Panel-Zugangsdaten in dieses Dokument, Tickets oder Git.

## A. Zugang wiederherstellen

Die Schritte der Reihe nach versuchen, beim ersten Erfolg zu Abschnitt B wechseln.

Vorab auf dem Arbeitsrechner den alten Hostschlüssel entfernen, sonst verweigert der Client die
Verbindung wegen geänderter Hostschlüssel:

    ssh-keygen -R <server-ip>

Den neuen Fingerabdruck beim ersten Verbinden nur akzeptieren, wenn er mit dem in der KVM-Konsole
angezeigten Wert übereinstimmt (`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub`).

### A1. Initial-Passwort aus dem IONOS-Panel

1. Im Panel unter Server, Zugangsdaten das Initial-Passwort anzeigen lassen.
2. `ssh root@<server-ip>` mit diesem Passwort. Bei "connection refused" einige Minuten warten und
   erneut versuchen (sshd startet nach der Hostschlüssel-Erzeugung verzögert).
3. Nach erfolgreicher Anmeldung sofort ein neues Passwort setzen (`passwd`) und den im Panel
   hinterlegten öffentlichen Schlüssel in `/root/.ssh/authorized_keys` eintragen (oder direkt
   `scripts/server/harden-ssh.sh`, siehe Abschnitt C, aber erst nach der Ursachenprüfung).

### A2. KVM-Konsole (Remote-Konsole im Panel)

1. Im Panel die KVM- bzw. Remote-Konsole öffnen.
2. Hinweis: Die Konsole arbeitet mit US-Tastaturlayout. Auf deutscher Tastatur sind z. B. `y` und
   `z` vertauscht, `-` liegt auf `ß`, `/` auf `-`, `:` auf `Ö` mit Umschalt. Passwörter vorher
   entsprechend übersetzen oder vorübergehend ein einfaches, nur aus Buchstaben und Ziffern
   bestehendes Passwort verwenden und danach per SSH ändern.
3. Als root mit dem Initial-Passwort anmelden, `passwd` ausführen, Schlüssel eintragen, sshd prüfen
   (`systemctl status ssh`, `sshd -t`).

### A3. Rettungssystem des Panels

1. Im Panel das Rettungssystem (Rescue) aktivieren und den Server daraus neu starten. Das
   Rettungssystem-Passwort zeigt das Panel an. Die Container sind in dieser Zeit nicht erreichbar.
2. Anmelden: `ssh root@<server-ip>` mit dem Rettungssystem-Passwort.
3. Root-Dateisystem finden und mounten:

       lsblk -f
       # bei Software-RAID: mdadm --assemble --scan ; bei LVM: vgchange -ay
       mount /dev/<root-partition> /mnt
       for d in dev proc sys run; do mount --rbind "/$d" "/mnt/$d"; done
       chroot /mnt /bin/bash

4. Im chroot:

       passwd root
       install -d -m 700 /root/.ssh
       echo '<öffentlicher-schlüssel>' >> /root/.ssh/authorized_keys
       chmod 600 /root/.ssh/authorized_keys
       sshd -t && echo "sshd-Konfiguration gültig"
       touch /etc/cloud/cloud-init.disabled   # verhindert erneutes Zurücksetzen, siehe C1

5. chroot verlassen (`exit`), `umount -R /mnt`, im Panel das Rettungssystem deaktivieren und neu
   starten. Danach Anmeldung per Schlüssel testen.

## B. Ursache prüfen

Als root auf dem Server ausführen und die Ausgabe sichern (lokal, nicht in Tickets mit Passwörtern):

    {
      echo "== Hostschlüssel";   ls -l --time-style=full-iso /etc/ssh/ssh_host_*
      echo "== shadow";          ls -l --time-style=full-iso /etc/shadow; chage -l root
      echo "== Boot-Verlauf";    last -x reboot | head -5
      echo "== cloud-init";      cloud-init status --long 2>/dev/null
      grep -nE 'ssh_deletekeys|set_passwords|cc_set_passwords|cc_ssh|new instance|instance-id' \
        /var/log/cloud-init.log | tail -40
      ls -l --time-style=full-iso /var/lib/cloud/instances/ 2>/dev/null
      echo "== SSH-Anmeldungen"; journalctl -u ssh -u sshd --since '-7 days' --no-pager \
        | grep -E 'Accepted|Failed|Invalid user' | tail -60
      echo "== authorized_keys"; for f in /root/.ssh/authorized_keys /home/*/.ssh/authorized_keys; do
        [ -f "$f" ] && { ls -l --time-style=full-iso "$f"; ssh-keygen -lf "$f"; }; done
      echo "== Konten mit UID 0"; awk -F: '$3==0' /etc/passwd
      echo "== Offene Ports";    ss -tulpn
    } 2>&1 | tee "/root/ursachenpruefung-$(date +%Y%m%d-%H%M).txt"

Erwartung bei harmloser Ursache: Die Zeitstempel von Hostschlüsseln und `/etc/shadow` liegen
wenige Sekunden nach dem Neustart, `cloud-init.log` zeigt im selben Zeitfenster die Module
`ssh` (mit Löschen der Schlüssel) und `set_passwords`, oft mit neuer instance-id.

| Befund | Einschätzung | Maßnahme |
|---|---|---|
| Zeitstempel Hostschlüssel und shadow = Bootzeit, cloud-init.log zeigt ssh_deletekeys/set_passwords, neue instance-id | harmlos, cloud-init-Erststartverhalten | Abschnitt C umsetzen |
| Nur `Failed`/`Invalid user` von fremden IPs, kein `Accepted` außer eigenen IPs | übliche Scans, harmlos | Abschnitt C, fail2ban |
| `Accepted` von unbekannter IP oder zu unbekannter Zeit | Verdacht auf Kompromittierung | Server vom Netz (Panel-Firewall), Beweise sichern, Neuinstallation, alle Secrets rotieren, Geschäftsführung und Datenschutz informieren |
| Unbekannte Schlüssel in authorized_keys oder weitere Konten mit UID 0 | Kompromittierung wahrscheinlich | wie oben |
| shadow oder Hostschlüssel geändert ohne passenden cloud-init-Eintrag und ohne Neustart | ungeklärt, Kompromittierung nicht ausgeschlossen | wie oben, bis geklärt keine echten Daten importieren |
| Unerwartete lauschende Ports oder Prozesse in `ss -tulpn` | Verdacht | Prozess identifizieren (`ls -l /proc/<pid>/exe`), im Zweifel wie oben |

Die Einschätzung ersetzt keine forensische Prüfung. Bei Verdacht einen Dienstleister hinzuziehen;
eine mögliche Meldepflicht nach DSGVO ist mit dem Datenschutzverantwortlichen zu klären.

## C. Härtung

Automatisiert über `scripts/server/harden-ssh.sh` (Schritte C1 und C2). Ablauf:

1. Kontrollverbindung: eine SSH-Sitzung als root offen lassen, bis alles geprüft ist.
2. `scp scripts/server/harden-ssh.sh root@<server-ip>:/root/` und
   `bash /root/harden-ssh.sh "ssh-ed25519 AAAA... betreiber@arbeitsplatz"`.
3. In einem zweiten Terminal `ssh -i <privater-schlüssel> root@<server-ip>` testen. Erst wenn das
   gelingt, die Kontrollverbindung schließen.

Das Skript trägt den Schlüssel ein, bevor die Passwortanmeldung abgeschaltet wird. Wer die Schritte
von Hand ausführt, hält dieselbe Reihenfolge ein: Schlüssel eintragen, Schlüssel-Login in zweitem
Terminal testen, erst danach das Drop-in aktivieren.

### C1. cloud-init nach der Erstinstallation stilllegen

Bevorzugt vollständig:

    touch /etc/cloud/cloud-init.disabled

Alternative, falls cloud-init weiterlaufen soll (z. B. für Netzwerkkonfiguration durch IONOS),
Datei `/etc/cloud/cloud.cfg.d/99-mhvp.cfg`:

    ssh_deletekeys: false
    preserve_hostname: true
    ssh_pwauth: false
    chpasswd:
      expire: false

Das Skript legt beides an: die Sperrdatei und als Rückfallebene die cfg-Datei.

### C2. SSH nur per Schlüssel

Drop-in `/etc/ssh/sshd_config.d/10-mhvp-hardening.conf`:

    PasswordAuthentication no
    KbdInteractiveAuthentication no
    PermitRootLogin prohibit-password
    PubkeyAuthentication yes

Hinweis: sshd übernimmt den ersten gefundenen Wert. Drop-ins werden über `Include` am Anfang der
`sshd_config` gelesen und in Namensreihenfolge ausgewertet. Eine Datei wie
`50-cloud-init.conf` mit `PasswordAuthentication yes` wird deshalb von `10-...` übersteuert.
Wirksamkeit prüfen:

    sshd -T | grep -Ei '^(passwordauthentication|permitrootlogin|kbdinteractiveauthentication)'

### C3. fail2ban

Falls installiert (`systemctl status fail2ban`): Jail `sshd` aktivieren und prüfen
(`fail2ban-client status sshd`). Die Installation eines neuen Pakets ist mit dem Betreiber
abzustimmen; bei reiner Schlüsselanmeldung ist fail2ban eine Ergänzung, keine Voraussetzung.

### C4. IONOS-Firewall-Richtlinie

Im Panel eine Firewall-Richtlinie für den Server anlegen, eingehend nur TCP 22, 80, 443 erlauben,
alles andere verwerfen. Port 22 nach Möglichkeit auf die festen IPs des Betreibers beschränken.
Danach `ss -tulpn` und ein Portscan von außen zum Abgleich. Docker veröffentlicht Ports an der
Host-Firewall (ufw) vorbei, die Panel-Firewall wirkt davor und ist deshalb maßgeblich.

## D. Backup

* Das Cloud Backup im IONOS-Panel ist nicht aktiv. Es gibt kein Server-Abbild beim Anbieter.
* Vorhanden auf dem Server:
  * `mhvp-backup.service` mit Timer: verschlüsselte Datenbank- und Dokumentensicherung nach
    `/srv/mhvp-backup` (siehe `docs/runbooks/server-setup.md`, Abschnitt 5).
  * Hub-Backup: `/var/backups/immoware-hub/daily/` (siehe `docs/runbooks/hub-abschaltung.md`).
* Beide liegen auf demselben Server. Bei Hardwaredefekt, Kompromittierung oder Neuinstallation sind
  sie verloren.
* Empfehlung: Offsite-Kopie einrichten (`BACKUP_REMOTE` in `.env.backup`, z. B. per rsync auf
  einen getrennten Speicher mit eigenem Zugang), echtes age-Schlüsselpaar erzeugen (privater
  Schlüssel außerhalb des Servers) und einen Wiederherstellungstest dokumentieren. Zusätzlich
  prüfen, ob das Cloud Backup des Panels wirtschaftlich sinnvoll ist. Alles vor dem Import echter
  Daten aus Immoware24 (M9-05).
