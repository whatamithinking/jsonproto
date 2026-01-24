from typing import Any, Callable
from functools import partial

from .._constraints import T_DataType
from .._common import T_CodecSerializationFormat
from .._errors import ValidationError
from .._issues import SerializeIssue, DeserializeIssue
from .._pointers import JsonPointer

from json import (
    dumps,
    loads,
    JSONEncoder,
    JSONDecodeError,
    JSONDecoder,
)


class JsonSerializer:
    deserialize_types: dict[T_DataType, type] = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "null": None,
    }
    serialize_types = dict[type, T_DataType] = {
        dict: "object",
        list: "array",
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        None: "null",
    }
    #TODO: figure out how to update these mappings if caller provides custom handlers for parsing stuff

    def __init__(
        self,
        skipkeys: bool = False,
        ensure_ascii: bool = False,  # utf std now, not needed
        check_circular: bool = False,  # not worth runtime overhead
        allow_nan: bool = False,
        indent: int | None = None,
        separators: tuple[str, str] = (",", ":"),
        sort_keys: bool = False,
        parse_float: Callable[[str], Any] | None = None,
        parse_int: Callable[[str], Any] | None = None,
        parse_constant: Callable[[str], Any] | None = None,
        strict: bool = True,
        object_hook: Callable[[dict], Any] | None = None,
        object_pairs_hook: Callable[[list[tuple[str, Any]]], Any] | None = None,
        default: Callable | None = None,
    ) -> None:
        self._dumps = partial(
            dumps,
            parse_float=parse_float,
            parse_int=parse_int,
            parse_constant=parse_constant,
            strict=strict,
            object_hook=object_hook,
            cls=JSONEncoder(
                skipkeys=skipkeys,
                ensure_ascii=ensure_ascii,
                check_circular=check_circular,
                allow_nan=allow_nan,
                indent=indent,
                separators=separators,
                sort_keys=sort_keys,
                default=default,
            ),
        )
        self._loads = partial(
            loads,
            cls=JSONDecoder(
                parse_float=parse_float,
                parse_int=parse_int,
                parse_constant=parse_constant,
                strict=strict,
                object_hook=object_hook,
                object_pairs_hook=object_pairs_hook,
            ),
        )

    def serialize(self, value: Any, target: T_CodecSerializationFormat) -> str | bytes:
        try:
            data = self._dumps(value)
        except TypeError as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc
        if target == "jsonbytes":
            return data
        return data.decode()

    def deserialize(self, value: bytes | str) -> Any:
        try:
            return self._loads(value)
        except JSONDecodeError as exc:
            raise ValidationError(
                [
                    DeserializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc
