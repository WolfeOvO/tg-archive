"""OpenList management engine: dynamic driver catalog and real storage mounts."""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx

_SECRET_NAMES = re.compile(
    r"token|secret|password|passwd|passphrase|pwd|cookie|key|authorization|(?:two_fa|sms|validate|verify|receive)_?code",
    re.IGNORECASE,
)


class OpenListEngine:
    @staticmethod
    def _is_secret(field: dict[str, Any]) -> bool:
        return bool(field.get("confidential")) or bool(
            _SECRET_NAMES.search(field.get("name", ""))
        )

    @staticmethod
    def _mount_id(mount_id: str) -> str:
        value = str(mount_id)
        if not value.isdecimal():
            raise ValueError("Invalid mount ID")
        return value

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        client: httpx.AsyncClient | None = None,
        state_path: str | Path | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.client = client or httpx.AsyncClient(base_url=self.base_url, timeout=60)
        self._owns_client = client is None
        self.token = ""
        self._drivers: dict[str, dict[str, Any]] = {}
        self._mounts: list[dict[str, Any]] = []
        self._adapters: dict[str, Any] = {}
        self._adapter_locks: dict[str, asyncio.Lock] = {}
        self.state_path = Path(state_path) if state_path else None
        self.default_mount_id = self._load_state()

    def _load_state(self) -> str:
        if self.state_path is None or not self.state_path.exists():
            return ""
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return str(payload.get("default_mount_id", ""))
        except (OSError, ValueError, TypeError):
            return ""

    def set_default_mount(self, mount_id: str):
        self.default_mount_id = str(mount_id)
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".openlist-state-", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"default_mount_id": self.default_mount_id}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.state_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    async def close(self):
        for mount_id in list(self._adapters):
            await self._close_adapter(mount_id)
        if self._owns_client:
            await self.client.aclose()

    async def _close_adapter(self, mount_id: str):
        lock = self._adapter_locks.setdefault(mount_id, asyncio.Lock())
        async with lock:
            await self._close_adapter_unlocked(mount_id)

    async def _close_adapter_unlocked(self, mount_id: str):
        adapter = self._adapters.pop(mount_id, None)
        if adapter is not None:
            await adapter.close()

    async def _login(self):
        if self.token:
            return
        response = await self.client.post(
            self.base_url + "/api/auth/login" if self.client.base_url == httpx.URL("") else "/api/auth/login",
            json={"username": self.username, "password": self.password},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(payload.get("message") or "OpenList login failed")
        self.token = payload["data"]["token"]

    def _headers(self):
        return {"Authorization": self.token}

    async def _request(self, method: str, path: str, **kwargs):
        await self._login()
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        url = self.base_url + path if self.client.base_url == httpx.URL("") else path
        response = await self.client.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise RuntimeError(payload.get("message") or f"OpenList request failed: {path}")
        return payload.get("data")

    @staticmethod
    def _field(item: dict[str, Any]) -> dict[str, Any]:
        key = item.get("name", "")
        raw_type = item.get("type", "string").lower()
        field_type = {
            "bool": "boolean", "boolean": "boolean", "number": "number",
            "int": "number", "uint": "number", "text": "textarea",
            "select": "select",
        }.get(raw_type, "password" if OpenListEngine._is_secret(item) else "text")
        return {
            "key": key,
            "label": key.replace("_", " ").title(),
            "type": field_type,
            "required": bool(item.get("required")),
            "secret": OpenListEngine._is_secret(item),
            "placeholder": str(item.get("default") or ""),
            "default": item.get("default", ""),
            "options": [value for value in str(item.get("options") or "").split(",") if value],
            "help": item.get("help", ""),
        }

    @staticmethod
    def _value(field: dict[str, Any], value: Any) -> Any:
        field_type = field.get("type", "string").lower()
        if field_type in {"bool", "boolean"}:
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on"}
            return bool(value)
        if field_type in {"number", "int", "uint"}:
            if value in {None, ""}:
                return 0
            text = str(value)
            return float(text) if "." in text else int(text)
        return value

    async def list_drivers(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/admin/driver/list")
        self._drivers = data
        result = []
        for name in sorted(data):
            info = data[name]
            fields = [
                self._field(item)
                for item in [*info.get("common", []), *info.get("additional", [])]
                if item.get("name") != "mount_path"
            ]
            result.append({
                "key": name,
                "name": name,
                "description": info.get("config", {}).get("local_sort", "") or "OpenList storage driver",
                "fields": fields,
                "source": "openlist",
            })
        return result

    async def list_mounts(self) -> list[dict[str, Any]]:
        data = await self._request("GET", "/api/admin/storage/list?page=1&per_page=1000")
        self._mounts = [{
            "id": str(item["id"]),
            "name": item.get("remark") or item["mount_path"].strip("/") or item["driver"],
            "mount_path": item["mount_path"],
            "driver": item["driver"],
            "enabled": not item.get("disabled", False),
            "default": str(item["id"]) == self.default_mount_id,
            "status": item.get("status", "unknown"),
            "config": {},
            "secret_fields_set": [],
        } for item in data.get("content", [])]
        return self._mounts

    async def refresh(self):
        await self.list_drivers()
        await self.list_mounts()

    def resolve(self, mount_id: str | None = None):
        explicit = mount_id is not None
        if explicit:
            mount_id = self._mount_id(mount_id)
        selected_id = mount_id or self.default_mount_id
        selected = next((item for item in self._mounts if item["id"] == selected_id), None)
        if not explicit and (selected is None or not selected["enabled"]):
            selected = next((item for item in self._mounts if item["enabled"]), None)
            if selected is not None and selected["id"] != self.default_mount_id:
                self.set_default_mount(selected["id"])
        if selected is None:
            raise ValueError("No storage mount configured")
        if not selected["enabled"]:
            raise ValueError("Selected mount is disabled")
        return type("OpenListMount", (), selected)()

    async def adapter(self, mount_id: str | None = None):
        async with self.adapter_session(mount_id) as adapter:
            return adapter

    @asynccontextmanager
    async def adapter_session(self, mount_id: str | None = None):
        from storage.drivers import OpenListStorage
        while True:
            mount = self.resolve(mount_id)
            lock = self._adapter_locks.setdefault(mount.id, asyncio.Lock())
            await lock.acquire()
            retry = False
            try:
                locked_mount = self.resolve(mount_id)
                if locked_mount.id != mount.id:
                    retry = True
                else:
                    adapter = self._adapters.get(mount.id)
                    if adapter is None:
                        adapter = OpenListStorage(
                            base_url=self.base_url,
                            username=self.username,
                            password=self.password,
                            root_path=locked_mount.mount_path,
                        )
                        await adapter.initialize()
                        self._adapters[mount.id] = adapter
                    yield adapter
            finally:
                lock.release()
            if retry:
                continue
            return

    async def get_mount(self, mount_id: str) -> dict[str, Any]:
        mount_id = self._mount_id(mount_id)
        item = await self._request("GET", f"/api/admin/storage/get?id={mount_id}")
        addition = json.loads(item.get("addition") or "{}")
        return {**item, "addition": addition}

    async def public_mount(self, mount_id: str) -> dict[str, Any]:
        if not self._drivers:
            await self.list_drivers()
        item = await self.get_mount(mount_id)
        info = self._drivers.get(item["driver"], {})
        common_names = {field["name"] for field in info.get("common", [])}
        secret_names = {
            field["name"]
            for field in [*info.get("common", []), *info.get("additional", [])]
            if self._is_secret(field)
        }
        addition = item.pop("addition", {})
        config = {**{name: item.get(name, "") for name in common_names}, **addition}
        config = {
            key: "" if key in secret_names else value
            for key, value in config.items()
        }
        return {
            "id": str(item["id"]),
            "name": item.get("remark") or item["mount_path"],
            "mount_path": item["mount_path"],
            "driver": item["driver"],
            "enabled": not item.get("disabled", False),
            "default": str(item["id"]) == self.default_mount_id,
            "status": item.get("status", "unknown"),
            "config": config,
            "secret_fields_set": sorted(
                key for key in secret_names if item.get(key) or addition.get(key)
            ),
        }

    async def create_mount(self, payload: dict[str, Any]):
        if not self._drivers:
            await self.list_drivers()
        info = self._drivers[payload["driver"]]
        config = payload.get("config", {})
        common = {
            field["name"]: self._value(field, config.get(field["name"], field.get("default", "")))
            for field in info.get("common", [])
        }
        addition = {
            field["name"]: self._value(field, config.get(field["name"], field.get("default", "")))
            for field in info.get("additional", [])
        }
        body = {**common, "driver": payload["driver"], "mount_path": payload["mount_path"], "remark": payload.get("name", ""), "addition": json.dumps(addition, ensure_ascii=False)}
        result = await self._request("POST", "/api/admin/storage/create", json=body)
        mount_id = str(result["id"])
        if not payload.get("enabled", True):
            await self.set_enabled(mount_id, False)
        if payload.get("default"):
            self.set_default_mount(mount_id)
        await self.list_mounts()
        return result

    async def update_mount(self, mount_id: str, payload: dict[str, Any]):
        mount_id = self._mount_id(mount_id)
        lock = self._adapter_locks.setdefault(mount_id, asyncio.Lock())
        async with lock:
            await self._close_adapter_unlocked(mount_id)
            current = await self.get_mount(mount_id)
            if payload["driver"] != current["driver"]:
                raise ValueError("OpenList mount driver cannot be changed; create a new mount instead")
            if not self._drivers:
                await self.list_drivers()
            info = self._drivers[payload["driver"]]
            incoming = payload.get("config", {})
            common = {
                field["name"]: self._value(
                    field,
                    incoming.get(field["name"], current.get(field["name"], field.get("default", ""))),
                )
                for field in info.get("common", [])
            }
            addition = {
                **current.get("addition", {}),
                **{
                    field["name"]: self._value(field, incoming[field["name"]])
                    for field in info.get("additional", [])
                    if incoming.get(field["name"]) != ""
                },
            }
            body = {
                **common,
                "id": int(mount_id),
                "driver": payload["driver"],
                "mount_path": payload["mount_path"],
                "remark": payload.get("name", ""),
                "disabled": bool(current.get("disabled", False)),
                "addition": json.dumps(addition, ensure_ascii=False),
            }
            await self._request("POST", "/api/admin/storage/update", json=body)
            enabled = payload.get("enabled", True)
            if enabled == bool(current.get("disabled", False)):
                await self.set_enabled(mount_id, enabled)
            if payload.get("default"):
                self.set_default_mount(mount_id)
            elif self.default_mount_id == mount_id:
                self.set_default_mount("")
            await self.list_mounts()

    async def delete_mount(self, mount_id: str):
        mount_id = self._mount_id(mount_id)
        lock = self._adapter_locks.setdefault(mount_id, asyncio.Lock())
        async with lock:
            await self._close_adapter_unlocked(mount_id)
            await self._request("POST", f"/api/admin/storage/delete?id={mount_id}")
            if self.default_mount_id == mount_id:
                self.set_default_mount("")
            await self.list_mounts()

    async def set_enabled(self, mount_id: str, enabled: bool):
        mount_id = self._mount_id(mount_id)
        action = "enable" if enabled else "disable"
        await self._request("POST", f"/api/admin/storage/{action}?id={mount_id}")

    async def test_mount(self, mount_id: str):
        mount_id = self._mount_id(mount_id)
        item = await self.get_mount(mount_id)
        if item.get("status") not in {"work", "working"}:
            raise RuntimeError(item.get("status") or "OpenList storage is not ready")
        return {"ok": True, "storage": {"detail": f"OpenList {item['driver']} connected"}}
