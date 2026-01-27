from typing import Any, Protocol
from types import MappingProxyType

from .._constraints import T_DataType


type BytesLike = bytes | bytearray | memoryview


class ReadableBinaryStream(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


class WritableBinaryStream(Protocol):
    def write(self, buffer: BytesLike, /) -> int: ...
    def flush(self) -> None: ...


class ReadableTextStream(Protocol):
    def read(self, size: int = -1, /) -> str: ...


class WritableTextStream(Protocol):
    def write(self, s: str, /) -> int: ...
    def flush(self) -> None: ...


class BaseSerializer:
    json_to_native_types: MappingProxyType[T_DataType, type] = MappingProxyType({
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": float,
        "boolean": bool,
        "null": None,
    })
    
    def __init__(self, encoding: str = "utf-8") -> None:
        self.encoding = encoding

    def from_str(self, value: str) -> Any:
        ...

    def to_str(self, value: Any) -> str:
        ...

    def from_bytes(self, value: BytesLike) -> Any:
        ...
    
    def to_bytes(self, value: Any) -> BytesLike:
        ...

    def from_binary_stream(self, value: ReadableBinaryStream) -> Any:
        ...

    def to_binary_stream(self, value: Any, stream: WritableBinaryStream) -> None:
        ...

    def from_text_stream(self, value: ReadableTextStream) -> Any:
        ...

    def to_text_stream(self, value: Any, stream: WritableTextStream) -> None:
        ...
