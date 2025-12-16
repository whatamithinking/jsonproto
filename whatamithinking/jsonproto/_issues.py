from typing import ClassVar, Any
import re
from numbers import Number
from types import NoneType
from collections.abc import Mapping, Sequence

from ._struct import struct, field
from ._constraints import (
    T_DataType,
    T_Format,
    T_Encoding,
    T_LengthComparator,
    T_ValueComparator,
)
from ._pointers import JsonPointer
from ._common import JsonType


@struct
class BaseIssue:
    issue_type: ClassVar[str]
    value: JsonType
    pointer: JsonPointer


@struct
class SerializeIssue(BaseIssue):
    issue_type: ClassVar[str] = "serialize"
    message: str


@struct
class DeserializeIssue(BaseIssue):
    issue_type: ClassVar[str] = "deserialize"
    message: str


@struct
class StructTypeIssue(BaseIssue):
    issue_type: ClassVar[str] = "struct_type"
    expected_type: type

    @field(cache=True)
    def actual_type(self) -> type:
        return self.value.__class__


@struct
class JsonTypeIssue(BaseIssue):
    issue_type: ClassVar[str] = "json_type"
    expected_type: T_DataType

    @field(cache=True)
    def actual_type(self) -> T_DataType:
        match self.value:
            case NoneType():
                return "null"
            case bool():
                return "boolean"
            case int():
                return "integer"
            case float():
                return "number"
            case str():
                return "string"
            case Sequence():
                return "array"
            case Mapping():
                return "object"
            case _:
                raise ValueError(
                    "Cannot determine json data type name for given python object"
                )


@struct
class FormatIssue(BaseIssue):
    issue_type: ClassVar[str] = "format"
    format: T_Format


@struct
class DecodingIssue(BaseIssue):
    issue_type: ClassVar[str] = "decoding"
    encoding: T_Encoding


@struct
class EncodingIssue(BaseIssue):
    issue_type: ClassVar[str] = "encoding"
    encoding: T_Encoding


@struct
class PatternIssue(BaseIssue):
    issue_type: ClassVar[str] = "pattern"
    value: str
    pattern: re.Pattern


@struct
class LengthIssue(BaseIssue):
    issue_type: ClassVar[str] = "length"
    comparator: T_LengthComparator
    value: str | list
    limit: int

    @field(cache=True)
    def length(self) -> int:
        return len(self.value)


@struct
class NumberIssue(BaseIssue):
    issue_type: ClassVar[str] = "number"
    comparator: T_ValueComparator
    value: Number
    limit: Number


@struct
class ExtraFieldIssue(BaseIssue):
    issue_type: ClassVar[str] = "extra_field"
    extra: str


@struct
class MissingFieldIssue(BaseIssue):
    issue_type: ClassVar[str] = "missing_field"


@struct
class DependentIssue(BaseIssue):
    issue_type: ClassVar[str] = "dependent"
    dependent: frozenset[str]
    setted: frozenset[str]

    @field(cache=True)
    def missing(self) -> frozenset[str]:
        return self.dependent - self.setted


@struct
class DisjointIssue(BaseIssue):
    issue_type: ClassVar[str] = "disjoint"
    setted: frozenset[str]
    disjoint: frozenset[str]


@struct
class MissingDiscriminatorIssue(BaseIssue):
    issue_type: ClassVar[str] = "missing_discriminator"
    discriminator: str


@struct
class InvalidDiscriminatorIssue(BaseIssue):
    issue_type: ClassVar[str] = "invalid_discriminator"
    discriminator: str


@struct
class EnumOptionIssue(BaseIssue):
    issue_type: ClassVar[str] = "enum_option"
    options: frozenset


@struct
class ConstantIssue(BaseIssue):
    issue_type: ClassVar[str] = "constant"
    expected_value: Any
