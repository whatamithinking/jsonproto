from typing import Union, Self
import re

from lru import LRU

from ._errors import JsonPathError

__all__ = [
    "JsonPointer",
    "JsonPath",
]


T_JsonPointerPart = Union[str, int]
T_JsonPointerParts = tuple[T_JsonPointerPart, ...]


class JsonPointer:
    """JSON Pointer referring to exactly one node in a JSON structure"""

    __slots__ = "parts", "_hash", "_path", "_str", "_repr", "_cache"
    _instance_cache = LRU(65535)
    root: "JsonPointer" = None

    def __new__(cls, parts: T_JsonPointerParts = ("",)) -> "JsonPointer":
        cache = cls._instance_cache
        key = hash(parts)
        try:
            return cache[key]
        except KeyError:
            if len(parts) == 1 and not parts[0]:
                raise ValueError("Use JsonPointer.root instead")
            cache[key] = self = super().__new__(cls)
            self.parts = parts
            self._hash = key
            self._cache = LRU(1024)
            return self

    def path(self) -> str:
        try:
            return self._path
        except AttributeError:
            parts = self.parts
            len_parts = len(parts)
            if len_parts == 1:
                self._path = "$"
            elif len_parts == 2:
                if isinstance(parts[1], int):
                    self._path = f"$[{parts[1]}]"
                else:
                    self._path = f"$.{parts[1]}"
            elif len_parts == 3:
                if isinstance(parts[1], int):
                    if isinstance(parts[2], int):
                        self._path = f"$[{parts[1]}][{parts[2]}]"
                    else:
                        self._path = f"$[{parts[1]}].{parts[2]}"
                else:
                    if isinstance(parts[2], int):
                        self._path = f"$.{parts[1]}.[{parts[2]}]"
                    else:
                        self._path = f"$.{parts[1]}.{parts[2]}"
            else:
                self._path = f"${'.'.join(f"[{part}]" if isinstance(part, int) else part for part in parts)}"
            return self._path

    def __str__(self) -> str:
        try:
            return self._str
        except AttributeError:
            if not self.parts:
                self._str = "$"
            else:
                self._str = "/".join(map(str, self.parts))
            return self._str

    def __repr__(self) -> str:
        try:
            return self._repr
        except AttributeError:
            self._repr = f"JsonPointer({self._str!r})"
            return self._repr

    def __hash__(self) -> int:
        return self._hash

    def __gt__(self, other: Self) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return self.parts > other.parts

    def __lt__(self, other: Self) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return self.parts < other.parts

    def __ge__(self, other: Self) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return self.parts >= other.parts

    def __le__(self, other: Self) -> bool:
        if other.__class__ is not self.__class__:
            return NotImplemented
        return self.parts <= other.parts

    def join(self, other: T_JsonPointerPart) -> "JsonPointer":
        try:
            return self._cache[other]
        except KeyError:
            self._cache[other] = result = JsonPointer((*self.parts, other))
            return result


JsonPointer.root = object.__new__(JsonPointer)
JsonPointer.root.parts = ("",)
JsonPointer.root._hash = hash(JsonPointer.root.parts)
JsonPointer.root._cache = LRU(1024)
T_JsonPathArg = Union[str, JsonPointer, "JsonPath"]


class JsonPath:
    """A JSONPath expression pattern, which can match with zero or more JsonPointers,
    supporting a small subset of the full JSONPath spec.

    Supported:
        - Root element: $
        - Dot-notation for field name child: .fieldName
        - Bracket-notation for array index child: [0]
        - Positive array indices: 0, 1, 2, etc.
        - Non-recursive wildcard for fields and arrays: .*. or [*]
        - Recursive wildcard for fields and arrays: .. or [..]
        - Union of separate JSONPaths: <$.expr1>, <$.expr2>

    Not Supported:
        - Dot-notation for array index child: .0
        - Bracket-notation for field name child: ["fieldName"]
        - Negative array indices: -1, -2, etc.
        - Current node operator: @
        - Array slice: [start:end:step]
        - Filter expressions: ?()
        - Script expressions: ()
        - Field/array level unions: $.a.[b,d]

    Example: Match with all streetName nodes for all addresses
        $.addresses[*].streetName
    """

    __slots__ = (
        "_str",
        "_repr",
        "_hash",
        "_is_contains",
        "_contains_str",
        "_is_pattern",
        "_regex",
        "_cache",
        "_built",
    )

    _instance_cache = LRU(65535)
    everything: "JsonPath" = None
    nothing: "JsonPath" = None

    def __new__(cls, *args: T_JsonPathArg) -> "JsonPath":
        cache = cls._instance_cache
        try:
            self = cache[args]
        except KeyError:
            size = args.__len__()
            if size == 0 or (size == 1 and args[0] is None):
                raise ValueError("Use JsonPath.everything instead")
            elif size == 1:
                arg_cls = args[0].__class__
                if arg_cls is str:
                    path = args[0]
                    if not path:
                        raise ValueError("Use JsonPath.nothing instead")
                elif issubclass(arg_cls, JsonPath):
                    return args[0]
                elif arg_cls is JsonPointer:
                    path = args[0].path()
            else:
                path = ",".join(getattr(o, "path", o.__str__)() for o in args)
            self = super().__new__(cls)
            self._str = path
            cache[args] = self
            cache[(path,)] = self
        return self

    def __str__(self) -> str:
        return self._str

    def __repr__(self) -> str:
        try:
            return self._repr
        except AttributeError:
            self._repr = f"JsonPath({self._str!r})"
            return self._repr

    def __hash__(self) -> int:
        try:
            return self._hash
        except AttributeError:
            self._hash = hash(self._str)
            return self._hash

    def __or__(self, other: Union[str, JsonPointer, "JsonPath"]) -> "JsonPath":
        return JsonPath(self, other)  # specifically use JsonPath class!

    def _build(self) -> None:
        self._cache = LRU(1024)
        if (
            self._str.startswith("..")
            and self._str.endswith("..")
            and not any(
                _ in self._str[len("..") : -len("..")] for _ in (",", "*", "..")
            )
        ):
            self._constains_str = self._str[len("..") : -len("..")]
            self._is_contains = True
        else:
            self._is_contains = False
        if not self._is_contains:
            self._is_pattern = any(_ in self._str for _ in (",", "*", ".."))
            if self._is_pattern:
                try:
                    self._regex = re.compile(
                        self._str.replace(r" ", r"")
                        .replace(r"$", r"\$")
                        .replace(r",", r"|")
                        .replace(r".", r"\.")
                        .replace(r"[", r"\[")
                        .replace(r"]", r"\]")
                        .replace(r"\.*", r"\.\w+")
                        .replace(r"\.\.", r".*")
                        .replace(r"\[*\]", r"\[\d+\]")
                    )
                except re.error as exc:
                    raise JsonPathError("Error compiling JSONPath expression") from exc
        self._built = True

    def matches(self, value: Union[str, JsonPointer, "JsonPath"], /) -> bool:  # type: ignore
        try:
            self._built
        except AttributeError:
            self._build()
        try:
            result = self._cache[value]
        except KeyError:
            try:
                str_value = value.path()
            except AttributeError:
                str_value = str(value)
            # micro-optimization: if pattern is effectively just a check if the json path is contained
            # within the given pointer/path, just use python contains check. seems slightly faster
            if self._is_contains:
                result = self._constains_str in str_value
            # micro-optimization: if path is actually just a plain pointer, we can just do a string compare
            # instead of compiling into a regex and matching against that
            elif not self._is_pattern:
                result = self._str == str_value
            else:
                result = self._regex.fullmatch(str_value) is not None
            self._cache[value] = result
            self._cache[str_value] = result
        return result


class _EverythingJsonPath(JsonPath):
    __slots__ = ()
    _str = "$"

    def __new__(cls, *args):
        raise NotImplementedError

    def matches(self, value):
        return True


class _NothingJsonPath(JsonPath):
    __slots__ = ()
    _str = ""

    def __new__(cls, *args):
        raise NotImplementedError

    def matches(self, value):
        return False


JsonPath.everything = object.__new__(_EverythingJsonPath)
JsonPath.nothing = object.__new__(_NothingJsonPath)
