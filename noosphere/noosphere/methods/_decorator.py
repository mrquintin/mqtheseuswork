from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable
from uuid import uuid4

from pydantic import BaseModel

from noosphere.models import (
    CascadeEdgeRelation,
    Method,
    MethodImplRef,
    MethodInvocation,
    MethodType,
)
from noosphere.methods._hooks import _FAILURE_HOOKS, _POST_HOOKS, _PRE_HOOKS
from noosphere.methods._registry import REGISTRY

logger = logging.getLogger(__name__)

CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "CORRELATION_ID", default=""
)
TENANT_ID: contextvars.ContextVar[str] = contextvars.ContextVar(
    "TENANT_ID", default="default"
)

_store_factory: Callable[..., Any] | None = None


def set_store_factory(factory: Callable[..., Any]) -> None:
    global _store_factory
    _store_factory = factory


def _get_store() -> Any:
    if _store_factory is not None:
        try:
            return _store_factory()
        except Exception:
            return None
    return None


def _canonical_json(obj: Any) -> str:
    if isinstance(obj, BaseModel):
        obj = obj.model_dump(mode="json")
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _current_git_sha() -> str:
    sha = os.environ.get("THESEUS_GIT_SHA")
    if sha:
        return sha
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _current_correlation_id() -> str:
    return CORRELATION_ID.get()


def _current_tenant_id() -> str:
    return TENANT_ID.get()


def _validate_against_schema(schema: Any, data: Any) -> Any:
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        if isinstance(data, schema):
            return data
        return schema.model_validate(data)
    if isinstance(schema, dict) and schema:
        try:
            import jsonschema as _js

            _js.validate(data, schema)
        except ImportError:
            pass
    return data


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _run_failure_path(
    spec: Method,
    inv: MethodInvocation,
    validated_input: Any,
    exc: BaseException,
) -> None:
    inv = inv.model_copy(
        update={
            "ended_at": _utcnow(),
            "succeeded": False,
            "error_kind": type(exc).__name__,
        }
    )
    for hook_name, hook in _FAILURE_HOOKS:
        try:
            hook(spec, inv, validated_input, exc)
        except Exception:
            logger.exception("Failure hook %s raised", hook_name)
    store = _get_store()
    if store is not None:
        try:
            store.insert_method_invocation(inv)
        except Exception:
            logger.exception("Failed to persist invocation")


def register_method(
    *,
    name: str,
    version: str,
    method_type: MethodType,
    input_schema: Any,
    output_schema: Any,
    description: str,
    rationale: str,
    preconditions: list[str] | tuple[str, ...] = (),
    postconditions: list[str] | tuple[str, ...] = (),
    dependencies: list[tuple[str, str]] | tuple[tuple[str, str], ...] = (),
    owner: str,
    status: str = "active",
    nondeterministic: bool = False,
    emits_edges: list[CascadeEdgeRelation] | tuple[CascadeEdgeRelation, ...] = (),
) -> Callable:
    def decorator(fn: Callable) -> Callable:
        if isinstance(input_schema, type) and issubclass(input_schema, BaseModel):
            in_schema_dict = input_schema.model_json_schema()
        elif isinstance(input_schema, dict):
            in_schema_dict = input_schema
        else:
            in_schema_dict = {}

        if isinstance(output_schema, type) and issubclass(output_schema, BaseModel):
            out_schema_dict = output_schema.model_json_schema()
        elif isinstance(output_schema, dict):
            out_schema_dict = output_schema
        else:
            out_schema_dict = {}

        impl = MethodImplRef(
            module=fn.__module__,
            fn_name=fn.__qualname__,
            git_sha=_current_git_sha(),
            image_digest=None,
        )

        spec_for_hash = {
            "name": name,
            "version": version,
            "method_type": method_type.value,
            "input_schema": in_schema_dict,
            "output_schema": out_schema_dict,
            "description": description,
            "rationale": rationale,
            "preconditions": list(preconditions),
            "postconditions": list(postconditions),
            "dependencies": [list(d) for d in dependencies],
            "implementation": impl.model_dump(mode="json"),
            "owner": owner,
            "status": status,
            "nondeterministic": nondeterministic,
        }

        method_id = hashlib.sha256(
            _canonical_json(spec_for_hash).encode()
        ).hexdigest()[:32]

        spec = Method(
            method_id=method_id,
            name=name,
            version=version,
            method_type=method_type,
            input_schema=in_schema_dict,
            output_schema=out_schema_dict,
            description=description,
            rationale=rationale,
            preconditions=list(preconditions),
            postconditions=list(postconditions),
            dependencies=list(dependencies),
            implementation=impl,
            owner=owner,
            status=status,
            nondeterministic=nondeterministic,
            created_at=_utcnow(),
        )

        @wraps(fn)
        def wrapped(input_data: Any) -> Any:
            validated_input = _validate_against_schema(input_schema, input_data)
            input_hash = hashlib.sha256(
                _canonical_json(validated_input).encode()
            ).hexdigest()

            inv = MethodInvocation(
                id=str(uuid4()),
                method_id=spec.method_id,
                input_hash=input_hash,
                output_hash="",
                started_at=_utcnow(),
                ended_at=None,
                succeeded=False,
                error_kind=None,
                correlation_id=_current_correlation_id(),
                tenant_id=_current_tenant_id(),
            )

            try:
                for _hook_name, hook in _PRE_HOOKS:
                    hook(spec, inv, validated_input)
            except Exception as e:
                _run_failure_path(spec, inv, validated_input, e)
                raise

            try:
                result = fn(validated_input)
                _validate_against_schema(output_schema, result)
                output_hash = hashlib.sha256(
                    _canonical_json(result).encode()
                ).hexdigest()
                inv = inv.model_copy(
                    update={
                        "ended_at": _utcnow(),
                        "succeeded": True,
                        "output_hash": output_hash,
                    }
                )

                for hook_name, hook in _POST_HOOKS:
                    try:
                        hook(spec, inv, validated_input, result)
                    except Exception:
                        logger.exception("Post-hook %s raised", hook_name)

                store = _get_store()
                if store is not None:
                    try:
                        store.insert_method_invocation(inv)
                    except Exception:
                        logger.exception("Failed to persist invocation")

                return result
            except Exception as e:
                _run_failure_path(spec, inv, validated_input, e)
                raise

        wrapped.__method_spec__ = spec  # type: ignore[attr-defined]

        REGISTRY.register(spec, wrapped)

        if emits_edges:
            REGISTRY.set_emits_edges(method_id, list(emits_edges))

        store = _get_store()
        if store is not None:
            try:
                store.insert_method(spec)
            except Exception:
                logger.exception("Failed to persist method spec")

        return wrapped

    return decorator
