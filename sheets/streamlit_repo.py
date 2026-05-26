from typing import Any, Dict, Iterable, Optional, Set

import pandas as pd

from sheets.serialization import storage_key, tracked_info_from_row, tracked_info_to_apps_row


class StreamlitAppsRepository:
    def __init__(self, connection: Any, available: bool):
        self._conn = connection
        self.available = available
        self.last_error: Optional[str] = None

    @classmethod
    def connect(cls) -> "StreamlitAppsRepository":
        import streamlit as st
        from streamlit_gsheets import GSheetsConnection

        try:
            conn = st.connection("gsheets", type=GSheetsConnection)
            return cls(conn, True)
        except Exception as e:
            st.error(f"Ошибка подключения: {e}")
            return cls(None, False)

    def load_users(self) -> Dict[str, Any]:
        if not self.available:
            return {}
        try:
            df = self._conn.read(worksheet="users", ttl=0)
            return dict(zip(df["name"], df["chat_id"]))
        except Exception:
            return {}

    def load_apps(self) -> Dict[str, Dict[str, Any]]:
        if not self.available:
            return {}
        try:
            return self._read_apps()
        except Exception:
            return {}

    def _read_apps(self) -> Dict[str, Dict[str, Any]]:
        df = self._conn.read(worksheet="apps", ttl=0)
        if df is None or df.empty:
            return {}

        data = {}
        for _, row in df.iterrows():
            info = tracked_info_from_row(
                row.get("package_id"),
                row.get("geo"),
                row.get("chat_id"),
                title=row.get("title"),
                summary=row.get("summary"),
                description=row.get("description"),
                icon=row.get("icon"),
                header_image=row.get("header_image"),
                screenshots=row.get("screenshots"),
                history=row.get("history"),
                check_log=row.get("check_log"),
                ai_audit=row.get("ai_audit"),
                use_pandas_na=True,
            )
            if info:
                key = info.pop("_storage_key", storage_key(info))
                data[key] = info
        return data

    @staticmethod
    def _key_set(keys: Optional[Iterable[str]]) -> Set[str]:
        return {str(key) for key in keys or []}

    def save_apps(
        self,
        data: Dict[str, Dict[str, Any]],
        *,
        updated_keys: Optional[Iterable[str]] = None,
        deleted_keys: Optional[Iterable[str]] = None,
    ) -> bool:
        if not self.available:
            self.last_error = "Нет подключения к Google Sheets."
            return False
        try:
            keys_to_update = self._key_set(updated_keys)
            keys_to_delete = self._key_set(deleted_keys)
            if keys_to_update or keys_to_delete:
                data_to_save = self._read_apps()
                for key in keys_to_update:
                    if key in data:
                        data_to_save[key] = data[key]
                for key in keys_to_delete:
                    data_to_save.pop(key, None)
            else:
                data_to_save = data

            rows = [tracked_info_to_apps_row(info) for info in data_to_save.values()]
            self._conn.update(worksheet="apps", data=pd.DataFrame(rows))
            self.last_error = None
            return True
        except Exception as e:
            self.last_error = str(e)
            return False
