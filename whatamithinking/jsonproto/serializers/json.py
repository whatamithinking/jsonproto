from typing import Any
from functools import partial
from json import (
    dumps,
    dump,
    loads,
    load,
    JSONEncoder,
    JSONDecodeError,
    JSONDecoder,
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


class JsonSerializer(BaseSerializer):

    def __init__(
        self,
        skipkeys: bool = False,
        check_circular: bool = False,  # not worth runtime overhead
        allow_nan: bool = False,
        indent: int | None = None,
        separators: tuple[str, str] = (",", ":"),
        sort_keys: bool = False,
        strict: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._dumps = partial(
            dumps,
            strict=strict,
            cls=JSONEncoder(
                skipkeys=skipkeys,
                check_circular=check_circular,
                allow_nan=allow_nan,
                indent=indent,
                separators=separators,
                sort_keys=sort_keys,
            ),
        )
        self._dump = partial(
            dump,
            strict=strict,
            cls=JSONEncoder(
                skipkeys=skipkeys,
                check_circular=check_circular,
                allow_nan=allow_nan,
                indent=indent,
                separators=separators,
                sort_keys=sort_keys,
            ),
        )
        self._loads = partial(loads, cls=JSONDecoder(strict=strict))
        self._load = partial(load, cls=JSONDecoder(strict=strict))

    def from_str(self, value: str) -> Any:
        try:
            return self._loads(value)
        except TypeError as exc:
            raise ValidationError(
                [
                    DeserializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def to_str(self, value: Any) -> str:
        try:
            return self._dumps(value)
        except TypeError as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def from_bytes(self, value: BytesLike) -> Any:
        try:
            return self._loads(value)
        except TypeError as exc:  # handle case where memoryview given
            try:
                return self._loads(value.tobytes())
            except AttributeError:
                raise ValidationError(
                    [
                        DeserializeIssue(
                            value=value, pointer=JsonPointer.root, message=exc.args[0]
                        )
                    ]
                ) from exc
            except TypeError as exc2:
                raise ValidationError(
                    [
                        DeserializeIssue(
                            value=value, pointer=JsonPointer.root, message=exc2.args[0]
                        )
                    ]
                ) from exc2

    def to_bytes(self, value: Any) -> bytes:
        try:
            return self._dumps(value).encode(self.encoding)
        except TypeError as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def from_binary_stream(self, value: ReadableBinaryStream) -> Any:
        try:
            return self._load(value)
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
            # stdlib python does not support byte mode files, so we do the write manually
            stream.write(self.to_bytes(value))
        except TypeError as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc

    def from_text_stream(self, value: ReadableTextStream) -> Any:
        try:
            return self._load(value)
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
            self._dump(value, stream)
        except TypeError as exc:
            raise ValidationError(
                [
                    SerializeIssue(
                        value=value, pointer=JsonPointer.root, message=exc.args[0]
                    )
                ]
            ) from exc
