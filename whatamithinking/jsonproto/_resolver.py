from typing import (
    Literal,
    Annotated,
    NewType,
    TypeAliasType,
    TypeGuard,
    Union,
)
from types import ModuleType, UnionType
import sys
from functools import partial

from lru import LRU

from ._common import (
    cached_get_args,
    cached_get_origin,
    T_FuzzyTypeHint,
    T_ResolvedTypeHint,
    T_StringTypeHint,
    T_UnresolvedTypeHint,
)
from ._struct import struct

__all__ = []


@struct(slots=True)
class TypeHintResolution:
    owner: type
    original_type_hint: T_FuzzyTypeHint
    origin: type | None
    type_hint: T_ResolvedTypeHint
    annotations: tuple
    is_partial: bool


def _resolve_forward_ref(
    type_hint: T_StringTypeHint, owner: type
) -> T_UnresolvedTypeHint:
    globals = locals = None
    if isinstance(owner, type):
        locals = dict(vars(owner))
        while True:
            if hasattr(unwrap, "__wrapped__"):
                unwrap = unwrap.__wrapped__
                continue
            if isinstance(unwrap, partial):
                unwrap = unwrap.func
                continue
            break
        if hasattr(unwrap, "__globals__"):
            globals = unwrap.__globals__
        else:
            if (module_name := getattr(owner, "__module__", None)) and (
                module := sys.modules[module_name]
            ):
                globals = getattr(module, "__dict__", None)
    elif isinstance(owner, ModuleType):
        globals = getattr(owner, "__dict__")
    elif callable(owner):
        globals = getattr(owner, "__globals__", None)
    if type_params := getattr(owner, "__type_params__", None):
        if locals is None:
            locals = {}
        locals = {param.__name__: param for param in type_params} | locals
    return eval(type_hint, globals, locals)


class UNRESOLVE_TYPE:
    def __repr__(self) -> str:
        return "<UNRESOLVED>"


UNRESOLVED = UNRESOLVE_TYPE()


def _resolve_type_hint(
    type_hint: T_FuzzyTypeHint,
    owner: type,
    resolve_forward_refs: bool,
    cache: dict | None = None,
) -> TypeHintResolution:
    is_partial = False
    annotations = ()
    origin = None
    if cache is None:
        cache = {}
    resolved_type_hint = cache.get(type_hint)
    if resolved_type_hint is UNRESOLVED:
        resolved_type_hint = type_hint
        is_partial = True
    elif resolved_type_hint is None:
        cache[type_hint] = UNRESOLVED
        previous_type_hint = UNRESOLVED
        resolved_type_hint = type_hint
        while True:
            if (
                type_hint != resolved_type_hint and resolved_type_hint in cache
            ) or previous_type_hint is resolved_type_hint:
                resolved_type_hint = type_hint
                is_partial = True
                break
            previous_type_hint = resolved_type_hint
            if isinstance(resolved_type_hint, str):
                if resolve_forward_refs and owner is not None:
                    resolved_type_hint = _resolve_forward_ref(resolved_type_hint, owner)
                continue
            origin = cached_get_origin(resolved_type_hint)
            if origin is Annotated:
                args = cached_get_args(resolved_type_hint)
                if len(args) == 0:
                    raise ValueError(f"{Annotated!r} is not a type")
                resolved_type_hint = args[0]
                annotations = args[1:]
                continue
            if resolved_type_hint.__class__ is TypeAliasType:
                resolved_type_hint = resolved_type_hint.__value__
                continue
            if resolved_type_hint.__class__ is NewType:
                resolved_type_hint = resolved_type_hint.__supertype__
                continue
            if resolved_type_hint.__class__ is TypeGuard:
                resolved_type_hint = cached_get_args(resolved_type_hint)[0]
                continue
            if origin is not None and origin is not Literal:
                if origin is UnionType:
                    origin = Union
                args = tuple(
                    (
                        Annotated[thr.type_hint, *thr.annotations]
                        if thr.annotations
                        else thr.type_hint
                    )
                    for unionth in cached_get_args(resolved_type_hint)
                    if (
                        thr := _resolve_type_hint(
                            type_hint=unionth,
                            owner=owner,
                            resolve_forward_refs=resolve_forward_refs,
                            cache=cache,
                        )
                    )
                    and (is_partial := (is_partial or thr.is_partial)) is not None
                )
                if len(args) == 1:
                    resolved_type_hint = origin[args[0]]
                else:
                    resolved_type_hint = origin[*args]
            break
        cache[type_hint] = resolved_type_hint
    return TypeHintResolution(
        owner=owner,
        original_type_hint=type_hint,
        origin=origin,
        type_hint=resolved_type_hint,
        annotations=annotations,
        is_partial=is_partial,
    )


_resolved_type_hint_cache = LRU(1024**2)


def resolve_type_hint(
    type_hint: T_FuzzyTypeHint,
    resolve_forward_refs: bool = False,
    owner: type | None = None,
) -> TypeHintResolution:
    global _resolved_type_hint_cache
    try:
        thr = _resolved_type_hint_cache[type_hint]
    except KeyError:
        thr = _resolve_type_hint(
            type_hint=type_hint, resolve_forward_refs=resolve_forward_refs, owner=owner
        )
        # cannot safely cache partial resolutions since they may become resolveable later
        if not thr.is_partial:
            _resolved_type_hint_cache[type_hint] = thr
    return thr
