"""External DMS mirrors (11.1, 11.2): Paperless-ngx and Google Drive over their REST APIs.

The platform index and the S3 original stay authoritative; mirrors are copies. Deletion in the
mirrors follows the retention rules of the index (6.9.5) and is not offered here yet.
"""

import json
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import httpx

DRIVE_FOLDERS = (
    "01_Legitimationsunterlagen",
    "02_Stammakte",
    "03_Buchhaltung",
    "04_Mieterakte",
    "05_Eigentümerakte",
    "06_Sonstiges",
)
DEFAULT_DRIVE_FOLDER = "06_Sonstiges"
_FOLDER_MIME = "application/vnd.google-apps.folder"


class DmsError(Exception):
    """Mirror failed; the message is safe to store (no secrets, no document content)."""


@dataclass
class MirrorMeta:
    document_id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    tenant_slug: str
    property_number: str | None = None
    property_folder: str | None = None  # "NNN Ort, Straße Hausnummer"
    correspondent: str | None = None
    document_type: str | None = None
    drive_folder: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass
class MirrorResult:
    ref: str
    final: bool  # False: accepted, id resolved later (Paperless consumer task)


class DocumentStore(Protocol):
    async def put(self, data: bytes, meta: MirrorMeta) -> MirrorResult: ...

    async def resolve(self, ref: str) -> str | None: ...


@dataclass
class MirrorHit:
    """One document found in a mirror, scoped to a single property (11.2, M20-05)."""

    ref: str
    title: str
    url: str | None = None


def property_folder_name(
    number: str, city: str | None, street: str | None, house: str | None
) -> str:
    """Object folder "NNN Ort, Straße Hausnummer" (11.2, binding structure of the object file)."""
    address = " ".join(p for p in (street, house) if p)
    place = ", ".join(p for p in (city, address) if p)
    return f"{number} {place}".strip()


def _raise_for(response: httpx.Response, what: str) -> None:
    if response.status_code >= 400:
        raise DmsError(f"{what}: HTTP {response.status_code}")


class PaperlessStore:
    """Paperless-ngx REST API with a token per tenant (11.2)."""

    def __init__(self, base_url: str, token: str, client: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"Authorization": f"Token {token}", "Accept": "application/json"}
        self._client = client

    async def _id_for(self, endpoint: str, name: str) -> int:
        url = f"{self._base}/api/{endpoint}/"
        found = await self._client.get(url, params={"name__iexact": name}, headers=self._headers)
        _raise_for(found, f"lookup {endpoint}")
        results = found.json().get("results", [])
        if results:
            return int(results[0]["id"])
        created = await self._client.post(url, json={"name": name}, headers=self._headers)
        _raise_for(created, f"create {endpoint}")
        return int(created.json()["id"])

    async def put(self, data: bytes, meta: MirrorMeta) -> MirrorResult:
        tags = [f"mhvp:tenant:{meta.tenant_slug}", *meta.tags]
        if meta.property_number:
            tags.append(f"objekt:{meta.property_number}")
        form: dict[str, str | list[str]] = {"title": meta.title}
        form["tags"] = [str(await self._id_for("tags", tag)) for tag in tags]
        if meta.correspondent:
            form["correspondent"] = str(await self._id_for("correspondents", meta.correspondent))
        if meta.document_type:
            form["document_type"] = str(await self._id_for("document_types", meta.document_type))
        response = await self._client.post(
            f"{self._base}/api/documents/post_document/",
            data=form,
            files={"document": (meta.filename, data, meta.mime_type)},
            headers=self._headers,
        )
        _raise_for(response, "upload")
        task_id = response.json()
        if not isinstance(task_id, str):
            raise DmsError("upload: unexpected response")
        return MirrorResult(ref=f"task:{task_id}", final=False)

    async def resolve(self, ref: str) -> str | None:
        """Paperless consumes asynchronously; the task yields the document id when done."""
        if not ref.startswith("task:"):
            return ref
        response = await self._client.get(
            f"{self._base}/api/tasks/", params={"task_id": ref[5:]}, headers=self._headers
        )
        _raise_for(response, "task status")
        tasks = response.json()
        task = tasks[0] if isinstance(tasks, list) and tasks else None
        if task is None or task.get("status") in ("PENDING", "STARTED", None):
            return None
        if task.get("status") != "SUCCESS" or task.get("related_document") is None:
            raise DmsError(f"consume: {task.get('status')}")
        return str(task["related_document"])


class GoogleDriveStore:
    """Drive v3 REST API with the technical workspace account (11.2), OAuth refresh token."""

    TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 - endpoint, not a secret
    FILES_URL = "https://www.googleapis.com/drive/v3/files"
    UPLOAD_URL = "https://www.googleapis.com/upload/drive/v3/files"

    def __init__(
        self,
        root_folder_id: str,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        client: httpx.AsyncClient,
    ) -> None:
        self._root = root_folder_id
        self._credentials = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        self._client = client
        self._token: str | None = None

    async def _auth(self) -> dict[str, str]:
        if self._token is None:
            response = await self._client.post(self.TOKEN_URL, data=self._credentials)
            _raise_for(response, "token")
            self._token = str(response.json()["access_token"])
        return {"Authorization": f"Bearer {self._token}"}

    async def _folder(self, parent: str, name: str) -> str:
        escaped = name.replace("\\", "\\\\").replace("'", "\\'")
        query = (
            f"name = '{escaped}' and '{parent}' in parents and mimeType = '{_FOLDER_MIME}' "
            "and trashed = false"
        )
        params = {
            "q": query,
            "fields": "files(id,name)",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        }
        found = await self._client.get(self.FILES_URL, params=params, headers=await self._auth())
        _raise_for(found, "folder lookup")
        files = found.json().get("files", [])
        if files:
            return str(files[0]["id"])
        created = await self._client.post(
            self.FILES_URL,
            params={"supportsAllDrives": "true"},
            json={"name": name, "mimeType": _FOLDER_MIME, "parents": [parent]},
            headers=await self._auth(),
        )
        _raise_for(created, "folder create")
        return str(created.json()["id"])

    async def put(self, data: bytes, meta: MirrorMeta) -> MirrorResult:
        parent = self._root
        if meta.property_folder:
            parent = await self._folder(parent, meta.property_folder)
            folder = (
                meta.drive_folder if meta.drive_folder in DRIVE_FOLDERS else DEFAULT_DRIVE_FOLDER
            )
            parent = await self._folder(parent, folder)
        return await self._upload(data, meta, parent)

    async def file_in_property_year_folder(
        self, data: bytes, meta: MirrorMeta, year: int
    ) -> MirrorResult:
        """Files a document under "<Objektordner>/<Jahr>" (M11-finapi Stage 3, "Als Rechnung
        zuordnen"), scoped to exactly one property; the year folder is created on demand,
        same as every other folder in this store. Distinct from `put`'s fixed
        `DRIVE_FOLDERS` categories (01 to 06): a matched invoice is filed by calendar year
        instead, so `meta.property_folder` is required here."""
        if not meta.property_folder:
            raise DmsError("Kein Objektordner für die Jahresablage bekannt.")
        parent = await self._folder(self._root, meta.property_folder)
        parent = await self._folder(parent, str(year))
        return await self._upload(data, meta, parent)

    async def _upload(self, data: bytes, meta: MirrorMeta, parent: str) -> MirrorResult:
        boundary = f"mhvp{uuid.uuid4().hex}"
        metadata = {
            "name": meta.filename,
            "parents": [parent],
            "description": meta.title,
            "appProperties": {"mhvp_document_id": str(meta.document_id)},
        }
        body = (
            (
                f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                f"{json.dumps(metadata)}\r\n--{boundary}\r\nContent-Type: {meta.mime_type}\r\n\r\n"
            ).encode()
            + data
            + f"\r\n--{boundary}--\r\n".encode()
        )
        response = await self._client.post(
            self.UPLOAD_URL,
            params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id"},
            content=body,
            headers={
                **await self._auth(),
                "Content-Type": f"multipart/related; boundary={boundary}",
            },
        )
        _raise_for(response, "upload")
        return MirrorResult(ref=str(response.json()["id"]), final=True)

    async def resolve(self, ref: str) -> str | None:
        return ref

    async def download(self, ref: str) -> bytes:
        """Original file content for `ref` (a plain Drive file id, the same convention `put`/
        `resolve` use, M35 Stufe 2: a takeover document's `storage_ref` is the objektakte Drive
        file id verbatim, never copied locally, so a download goes through this method instead
        of the S3 `BlobStore`)."""
        response = await self._client.get(
            f"{self.FILES_URL}/{ref}",
            params={"alt": "media", "supportsAllDrives": "true"},
            headers=await self._auth(),
        )
        _raise_for(response, "download")
        return response.content

    async def search(self, property_folder: str, keywords: list[str]) -> list[MirrorHit]:
        """Documents in exactly one object's Drive folder (11.2, M20-05): the query is scoped to
        that folder's subtree and never lists the whole Drive account. Files under the
        Vertretungsakte and every sub folder of ``DRIVE_FOLDERS`` are searched by name."""
        escaped = property_folder.replace("\\", "\\\\").replace("'", "\\'")
        folder_query = (
            f"name = '{escaped}' and '{self._root}' in parents and mimeType = '{_FOLDER_MIME}' "
            "and trashed = false"
        )
        found = await self._client.get(
            self.FILES_URL,
            params={
                "q": folder_query,
                "fields": "files(id,name)",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            },
            headers=await self._auth(),
        )
        _raise_for(found, "folder lookup")
        folders = found.json().get("files", [])
        if not folders:
            return []
        parent = str(folders[0]["id"])
        name_query = " or ".join(f"name contains '{k}'" for k in keywords) if keywords else ""
        query = f"'{parent}' in parents and trashed = false"
        if name_query:
            query += f" and ({name_query})"
        response = await self._client.get(
            self.FILES_URL,
            params={
                "q": query,
                "fields": "files(id,name,webViewLink)",
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
                "corpora": "allDrives",
            },
            headers=await self._auth(),
        )
        _raise_for(response, "search")
        return [
            MirrorHit(ref=str(f["id"]), title=str(f.get("name") or ""), url=f.get("webViewLink"))
            for f in response.json().get("files", [])
        ]
