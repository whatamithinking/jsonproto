from typing import Any, ClassVar, Final
from collections import ChainMap
from itertools import chain

from lru import LRU

from ._handlers import (
    TypeHandler,
    default_type_hint_handler_classes,
    default_callback_handler_classes,
)
from ._pointers import (
    JsonPath,
    JsonPointer,
)
from ._issues import DeserializeIssue, SerializeIssue
from ._patches import Patches
from ._errors import TypeHandlerMissingError, ValidationError
from ._common import (
    Constraints,
    T_ExtrasMode,
    T_FuzzyTypeHint,
    T_UnresolvedTypeHint,
    T_ResolvedTypeHint,
    T_SourceFormat,
    T_TargetFormat,
    T_TypeHintValue,
    T_IsTypeCallback,
    T_CodecSourceFormat,
    T_CodecTargetFormat,
    T_CodecSerializationFormat,
    Metadata,
    MISSING_TYPE,
    MISSING,
)
from ._resolver import TypeHintResolution, resolve_type_hint
from ._struct import struct, is_struct_instance

__all__ = [
    "Config",
    "Codec",
]


@struct(slots=True)
class Config:
    metadata: Metadata = Metadata()
    source: T_SourceFormat = "unstruct"
    target: T_TargetFormat = "unstruct"
    coerce: bool = False
    validate: bool = False
    convert: bool = False
    include: JsonPath = JsonPath.everything
    exclude: JsonPath = JsonPath.nothing
    exclude_none: bool = False
    exclude_unset: bool = False
    exclude_default: bool = False
    extras_mode: T_ExtrasMode = "forbid"
    patches: Patches = Patches.empty


class Codec:
    def __init__(self) -> None:
        self._type_hint_handler_classes: dict[
            T_ResolvedTypeHint, type["TypeHandler"]
        ] = ChainMap({}, default_type_hint_handler_classes())
        self._callback_handler_classes: dict[T_IsTypeCallback, type["TypeHandler"]] = (
            ChainMap({}, default_callback_handler_classes())
        )
        self._cache_handler_classes: dict[T_FuzzyTypeHint, type["TypeHandler"]] = {}
        self._cache_handlers: dict[
            tuple[T_FuzzyTypeHint, Constraints, T_TypeHintValue], "TypeHandler"
        ] = {}
        # LRU cache for Config instances with optimized key generation
        self._config_cache = LRU(1024)

    def _create_config(
        self,
        metadata: Metadata,
        source: T_SourceFormat,
        target: T_TargetFormat,
        coerce: bool,
        validate: bool,
        convert: bool,
        include: JsonPath,
        exclude: JsonPath,
        exclude_none: bool,
        exclude_unset: bool,
        exclude_default: bool,
        extras_mode: T_ExtrasMode,
        patches: Patches,
    ) -> "Config":
        key = hash(
            (
                metadata,
                source,
                target,
                coerce,
                validate,
                convert,
                include,
                exclude,
                exclude_none,
                exclude_unset,
                exclude_default,
                extras_mode,
                patches,
            )
        )

        try:
            return self._config_cache[key]
        except KeyError:
            config = Config(
                metadata=metadata,
                source=source,
                target=target,
                coerce=coerce,
                validate=validate,
                convert=convert,
                include=include,
                exclude=exclude,
                exclude_none=exclude_none,
                exclude_unset=exclude_unset,
                exclude_default=exclude_default,
                extras_mode=extras_mode,
                patches=patches,
            )
            self._config_cache[key] = config
            return config

    def register_type_handler(
        self,
        type_handler_class: type["TypeHandler"],
        /,
        type_hint: T_FuzzyTypeHint | MISSING_TYPE = MISSING,
        callback: T_IsTypeCallback | MISSING_TYPE = MISSING,
    ) -> None:
        if type_hint is MISSING and callback is MISSING:
            raise ValueError("one of type_hint or callback must be given")
        elif type_hint is not MISSING and callback is not MISSING:
            raise ValueError("either type_hint or callback must be given, not both")
        if type_hint is not MISSING:
            thr = resolve_type_hint(type_hint=type_hint)
            if thr.is_partial:
                raise TypeError(
                    "stringified types not supported during type handler registration"
                )
            self._type_hint_handler_classes[thr.type_hint] = type_handler_class
        else:
            self._callback_handler_classes[callback] = type_handler_class
        # unclear what impact of this change will have, so start over with caches
        # to make sure we determine the handlers based on the new set of handlers
        self._cache_handler_classes.clear()
        self._cache_handlers.clear()

    def _get_type_handler_class(
        self, type_hint_resolution: TypeHintResolution
    ) -> type["TypeHandler"]:
        try:
            return self._cache_handler_classes[type_hint_resolution.type_hint]
        except KeyError:
            # note that we start by looking for handlers of the more specific type hint
            # and fallback to the less specific without the generic types, since
            # these shell types usually themselves call in this method to handle
            # generic types handling
            type_hint_options = [
                type_hint_resolution.original_type_hint,
                type_hint_resolution.type_hint,
            ]
            if (origin := type_hint_resolution.origin) is not None:
                type_hint_options.append(origin)
            type_hint_class = None
            for type_hint_option in type_hint_options:
                if type_hint_class := self._type_hint_handler_classes.get(
                    type_hint_option
                ):
                    break
                for is_type, thc in self._callback_handler_classes.items():
                    if not is_type(type_hint_option):
                        continue
                    type_hint_class = thc
                    break
                if type_hint_class:
                    break
            else:
                raise TypeHandlerMissingError(
                    f"No type handler class found supporting {type_hint_resolution.original_type_hint!r}"
                )
            self._cache_handler_classes[type_hint_resolution.original_type_hint] = (
                type_hint_class
            )
            self._cache_handler_classes[type_hint_option] = type_hint_class
            return type_hint_class

    def get_type_handler(
        self,
        type_hint: T_FuzzyTypeHint,
        constraints: Constraints = Constraints.empty,
        type_hint_value: T_TypeHintValue = MISSING,
    ) -> "TypeHandler":
        try:
            return self._cache_handlers[(type_hint, constraints, type_hint_value)]
        except KeyError:
            type_hint_resolution = resolve_type_hint(type_hint=type_hint)
            if type_hint_resolution.is_partial:
                raise TypeError("could not fully resolve type hint")
            # special case: ClassVar/Final type hints are effectively Literal with one value but
            # the value is not included in the type hint so we need to get it from the caller
            # and use it to index off of and create a new type handler for each one since the default
            # needs to be provided to each instance of the type handler
            if type_hint_resolution.origin in (ClassVar, Final):
                if type_hint_value is MISSING:
                    raise ValueError(
                        "type_hint_value must be given when getting the type handler for ClassVar or Final"
                    )
            elif type_hint_value is not MISSING:
                type_hint_value = MISSING  # always ignore the value otherwise so instances dont explode
                try:
                    return self._cache_handlers[
                        (type_hint, constraints, type_hint_value)
                    ]
                except KeyError:
                    pass

            total_constraints = Constraints(
                chain(
                    (
                        _
                        for _ in type_hint_resolution.annotations
                        if hasattr(_, "constraint_type")
                    ),
                    constraints,
                )
            )
            type_handler_class = self._get_type_handler_class(
                type_hint_resolution=type_hint_resolution
            )
            type_handler = type_handler_class(
                codec=self,
                type_hint=type_hint_resolution.type_hint,
                constraints=total_constraints,
                type_hint_value=type_hint_value,
            )
            # index off the original input exactly in case this is given again
            self._cache_handlers[
                (
                    type_hint_resolution.original_type_hint,
                    constraints,
                    type_hint_value,
                )
            ] = type_handler
            # index off the type hint alone without any annotations and with all the constraints
            # stripped off and provided separately in case a caller provides just the type hint and
            # the same set of constraints previously provided through the annotations
            self._cache_handlers[
                (
                    type_hint_resolution.type_hint,
                    total_constraints,
                    type_hint_value,
                )
            ] = type_handler
            return type_handler

    def serialize(self, value: Any, target: T_CodecSerializationFormat) -> str | bytes:
        import orjson

        try:
            data = orjson.dumps(value, option=orjson.OPT_SORT_KEYS)
        except (TypeError, orjson.JSONEncodeError) as exc:
            raise ValidationError(
                [SerializeIssue(value=value, pointer=JsonPointer.root, message=exc.msg)]
            ) from exc
        if target == "jsonbytes":
            return data
        return data.decode()

    def deserialize(self, value: bytes | str) -> Any:
        import orjson

        try:
            return orjson.loads(value)
        except orjson.JSONDecodeError as exc:
            raise ValidationError(
                [DeserializeIssue(value=value, pointer=JsonPointer.root, message=exc.msg)]
            ) from exc

    def execute(
        self,
        value: Any,
        type_hint: T_UnresolvedTypeHint = MISSING,
        type_hint_value: T_TypeHintValue = MISSING,
        metadata: Metadata = Metadata(),
        source: T_CodecSourceFormat = "unstruct",
        target: T_CodecTargetFormat | None = None,
        coerce: bool = False,
        validate: bool = False,
        convert: bool = False,
        include: JsonPath = JsonPath.everything,
        exclude: JsonPath = JsonPath.nothing,
        exclude_none: bool = False,
        exclude_unset: bool = False,
        exclude_default: bool = False,
        extras_mode: T_ExtrasMode = "forbid",
        patches: Patches = Patches.empty,
    ) -> Any:
        if not coerce and not validate and not convert:
            return value
        if type_hint is MISSING:
            if is_struct_instance(value):
                type_hint = value.__class__
            else:
                raise ValueError(
                    "type_hint must be given when value is not a model instance"
                )
        if target is None:
            target = source
        # NOTE: source and target are allowed to be the same thing, so we can perform a copy
        pointer = JsonPointer.root

        excluded = exclude.matches(pointer)
        if excluded:
            if target == "jsonbytes":
                return b""
            elif target == "jsonstr":
                return ""
            return None
        included = include.matches(pointer)

        raw_value = value
        if source in ("jsonstr", "jsonbytes") and (
            target in ("json", "unstruct", "struct") or validate
        ):
            value = self.deserialize(value=value)

        if patches:
            value = patches.patch("source", "value", pointer, value)

        if not (
            source in ("jsonstr", "jsonbytes") and target in ("jsonstr", "jsonbytes")
        ):
            type_handler = self.get_type_handler(
                type_hint=type_hint, type_hint_value=type_hint_value
            )
            value, issues = type_handler.handle(
                value=value,
                pointer=pointer,
                included=included,
                excluded=excluded,
                config=self._create_config(
                    metadata=metadata,
                    source=("json" if source in ("jsonstr", "jsonbytes") else source),
                    target=("json" if target in ("jsonstr", "jsonbytes") else target),
                    coerce=coerce,
                    validate=validate,
                    convert=convert,
                    include=include,
                    exclude=exclude,
                    exclude_none=exclude_none,
                    exclude_unset=exclude_unset,
                    exclude_default=exclude_default,
                    extras_mode=extras_mode,
                    patches=patches,
                ),
            )
            if issues:
                raise ValidationError(issues=issues)

        if patches:
            value = patches.patch("target", "value", pointer, value)

        if (included and not excluded) or value is not MISSING:
            if target in ("jsonstr", "jsonbytes"):
                if source == target:
                    return raw_value
                elif source == "jsonstr" and target == "jsonbytes":
                    return raw_value.encode()
                elif source == "jsonbytes" and target == "jsonstr":
                    return raw_value.decode()
                else:
                    value = self.serialize(value=value, target=target)
            return value

        if target == "jsonbytes":
            return b""
        elif target == "jsonstr":
            return ""
        return None
