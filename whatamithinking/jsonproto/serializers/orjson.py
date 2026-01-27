from typing import Any
from functools import partial

from orjson import (
    dumps,
    loads,
    JSONEncodeError,
    JSONDecodeError,
)

from .._errors import ValidationError
from .._issues import SerializeIssue, DeserializeIssue
from .._pointers import JsonPointer

from .base import (
    BaseSerializer,
    ReadableBinaryStream,
    WritableBinaryStream,
    ReadableTextStream,
    WritableTextStream,
    BytesLike,
)


class OrjsonSerializer(BaseSerializer):

    def __init__(self, option: int = 0, **kwargs) -> None:
        super().__init__(**kwargs)
        if self.encoding != "utf-8":
            raise ValueError("Only utf-8 encoding is supported")
        self._dumps = partial(dumps, option=option)

    def from_str(self, value: str) -> Any:
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

    def to_str(self, value: Any) -> str:
        try:
            return self._dumps(value).decode(self.encoding)
        except (TypeError, JSONEncodeError) as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc
    
    def from_bytes(self, value: BytesLike) -> Any:
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
    
    def to_bytes(self, value: Any) -> BytesLike:
        try:
            return self._dumps(value)
        except (TypeError, JSONEncodeError) as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def from_binary_stream(self, value: ReadableBinaryStream) -> Any:
        try:
            return loads(value.read())
        except JSONDecodeError as exc:
            raise ValidationError(
                [
                    DeserializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def to_binary_stream(self, value: Any, stream: WritableBinaryStream) -> None:
        try:
            stream.write(self._dumps(value))
        except (TypeError, JSONEncodeError) as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def from_text_stream(self, value: ReadableTextStream) -> Any:
        try:
            return loads(value.read())
        except JSONDecodeError as exc:
            raise ValidationError(
                [
                    DeserializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def to_text_stream(self, value: Any, stream: WritableTextStream) -> None:
        try:
            stream.write(self._dumps(value).decode(self.encoding))
        except (TypeError, JSONEncodeError) as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc
