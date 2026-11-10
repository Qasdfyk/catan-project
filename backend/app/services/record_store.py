"""
Finished game records on disk, one gzipped JSON file per room. Redis holds a
record only while its game runs; this is where it stays afterwards.
"""
import gzip
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

# Room IDs come from URLs, so they must never reach the file system unchecked
ROOM_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")


class RecordStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)

    def path(self, room_id: str) -> Path:
        if not ROOM_ID.fullmatch(room_id):
            raise ValueError(f"Invalid room ID {room_id!r}.")
        return self.directory / f"{room_id}.json.gz"

    def save(self, room_id: str, record: Dict[str, Any]):
        """
        Writes to a temporary file and renames it, so a reader sees either no
        record or a whole one. The fsync before the rename keeps a power cut
        from leaving an empty file under the final name.
        """
        path = self.path(room_id)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        data = json.dumps(record, separators=(",", ":")).encode()
        with open(temporary, "wb") as file:
            with gzip.GzipFile(fileobj=file, mode="wb") as zipped:
                zipped.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)

    def load(self, room_id: str) -> Optional[Dict[str, Any]]:
        try:
            with gzip.open(self.path(room_id), "rt", encoding="utf-8") as file:
                return json.load(file)
        except FileNotFoundError:
            return None
