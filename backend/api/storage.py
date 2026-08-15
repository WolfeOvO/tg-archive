"""OpenList-backed storage driver and mount management endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth import require_auth

router = APIRouter(prefix="/api/storage", tags=["storage"])


class MountPayload(BaseModel):
    name: str = Field(default="", max_length=80)
    mount_path: str = Field(min_length=1, max_length=300)
    driver: str
    enabled: bool = True
    default: bool = False
    config: dict[str, Any] = Field(default_factory=dict)


def _engine(request: Request):
    return getattr(request.app.state, "storage_engine", None)


def _require_engine(request: Request):
    engine = _engine(request)
    if engine is None:
        raise HTTPException(status_code=409, detail="OpenList storage engine is not configured")
    return engine


@router.get("/drivers")
async def list_drivers(request: Request, token: str = Depends(require_auth)):
    engine = _engine(request)
    if engine is None:
        return {"connected": False, "drivers": []}
    try:
        return {"connected": True, "drivers": await engine.list_drivers()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenList connection failed: {exc}") from exc


@router.get("/mounts")
async def list_mounts(request: Request, token: str = Depends(require_auth)):
    engine = _engine(request)
    if engine is None:
        return {"connected": False, "mounts": []}
    try:
        return {"connected": True, "mounts": await engine.list_mounts()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenList connection failed: {exc}") from exc


@router.get("/mounts/{mount_id}")
async def get_mount(mount_id: str, request: Request, token: str = Depends(require_auth)):
    try:
        return await _require_engine(request).public_mount(mount_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mounts")
async def create_mount(payload: MountPayload, request: Request, token: str = Depends(require_auth)):
    engine = _require_engine(request)
    try:
        result = await engine.create_mount(payload.model_dump())
        return {"success": True, **(result or {})}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/mounts/{mount_id}")
async def update_mount(mount_id: str, payload: MountPayload, request: Request, token: str = Depends(require_auth)):
    try:
        await _require_engine(request).update_mount(mount_id, payload.model_dump())
        return {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/mounts/{mount_id}")
async def delete_mount(mount_id: str, request: Request, token: str = Depends(require_auth)):
    try:
        await _require_engine(request).delete_mount(mount_id)
        return {"success": True}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/mounts/{mount_id}/test")
async def test_mount(mount_id: str, request: Request, token: str = Depends(require_auth)):
    try:
        return await _require_engine(request).test_mount(mount_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
