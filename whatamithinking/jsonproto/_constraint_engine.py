from typing import Callable, Iterable, Annotated
from whatamithinking.jsonproto import (
    Length,
    BaseIssue,
    JsonPointer,
    LengthIssue,
    Encoding,
    DecodingIssue,
    DataType,
    JsonTypeIssue,
)
from base64 import b32hexdecode, b32hexencode
import binascii


T_ConstrainedString = Annotated[
    str,
    Length("le", 99),
    Encoding("base32hex"),
]


def validate_json_type(
    constraint: DataType,
) -> Callable[[str, JsonPointer], tuple[str, Iterable[LengthIssue]]]:
    expected_type = constraint.value

    def validate_data_type_string_inner(
        value: str, pointer: JsonPointer
    ) -> tuple[str, Iterable[LengthIssue]]:
        if value.__class__ is str:
            return value, ()
        return value, (
            JsonTypeIssue(
                value=value,
                pointer=pointer,
                expected_type=expected_type,
            ),
        )

    return validate_data_type_string_inner


def validate_length_le(
    constraint: Length,
) -> Callable[[str, JsonPointer], tuple[str, Iterable[LengthIssue]]]:
    length = constraint.value

    def validate_length_le_inner(
        value: str, pointer: JsonPointer
    ) -> tuple[str, Iterable[LengthIssue]]:
        if value.__len__() <= length:
            return value, ()
        return value, (
            LengthIssue(
                comparator="le",
                value=value,
                pointer=pointer,
                limit=length,
            ),
        )

    return validate_length_le_inner


def validate_base32hex_json(
    constraint: Encoding,
) -> Callable[[str, JsonPointer], tuple[str, Iterable[DecodingIssue]]]:
    encoding = constraint.value

    def validate_base32hex_json_inner(
        value: str, pointer: JsonPointer
    ) -> tuple[str, Iterable[DecodingIssue]]:
        try:
            return b32hexdecode(value).decode(), ()
        except (ValueError, binascii.Error):
            return value, (
                DecodingIssue(
                    value=value,
                    pointer=pointer,
                    encoding=encoding,
                ),
            )

    return validate_base32hex_json_inner


def validate_base32hex_json(
    constraint: Encoding,
) -> Callable[[str, JsonPointer], tuple[str, Iterable[DecodingIssue]]]:
    encoding = constraint.value

    def validate_base32hex_json_inner(
        value: str, pointer: JsonPointer
    ) -> tuple[str, Iterable[DecodingIssue]]:
        try:
            return b32hexdecode(value).decode(), ()
        except (ValueError, binascii.Error):
            return value, (
                DecodingIssue(
                    value=value,
                    pointer=pointer,
                    encoding=encoding,
                ),
            )

    return validate_base32hex_json_inner
