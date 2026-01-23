from typing import Any, cast, TYPE_CHECKING, Callable, Self
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
import re

if TYPE_CHECKING:
    from .._codec import Config

from .._common import identity
from .._errors import ConstraintError
from .._pointers import JsonPointer
from .._common import Empty, Empty
from .._issues import (
    DecodingIssue,
    EncodingIssue,
    JsonTypeIssue,
    BaseIssue,
    StructTypeIssue,
    LengthIssue,
    PatternIssue,
    FormatIssue,
)
from .._constraints import (
    Length,
    Encoding,
    Pattern,
)

from .base import TypeHandler, default_type_handler_registry

__all__ = ["StringHandler"]


def is_structure_class(self: "StringHandler", obj: Any) -> bool:
    return obj.__class__ is self.structure_class


@default_type_handler_registry.register(type_hint=str)
class StringHandler(TypeHandler):
    data_type = "string"
    media_type = "text/plain"
    structure_class: type = str
    is_structure_class: Callable[[Self, Any], bool] = is_structure_class
    structure: Callable[[str], Any] = str
    copy_structure: Callable[[Any], Any] = staticmethod(identity)
    destructure_class: type = str
    destructure: Callable[[Any], str] = str

    @staticmethod
    def _decode_base16(value: str) -> str:
        return b16decode(value).decode()

    @staticmethod
    def _decode_base32(value: str) -> str:
        return b32decode(value).decode()

    @staticmethod
    def _decode_base32hex(value: str) -> str:
        return b32hexdecode(value).decode()

    @staticmethod
    def _decode_base64(value: str) -> str:
        return b64decode(value).decode()

    _decoders = {
        "base16": _decode_base16,
        "base32": _decode_base32,
        "base32hex": _decode_base32hex,
        "base64": _decode_base64,
    }

    @staticmethod
    def _encode_base16(value: str) -> str:
        return b16encode(value.encode()).decode()

    @staticmethod
    def _encode_base32(value: str) -> str:
        return b32encode(value.encode()).decode()

    @staticmethod
    def _encode_base32hex(value: str) -> str:
        return b32hexencode(value.encode()).decode()

    @staticmethod
    def _encode_base64(value: str) -> str:
        return b64encode(value.encode()).decode()

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

    def _validate_pattern(
        self, pattern: re.Pattern, value: str, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if not pattern.fullmatch(value):
            return [
                PatternIssue(
                    value=value,
                    pointer=pointer,
                    pattern=pattern,
                )
            ]
        return ()

    def build(self) -> None:
        self._validators = []
        if not self.constraints:
            return
        len_min_inc = len_min_exc = len_max_inc = len_max_exc = len_eq = None
        seen = set[str]()
        for constraint in self.constraints:
            if constraint.constraint_id in seen:
                continue
            match constraint.constraint_type:
                case "encoding":
                    constraint = cast(Encoding, constraint)
                    self.encoding = constraint.value
                    try:
                        self._decoder = self._decoders[self.encoding]
                        self._encoder = self._encoders[self.encoding]
                    except KeyError:
                        raise ConstraintError(
                            message=f"Encoding, {self.encoding!r}, is not supported by {self.__class__.__qualname__}",
                            constraint=constraint,
                        )
                case "pattern":
                    constraint = cast(Pattern, constraint)
                    self._validators.append(
                        partial(self._validate_pattern, pattern=constraint.pattern)
                    )
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
                # NOTE: all formats skipped here because it is assumed those will always
                # be parsed into native types instead of leaving as strings

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
        if self.structure_class is not str:
            if config.source != "json" and value.__class__ is str:
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
            converted = coerced = self.coerce(
                value=value, pointer=pointer, config=config
            )
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
            if is_json_type and (
                config.validate or (config.convert and config.target != "json")
            ):
                if self.encoding:
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
            is_struct_type = True
            if not self.is_structure_class(converted):
                is_struct_type = False
                issues.append(
                    StructTypeIssue(
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
            if is_struct_type and config.convert:
                if config.target == "json":
                    if converted.__class__ is not self.destructure_class:
                        try:
                            converted = self.destructure(converted)
                        except TypeError:
                            issues.append(
                                StructTypeIssue(
                                    value=converted,
                                    pointer=pointer,
                                    expected_type=self.structure_class,
                                )
                            )
                    if self.encoding:
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
                            StructTypeIssue(
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
