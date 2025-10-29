from typing import Any, cast, TYPE_CHECKING, Callable
from base64 import (
    b16decode,
    b32decode,
    b32hexdecode,
    b64decode,
    b16encode,
    b32encode,
    b32hexencode,
    b64encode,
)
import binascii
from functools import partial
from contextlib import suppress

if TYPE_CHECKING:
    from .._codec import Config

from .._common import identity
from .._errors import ConstraintError
from .._pointers import JsonPointer
from .._common import Empty
from .._issues import (
    DecodingIssue,
    EncodingIssue,
    JsonTypeIssue,
    BaseIssue,
    PythonTypeIssue,
    LengthIssue,
    FormatIssue,
)
from .._constraints import Length, Encoding

from .base import TypeHandler, register_default_type_handler

__all__ = [
    "BytesHandler",
    "ByteArrayHandler",
    "MemoryViewHandler",
]


T_BytesLike = bytes | bytearray | memoryview


class BytesLikeHandler(TypeHandler):
    data_type = "string"
    media_type = "application/octet-stream"
    encoding = "base64"
    structure_class: type
    structure: Callable[[T_BytesLike], Any]
    copy_structure: Callable[[Any], Any]
    destructure_class: T_BytesLike
    destructure: Callable[[Any], T_BytesLike]

    @staticmethod
    def _decode_base16(value: str) -> bytes:
        return b16decode(value)

    @staticmethod
    def _decode_base32(value: str) -> bytes:
        return b32decode(value)

    @staticmethod
    def _decode_base32hex(value: str) -> bytes:
        return b32hexdecode(value)

    @staticmethod
    def _decode_base64(value: str) -> bytes:
        return b64decode(value)

    _decoders = {
        "base16": _decode_base16,
        "base32": _decode_base32,
        "base32hex": _decode_base32hex,
        "base64": _decode_base64,
    }

    @staticmethod
    def _encode_base16(value: T_BytesLike) -> str:
        return b16encode(value).decode()

    @staticmethod
    def _encode_base32(value: T_BytesLike) -> str:
        return b32encode(value).decode()

    @staticmethod
    def _encode_base32hex(value: T_BytesLike) -> str:
        return b32hexencode(value).decode()

    @staticmethod
    def _encode_base64(value: T_BytesLike) -> str:
        return b64encode(value).decode()

    _encoders = {
        "base16": _encode_base16,
        "base32": _encode_base32,
        "base32hex": _encode_base32hex,
        "base64": _encode_base64,
    }

    def _validate_length_eq(
        self, limit: int, value: str, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if len(value) == limit:
            return ()
        return [
            LengthIssue(
                comparator="eq",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_lt(
        self, limit: int, value: str, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if len(value) < limit:
            return ()
        return [
            LengthIssue(
                comparator="lt",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_le(
        self, limit: int, value: str, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if len(value) <= limit:
            return ()
        return [
            LengthIssue(
                comparator="le",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_ge(
        self, limit: int, value: str, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if len(value) >= limit:
            return ()
        return [
            LengthIssue(
                comparator="ge",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_gt(
        self, limit: int, value: str, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if len(value) > limit:
            return ()
        return [
            LengthIssue(
                comparator="gt",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def build(self) -> None:
        self._validators = []
        if not self.constraints:
            return
        len_min_inc = len_min_exc = len_max_inc = len_max_exc = len_eq = None
        for constraint in self.constraints:
            match constraint.constraint_type:
                case "encoding":
                    constraint = cast(Encoding, constraint)
                    self.encoding = constraint.value
                case "length":
                    constraint = cast(Length, constraint)
                    match constraint.comparator:
                        case "eq":
                            len_eq = constraint
                        case "lt":
                            len_max_exc = constraint
                        case "le":
                            len_max_inc = constraint
                        case "ge":
                            len_min_inc = constraint
                        case "gt":
                            len_min_exc = constraint

        # encoding must always be used. default to base64 since that is most common
        try:
            self._decoder = self._decoders[self.encoding]
            self._encoder = self._encoders[self.encoding]
        except KeyError:
            raise ConstraintError(
                message=f"Encoding, {self.encoding!r}, is not supported by {self.__class__.__qualname__}"
            )

        # consolidate length constraints to get union of all to avoid duplicate checks
        if len_eq is not None:
            self._validators.append(
                partial(self._validate_length_eq, limit=len_eq.value)
            )
        else:
            if len_min_inc is not None and len_min_exc is not None:
                if len_min_inc.value > len_min_exc.value:
                    len_min_exc = None
                else:
                    len_min_inc = None
            if len_min_inc is not None:
                self._validators.append(
                    partial(self._validate_length_ge, limit=len_min_inc.value)
                )
            elif len_min_exc is not None:
                self._validators.append(
                    partial(self._validate_length_gt, limit=len_min_exc.value)
                )
            if len_max_inc is not None and len_max_exc is not None:
                if len_max_inc.value < len_max_exc.value:
                    len_min_exc = None
                else:
                    len_min_inc = None
            if len_max_inc is not None:
                self._validators.append(
                    partial(self._validate_length_le, limit=len_max_inc.value)
                )
            elif len_max_exc is not None:
                self._validators.append(
                    partial(self._validate_length_lt, limit=len_max_exc.value)
                )

    def coerce(self, value: Any, pointer: JsonPointer, config: "Config") -> Any:
        if config.source != "json" and value.__class__ is not self.structure_class:
            with suppress(TypeError):
                return self.structure(value)
        return value

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        issues = []
        if not included or excluded or value is Empty:
            return Empty, issues
        converted = coerced = value
        if config.coerce:
            converted = coerced = self.coerce(value=value, pointer=pointer, config=config)
        if config.source == "json":
            is_json_type = True
            if converted.__class__ is not str:
                is_json_type = False
                issues.append(
                    JsonTypeIssue(
                        value=converted,
                        pointer=pointer,
                        expected_type="string",
                    )
                )
            if config.validate:
                if self._validators:
                    issues.extend(
                        issue
                        for validator in self._validators
                        for issue in validator(value=converted, pointer=pointer)
                    )
            if is_json_type and (config.validate or (config.convert and config.target != "json")):
                try:
                    converted = self._decoder(converted)
                except (ValueError, binascii.Error):
                    issues.append(
                        DecodingIssue(
                            value=converted,
                            pointer=pointer,
                            encoding=self.encoding,
                        )
                    )
                try:
                    converted = self.structure(converted)
                except ValueError:
                    issues.append(
                        FormatIssue(
                            value=converted, pointer=pointer, format=self.format
                        )
                    )
                except TypeError:
                    issues.append(
                        JsonTypeIssue(
                            value=converted, pointer=pointer, expected_type="string"
                        )
                    )
        else:
            is_python_type = True
            if converted.__class__ is not self.structure_class:
                is_python_type = False
                issues.append(
                    PythonTypeIssue(
                        value=converted,
                        pointer=pointer,
                        expected_type=self.structure_class,
                    )
                )
            if config.validate:
                if self._validators and self.structure_class is self.destructure_class:
                    issues.extend(
                        issue
                        for validator in self._validators
                        for issue in validator(value=converted, pointer=pointer)
                    )
            if is_python_type and config.convert:
                if config.target == "json":
                    if converted.__class__ is not self.destructure_class:
                        try:
                            converted = self.destructure(converted)
                        except TypeError:
                            issues.append(
                                PythonTypeIssue(
                                    value=converted,
                                    pointer=pointer,
                                    expected_type=self.structure_class,
                                )
                            )
                    try:
                        converted = self._encoder(converted)
                    except (ValueError, binascii.Error):
                        issues.append(
                            EncodingIssue(
                                value=converted,
                                pointer=pointer,
                                encoding=self.encoding,
                            )
                        )
                else:
                    # make a copy of the data, as needed. if immutable, passthrough
                    try:
                        converted = self.copy_structure(converted)
                    except TypeError:
                        issues.append(
                            PythonTypeIssue(
                                value=converted,
                                pointer=pointer,
                                expected_type=self.structure_class,
                            )
                        )

        if config.convert:
            return converted, issues
        elif config.coerce:
            return coerced, issues
        else:
            return value, issues


@register_default_type_handler(bytes)
class BytesHandler(BytesLikeHandler):
    structure_class = bytes
    structure = structure_class
    copy_structure = staticmethod(identity)
    destructure_class = structure_class
    destructure = structure_class


@register_default_type_handler(bytearray)
class ByteArrayHandler(BytesLikeHandler):
    structure_class = bytearray
    structure = structure_class
    copy_structure = structure_class
    destructure_class = structure_class
    destructure = structure_class


@register_default_type_handler(memoryview)
class MemoryViewHandler(BytesLikeHandler):
    structure_class = memoryview
    structure = structure_class
    copy_structure = staticmethod(identity)
    destructure_class = structure_class
    destructure = structure_class
