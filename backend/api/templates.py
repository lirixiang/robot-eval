from __future__ import annotations
import structlog
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.db import db
from backend.db.queries import templates as tq

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/templates", tags=["templates"])


class CreateTemplateRequest(BaseModel):
    name:        str
    version:     str = "1.0"
    runner_type: str
    config_yaml: str
    description: str = ""


class ValidateRequest(BaseModel):
    config_yaml: str


@router.post("")
async def create_template(req: CreateTemplateRequest):
    errors = _validate_yaml(req.config_yaml)
    if errors:
        raise HTTPException(422, {"errors": errors})
    try:
        t = await tq.create_template(
            db.pool, name=req.name, version=req.version,
            runner_type=req.runner_type, config_yaml=req.config_yaml,
            description=req.description or None,
        )
        return t
    except Exception as e:
        if "unique" in str(e).lower():
            raise HTTPException(409, f"Template {req.name}@{req.version} already exists")
        raise


@router.get("")
async def list_templates():
    return await tq.list_templates(db.pool)


# NOTE: /validate must be registered before /{template_id} so FastAPI does not
# treat the literal string "validate" as an integer path parameter.
@router.post("/validate")
async def validate_yaml(req: ValidateRequest):
    errors = _validate_yaml(req.config_yaml)
    return {"valid": len(errors) == 0, "errors": errors}


@router.get("/{template_id}")
async def get_template(template_id: int):
    t = await tq.get_template(db.pool, template_id)
    if not t:
        raise HTTPException(404, f"Template {template_id} not found")
    return t


@router.delete("/{template_id}")
async def delete_template(template_id: int):
    t = await tq.get_template(db.pool, template_id)
    if not t:
        raise HTTPException(404)
    await tq.delete_template(db.pool, template_id)
    return {"ok": True}


def _validate_yaml(yaml_str: str) -> list[str]:
    import yaml
    errors = []
    try:
        doc = yaml.safe_load(yaml_str)
    except yaml.YAMLError as e:
        return [f"YAML parse error: {e}"]
    if not isinstance(doc, dict):
        return ["YAML must be a mapping"]
    for key in ("name", "runner", "episodes"):
        if key not in doc:
            errors.append(f"Missing required key: '{key}'")
    if "episodes" in doc:
        ep = doc["episodes"]
        if not isinstance(ep, int) or ep <= 0:
            errors.append(f"'episodes' must be a positive integer, got: {ep!r}")
    if "metrics" in doc and not isinstance(doc["metrics"], list):
        errors.append("'metrics' must be a list")
    return errors
