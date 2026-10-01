# Optionaler Python-Client für Bestandstools (S12-07)

Der Python-Client wird bei Bedarf aus `apps/api/openapi.json` erzeugt. Er ist nicht eingecheckt
(`.gitignore`), damit er nie vom Schema abweicht.

## Erzeugen

```
make openapi      # nur falls die Spezifikation neu exportiert werden soll
make client-py    # ruft scripts/gen_python_client.sh auf
```

Das Skript startet `openapi-python-client` (Version fest gepinnt, Standard 0.29.1, überschreibbar
über `OPENAPI_PYTHON_CLIENT_VERSION`) per `uvx`. Dadurch ändert sich das Lockfile der API nicht.
Beim ersten Lauf ist Netzzugang zum Paketindex nötig. Ausgabe: `packages/api-client-py`.
Prüfung ohne Netz: `sh scripts/gen_python_client.sh --help`.

Der Generator meldet für wenige Schemas mit zirkulären oder doppelt benannten Referenzen
Warnungen und lässt diese Modelle aus (zuletzt `ImmowareSyncRunOut`). Der Lauf endet dennoch
mit Exit 0.

## Beispiel

```python
import httpx
from mhvp_api_client import AuthenticatedClient

client = AuthenticatedClient(
    base_url="https://api.example.invalid",
    token="<API-Token, nie im Code ablegen>",
)
# Funktionen je Endpunkt: mhvp_api_client.api.<tag>.<operation>.sync(client=client)
```

Hinweis: Das Schema deklariert kein Security Scheme, Authentifizierung und Mandantenbezug richten sich nach der API-Dokumentation (Beispielwerte sind Platzhalter).
Der Client ersetzt keine Gates oder Berechtigungen, die Sperren der API gelten unverändert.
