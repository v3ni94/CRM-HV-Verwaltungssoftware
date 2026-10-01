"""External DMS mirrors (11.1, 11.2): Paperless-ngx and Google Drive over their REST APIs.

The platform index and the S3 original stay authoritative; mirrors are copies. Deletion in the
mirrors follows the retention rules of the index (6.9.5) and the operator decision of
26.09.2026 (M6-03): ``GoogleDriveStore.delete`` (fallback ``trash``) and
``PaperlessStore.add_tag`` (tag ``gelöscht``, the Paperless document is kept) are only ever
called by ``mhvp.documents.mirror_deletion`` after the platform deletion (released profile,
expired retention, no hold) and every call is logged as a domain event (A43).
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
    entity_type: str | None = None  # Paperless custom fields (11.2, M6-07)
    entity_id: str | None = None


@dataclass
class MirrorResult:
    ref: str
    final: bool  # False: accepted, id resolved later (Paperless consumer task)


class DocumentStore(Protocol):
    async def put(self, data: bytes, meta: MirrorMeta) -> MirrorResult: ...

    async def resolve(self, ref: str) -> str | None: ...

    async def delete(self, ref: str) -> bool:
        """Remove the mirrored copy; True when deleted now, False when it was already gone."""
        ...

    async def update_meta(self, ref: str, meta: MirrorMeta) -> bool:
        """Push changed metadata (title, category, link) to the copy (11.2, M6-06); False when
        the copy no longer exists."""
        ...


@dataclass(frozen=True)
class InboxFile:
    """One file of a Drive inbox folder (A42, `GoogleDriveStore.list_folder`)."""

    ref: str
    name: str
    mime_type: str
    modified_at: str  # RFC 3339 as Drive returns it; used as the intake watermark
    size: int | None = None


@dataclass(frozen=True)
class DriveChange:
    """One entry of the Drive Changes API (11.2 ``subscribe_changes``, M6-05)."""

    file_id: str
    removed: bool  # removed from the account or moved to the trash
    name: str | None = None
    modified_at: str | None = None


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

    async def delete(self, ref: str) -> bool:
        if ref.startswith("task:") or not ref.isdigit():
            raise DmsError("delete: reference is not a Paperless document id")
        response = await self._client.delete(
            f"{self._base}/api/documents/{ref}/", headers=self._headers
        )
        if response.status_code == 404:
            return False
        _raise_for(response, "delete")
        return True

    async def add_tag(self, ref: str, name: str) -> bool:
        """Assign the tag ``name`` (created when missing) to the Paperless document ``ref``.

        Operator decision 26.09.2026 (M6-03): a document deleted in the platform stays in
        Paperless and is marked with the tag ``gelöscht`` instead. Returns True when the tag is
        set now or was already set, False when the Paperless document no longer exists."""
        if ref.startswith("task:") or not ref.isdigit():
            raise DmsError("tag: reference is not a Paperless document id")
        url = f"{self._base}/api/documents/{ref}/"
        current = await self._client.get(url, headers=self._headers)
        if current.status_code == 404:
            return False
        _raise_for(current, "tag lookup")
        tags = [int(t) for t in current.json().get("tags", [])]
        tag_id = await self._id_for("tags", name)
        if tag_id in tags:
            return True
        response = await self._client.patch(
            url, json={"tags": [*tags, tag_id]}, headers=self._headers
        )
        _raise_for(response, "tag")
        return True

    async def _custom_field_id(self, name: str) -> int:
        url = f"{self._base}/api/custom_fields/"
        found = await self._client.get(url, params={"name__iexact": name}, headers=self._headers)
        _raise_for(found, "lookup custom_fields")
        results = found.json().get("results", [])
        if results:
            return int(results[0]["id"])
        created = await self._client.post(
            url, json={"name": name, "data_type": "string"}, headers=self._headers
        )
        _raise_for(created, "create custom_fields")
        return int(created.json()["id"])

    async def update_meta(self, ref: str, meta: MirrorMeta) -> bool:
        """PATCH title, document type, correspondent, category tags and the custom fields
        ``entity_type`` and ``entity_id`` (11.2, M6-06, M6-07). Existing tags stay."""
        if ref.startswith("task:") or not ref.isdigit():
            raise DmsError("update_meta: reference is not a Paperless document id")
        url = f"{self._base}/api/documents/{ref}/"
        current = await self._client.get(url, headers=self._headers)
        if current.status_code == 404:
            return False
        _raise_for(current, "meta lookup")
        payload: dict[str, object] = {"title": meta.title}
        if meta.correspondent:
            payload["correspondent"] = await self._id_for("correspondents", meta.correspondent)
        if meta.document_type:
            payload["document_type"] = await self._id_for("document_types", meta.document_type)
        tags = [int(t) for t in current.json().get("tags", [])]
        for name in meta.tags:
            tag_id = await self._id_for("tags", name)
            if tag_id not in tags:
                tags.append(tag_id)
        payload["tags"] = tags
        if meta.entity_type and meta.entity_id:
            fields = {
                int(f["field"]): f.get("value") for f in current.json().get("custom_fields", [])
            }
            fields[await self._custom_field_id("entity_type")] = meta.entity_type
            fields[await self._custom_field_id("entity_id")] = meta.entity_id
            payload["custom_fields"] = [{"field": k, "value": v} for k, v in fields.items()]
        response = await self._client.patch(url, json=payload, headers=self._headers)
        _raise_for(response, "update_meta")
        return True


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

    async def delete(self, ref: str) -> bool:
        response = await self._client.delete(
            f"{self.FILES_URL}/{ref}",
            params={"supportsAllDrives": "true"},
            headers=await self._auth(),
        )
        if response.status_code == 404:
            return False
        _raise_for(response, "delete")
        return True

    async def update_meta(self, ref: str, meta: MirrorMeta) -> bool:
        """Description and the mhvp appProperties follow the index; the file stays in its folder
        (moving between category folders is not mirrored, M6-06)."""
        properties = {"mhvp_document_id": str(meta.document_id)}
        if meta.entity_type and meta.entity_id:
            properties.update(mhvp_entity_type=meta.entity_type, mhvp_entity_id=meta.entity_id)
        response = await self._client.patch(
            f"{self.FILES_URL}/{ref}",
            params={"supportsAllDrives": "true"},
            json={"description": meta.title, "appProperties": properties},
            headers=await self._auth(),
        )
        if response.status_code == 404:
            return False
        _raise_for(response, "update_meta")
        return True

    async def trash(self, ref: str) -> bool:
        """Move the file to the Drive trash (fallback when the permanent ``delete`` is refused,
        for example on a shared drive without delete right). False when already gone."""
        response = await self._client.patch(
            f"{self.FILES_URL}/{ref}",
            params={"supportsAllDrives": "true"},
            json={"trashed": True},
            headers=await self._auth(),
        )
        if response.status_code == 404:
            return False
        _raise_for(response, "trash")
        return True

    CHANGES_URL = "https://www.googleapis.com/drive/v3/changes"

    async def start_page_token(self) -> str:
        """Cursor of the Changes API at this moment (M6-05); changes before it are ignored."""
        response = await self._client.get(
            f"{self.CHANGES_URL}/startPageToken",
            params={"supportsAllDrives": "true"},
            headers=await self._auth(),
        )
        _raise_for(response, "changes start token")
        return str(response.json()["startPageToken"])

    async def list_changes(
        self, page_token: str, max_pages: int = 10
    ) -> tuple[list[DriveChange], str]:
        """Changes since ``page_token``; returns them and the cursor to store. When more than
        ``max_pages`` pages are waiting, the cursor of the next page is returned so the next
        run continues there."""
        changes: list[DriveChange] = []
        token = page_token
        for _ in range(max_pages):
            response = await self._client.get(
                self.CHANGES_URL,
                params={
                    "pageToken": token,
                    "fields": (
                        "nextPageToken,newStartPageToken,"
                        "changes(fileId,removed,file(name,trashed,modifiedTime))"
                    ),
                    "pageSize": "100",
                    "supportsAllDrives": "true",
                    "includeItemsFromAllDrives": "true",
                },
                headers=await self._auth(),
            )
            _raise_for(response, "changes listing")
            payload = response.json()
            for item in payload.get("changes", []):
                if not item.get("fileId"):
                    continue
                file = item.get("file") or {}
                changes.append(
                    DriveChange(
                        file_id=str(item["fileId"]),
                        removed=bool(item.get("removed")) or bool(file.get("trashed")),
                        name=file.get("name"),
                        modified_at=file.get("modifiedTime"),
                    )
                )
            if payload.get("newStartPageToken"):
                return changes, str(payload["newStartPageToken"])
            token = str(payload.get("nextPageToken") or token)
            if not payload.get("nextPageToken"):
                return changes, token
        return changes, token

    async def list_folder(
        self, folder_id: str, modified_after: str | None = None, page_size: int = 100
    ) -> list[InboxFile]:
        """Files (no sub folders) of one folder, oldest change first, optionally only those
        changed after ``modified_after`` (RFC 3339), so the inbox job (A42) can keep a
        watermark. Only the given folder is listed, never the whole Drive account."""
        escaped = folder_id.replace("\\", "\\\\").replace("'", "\\'")
        query = f"'{escaped}' in parents and trashed = false and mimeType != '{_FOLDER_MIME}'"
        if modified_after:
            query += f" and modifiedTime > '{modified_after}'"
        files: list[InboxFile] = []
        token: str | None = None
        while True:
            params = {
                "q": query,
                "fields": "nextPageToken,files(id,name,mimeType,modifiedTime,size)",
                "orderBy": "modifiedTime",
                "pageSize": str(page_size),
                "supportsAllDrives": "true",
                "includeItemsFromAllDrives": "true",
            }
            if token:
                params["pageToken"] = token
            response = await self._client.get(
                self.FILES_URL, params=params, headers=await self._auth()
            )
            _raise_for(response, "inbox listing")
            payload = response.json()
            for f in payload.get("files", []):
                size = f.get("size")
                files.append(
                    InboxFile(
                        ref=str(f["id"]),
                        name=str(f.get("name") or f["id"]),
                        mime_type=str(f.get("mimeType") or "application/octet-stream"),
                        modified_at=str(f.get("modifiedTime") or ""),
                        size=int(size) if size is not None else None,
                    )
                )
            token = payload.get("nextPageToken")
            if not token:
                return files

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
