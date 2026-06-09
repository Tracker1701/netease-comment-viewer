import json
import os
import tempfile
import uuid
from datetime import datetime


SCHEMA_VERSION = 1


class HistoryStore:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self.path = os.path.join(data_dir, "parse_history.json")

    def load(self):
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (FileNotFoundError, OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        records = [item for item in data if self._is_valid(item)]
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)

    def add(self, category, entity_id, source_text, title, summary, rows):
        record = {
            "history_id": str(uuid.uuid4()),
            "category": category,
            "entity_id": str(entity_id),
            "source_text": source_text,
            "title": title or "未命名解析记录",
            "summary": summary,
            "rows": rows,
            "row_count": len(rows),
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "schema_version": SCHEMA_VERSION,
        }
        records = self.load()
        records.insert(0, record)
        self._write(records)
        return record

    def get(self, history_id):
        return next(
            (record for record in self.load() if record["history_id"] == history_id),
            None,
        )

    def delete(self, history_id):
        return self.delete_many([history_id]) == 1

    def delete_many(self, history_ids):
        wanted = set(history_ids)
        records = self.load()
        kept = [record for record in records if record["history_id"] not in wanted]
        deleted = len(records) - len(kept)
        if deleted:
            self._write(kept)
        return deleted

    def _write(self, records):
        os.makedirs(self.data_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            prefix="parse_history_", suffix=".tmp", dir=self.data_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(records, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, self.path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    @staticmethod
    def _is_valid(record):
        return (
            isinstance(record, dict)
            and isinstance(record.get("history_id"), str)
            and isinstance(record.get("rows"), list)
        )
