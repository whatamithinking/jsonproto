from typing import Any
from functools import partial

from .._common import T_CodecSerializationFormat
from .._constraints import T_DataType
from .._errors import ValidationError
from .._issues import SerializeIssue, DeserializeIssue
from .._pointers import JsonPointer

from orjson import (
    dumps,
    loads,
    JSONEncodeError,
    JSONDecodeError,
)


class OrjsonSerializer:
    deserialize_types: dict[T_DataType, type] = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "null": None,
    }
    serialize_types = dict[type, T_DataType] = {}#TODO

    def __init__(self, option: int = 0) -> None:
        self._dumps = partial(dumps, option=option)

    def serialize(self, value: Any, target: T_CodecSerializationFormat) -> str | bytes:
        try:
            data = self._dumps(value)
        except (TypeError, JSONEncodeError) as exc:

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
            return loads(value)
        except JSONDecodeError as exc:
            raise ValidationError(
                [
                    DeserializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc
