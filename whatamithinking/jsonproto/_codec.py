from typing import Any, ClassVar, Final, Mapping
from types import MappingProxyType
from collections import ChainMap
from itertools import chain
import shutil
from io import TextIOWrapper, DEFAULT_BUFFER_SIZE
from functools import partial

from lru import LRU

from ._handlers import (
    TypeHandler,
    TypeHandlerRegistry,
    default_type_handler_registry,
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
    ExtrasMode,
    FuzzyTypeHint,
    UnresolvedTypeHint,
    ResolvedTypeHint,
    TypeHandlerFormat,
    TypeHandlerFormat,
    TypeHintValue,
    IsTypeCallback,
    CodecFormat,
    CodecFormat,
    CodecSerializationFormat,
    Metadata,
    Empty,
)
from ._resolver import TypeHintResolution, resolve_type_hint
from ._struct import struct, is_struct_instance, is_struct_class
from .serializers.base import BaseSerializer, WritableTextStream, WritableBinaryStream

# pick fastest available serializer as the default, always!
try:
    from .serializers.orjson import OrjsonSerializer as DefaultSerializer
except ImportError:
    from .serializers.json import JsonSerializer as DefaultSerializer


__all__ = [
    "Config",
    "Codec",
]


@struct(slots=True)
class Config:
    metadata: Metadata = Metadata()
    source: TypeHandlerFormat = "unstruct"
    target: TypeHandlerFormat = "unstruct"
    coerce: bool = False
    validate: bool = False
    convert: bool = False
    include: JsonPath = JsonPath.everything
    exclude: JsonPath = JsonPath.nothing
    exclude_none: bool = False
    exclude_unset: bool = False
    exclude_default: bool = False
    extras_mode: ExtrasMode = "forbid"
    patches: Patches = Patches.empty


class Codec:
    format_translation: dict[CodecFormat, TypeHandlerFormat] = {
        "jsonstr": "json",
        "jsonbytes": "json",
        "binstream": "json",
        "textstream": "json",
        "json": "json",
        "struct": "struct",
        "unstruct": "unstruct",
    }

    def __init__(
        self,
        serializers: Mapping[str, BaseSerializer] | None = None,
        type_handler_registry: TypeHandlerRegistry = default_type_handler_registry,
    ) -> None:
        if not serializers:
            serializers = {"default": DefaultSerializer()}
        self._serializers = serializers
        self._type_handler_registry = type_handler_registry
        self._cache_handlers: dict[
            tuple[FuzzyTypeHint, Constraints, TypeHintValue], "TypeHandler"
        ] = {}
        self._type_handler_registry.add_register_callback(self._cache_handlers.clear)
        # LRU cache for Config instances with optimized key generation
        self._config_cache = LRU(1024)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}()"

    def _create_config(
        self,
        metadata: Metadata,
        source: CodecFormat,
        target: CodecFormat,
        coerce: bool,
        validate: bool,
        convert: bool,
        include: JsonPath,
        exclude: JsonPath,
        exclude_none: bool,
        exclude_unset: bool,
        exclude_default: bool,
        extras_mode: ExtrasMode,
        patches: Patches,
    ) -> "Config":
        key = hash(
            (
                metadata,
                self.format_translation[source],
                self.format_translation[target],
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

    def get_type_handler(
        self,
        type_hint: FuzzyTypeHint,
        constraints: Constraints = Constraints.empty,
        type_hint_value: TypeHintValue = Empty,
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
                if type_hint_value is Empty:
                    raise ValueError(
                        "type_hint_value must be given when getting the type handler for ClassVar or Final"
                    )
            elif type_hint_value is not Empty:
                type_hint_value = (
                    Empty  # always ignore the value otherwise so instances dont explode
                )
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
            type_handler_class = self._type_handler_registry.get(
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

    def execute(
        self,
        input: Any,
        type_hint: UnresolvedTypeHint | Empty = Empty,
        type_hint_value: TypeHintValue | Empty = Empty,
        metadata: Metadata = Metadata(),
        source: CodecFormat | Empty = Empty,
        target: CodecFormat | Empty = Empty,
        coerce: bool = False,
        validate: bool = False,
        convert: bool = False,
        include: JsonPath = JsonPath.everything,
        exclude: JsonPath = JsonPath.nothing,
        exclude_none: bool = False,
        exclude_unset: bool = False,
        exclude_default: bool = False,
        extras_mode: ExtrasMode = "forbid",
        patches: Patches = Patches.empty,
        serializer: str = "default",
        output: WritableTextStream | WritableBinaryStream | Empty = Empty,
    ) -> Any:
        # if none of the flags are set, highly likely caller just forgot
        if not coerce and not validate and not convert:
            raise ValueError("coerce or validate or convert must be true")
        if type_hint is Empty:
            if is_struct_instance(input):
                type_hint = input.__class__
                if source is Empty:
                    source = "struct"
            else:
                # while it may be possible to guess the type hint in some cases, it may be slow
                # and error prone. user should generally provide it in most cases when not simply
                # working with structs to avoid ambiguous type inference
                raise ValueError(
                    "type_hint must be given when value is not a model instance"
                )
        if source is Empty:
            if is_struct_instance(input):
                source = "struct"
            else:
                is_type_hint_struct = is_struct_class(type_hint)
                if is_type_hint_struct and isinstance(input, str):
                    source = "jsonstr"
                elif is_type_hint_struct and isinstance(input, (bytes, bytearray)):
                    source = "jsonbytes"
                elif hasattr(input, "read"):
                    source = "textstream" if hasattr(input, "encoding") else "binstream"
                else:
                    # other option is a dict. if a dict, possible it is a dict of json-encoded
                    # fields and values OR it is a dict of python types. no great way to tell
                    # in a reliable way one or the other
                    raise ValueError(
                        "source format cannot be inferred, please explicitly provide it."
                    )
        if target is Empty:
            if output is not Empty and hasattr(output, "write"):
                target = "textstream" if hasattr(output, "encoding") else "binstream"
            else:
                # NOTE: source and target are allowed to be the same thing, so we can perform a copy
                target = source

        pointer = JsonPointer.root

        excluded = exclude.matches(pointer)
        if excluded:
            if target == "jsonbytes":
                return b""
            elif target == "jsonstr":
                return ""
            return Empty  # binstream/textstream we do nothing
        included = include.matches(pointer)

        try:
            ser = self._serializers[serializer]
        except KeyError:
            raise ValueError(f"No serializer found with this name, {serializer}")

        # if some sort of json encoded data in bytes/string form, we want to handle special cases where we just need
        # to encode or decode and then fallback to normal deserialization
        if source == "jsonbytes":
            if not coerce and not validate:
                if target == "jsonbytes":
                    return input
                elif target == "jsonstr":
                    return input.decode(encoding=ser.encoding)
            input = ser.from_bytes(input)
        elif source == "jsonstr":
            if not coerce and not validate:
                if target == "jsonstr":
                    return input
                elif target == "jsonbytes":
                    return input.encode(encoding=ser.encoding)
            input = ser.from_str(input)
        # if some sort of io stream, either specially handle if caller just wants to transfer to another stream
        # or else handle different special cases to move data between streams instead of deserializing
        # if going from bin/textstream to another bin/textstream, we can bypass converting to native types
        # so long as we do not need to validate or coerce the data in between, which requires native types
        if source == "binstream":
            if not coerce and not validate:
                if target == "binstream":
                    shutil.copyfileobj(input, output)
                    return Empty
                elif target == "textstream":
                    # fast path - where we bypass text conversion and copy from one to other
                    # safe because both files should use exact same encoding
                    if hasattr(output, "buffer"):
                        output.flush()  # make sure to flush out any currently buffered text
                        shutil.copyfileobj(input, output.buffer)
                        return Empty
                    # otherwise, we need to decode binary to text so the output text stream will accept it
                    input_buffer = TextIOWrapper(input, encoding=ser.encoding)
                    try:
                        shutil.copyfileobj(input_buffer, output)
                    finally:
                        input_buffer.detach()
                    return Empty
            input = ser.from_binary_stream(input)
        elif source == "textstream":
            if not coerce and not validate:
                if target == "textstream":
                    # fast path - if we can access binary buffer on both we should be able to copy data
                    # without text decoding on input side and encoding on output side. safe b/c same encoding.
                    if hasattr(input, "buffer") and hasattr(output, "buffer"):
                        output.flush()
                        shutil.copyfileobj(input.buffer, output.buffer)
                        return Empty
                    # otherwise, fallback to just doing decoding/encoding
                    shutil.copyfileobj(input, output)
                    return Empty
                elif target == "binstream":
                    # fast path - for streams exposing their binary buffer, which we can copy from directly
                    # safe again b/c encoding should be the same everywhere
                    if hasattr(input, "buffer"):
                        shutil.copyfileobj(input.buffer, output)
                        return Empty
                    # otherwise we need to handle re-encoding ourselves before sending to binary stream
                    input_read = partial(input.read, size=DEFAULT_BUFFER_SIZE)
                    output_write = output.write
                    enc = partial(str.encode, encoding="utf-8")
                    while textbuf := input_read():
                        output_write(enc(textbuf))
                    return Empty
            input = ser.from_text_stream(input)

        if patches:
            input = patches.patch("source", "value", pointer, input)

        type_handler = self.get_type_handler(
            type_hint=type_hint, type_hint_value=type_hint_value
        )
        input, issues = type_handler.handle(
            value=input,
            pointer=pointer,
            included=included,
            excluded=excluded,
            config=self._create_config(
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
            ),
        )
        if issues:
            raise ValidationError(issues=issues)

        if patches:
            input = patches.patch("target", "value", pointer, input)

        if (included and not excluded) or input is not Empty:
            if target in ("struct", "unstruct", "json"):
                return input
            elif target == "jsonstr":
                return ser.to_str(input)
            elif target == "jsonbytes":
                return ser.to_bytes(input)
            elif target == "binstream":
                return ser.to_binary_stream(input, output)
            else:
                return ser.to_text_stream(input, output)

        if target == "jsonbytes":
            return b""
        elif target == "jsonstr":
            return ""
        return Empty  # i think??? this is the right thing to return in the case where we dont actually want to
        # return anything. None would be normal but it is technically a valid json value
