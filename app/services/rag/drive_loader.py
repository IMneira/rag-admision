import io, os, pathlib, mimetypes
from typing import Iterator, List

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
CREDS = service_account.Credentials.from_service_account_file(
    os.environ["GOOGLE_CREDENTIALS_PATH"], scopes=SCOPES
)

def _drive() -> "googleapiclient.discovery.Resource":
    return build("drive", "v3", credentials=CREDS, cache_discovery=False)

def list_files(folder_id: str) -> List[dict]:
    """Return Drive file metadata (id, name, mimeType) for the folder (non-recursive)."""
    q = f"'{folder_id}' in parents and trashed = false"
    res = _drive().files().list(q=q, fields="files(id,name,mimeType,md5Checksum)").execute()
    return res["files"]

def download(file_id: str, local_path: pathlib.Path) -> pathlib.Path:
    local_path.parent.mkdir(parents=True, exist_ok=True)
    fh = io.FileIO(local_path, "wb")
    request = _drive().files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    return local_path

def iter_local_docs(folder_id: str) -> Iterator[pathlib.Path]:
    """Yield local file paths, downloading to a tmp dir if needed."""
    tmp_dir = pathlib.Path("/tmp/drive_docs")
    for meta in list_files(folder_id):
        name = meta["name"]
        ext = mimetypes.guess_extension(meta["mimeType"]) or pathlib.Path(name).suffix
        local = tmp_dir / f"{meta['id']}{ext}"
        if not local.exists():
            download(meta["id"], local)
        yield local