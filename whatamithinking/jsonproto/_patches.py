from typing import Literal, Any, Union

from lru import LRU

from ._pointers import JsonPath, JsonPointer
from ._common import MISSING

__all__ = ["Patches"]


T_PatchFormatType = Literal["source", "target"]
T_PatchMode = Literal["value", "key"]
T_PatchValue = Any
T_PatchFull = tuple[JsonPath | str, T_PatchValue, T_PatchFormatType, T_PatchMode]
T_Patch = (
    tuple[JsonPath | str, T_PatchValue]
    | tuple[JsonPath | str, T_PatchValue, T_PatchFormatType]
    | tuple[JsonPath | str, T_PatchValue, T_PatchMode]
    | T_PatchFull
)


class Patches:
    """A collection of updates to make to data, which are applied from earliest
    in the collection to latest and based on what JsonPath matches the given JsonPointer
    first."""
    __slots__ = "_cache", "_patches", "_hash"

    _instance_cache = LRU(1024)
    _patches: dict[
        tuple[T_PatchFormatType, T_PatchMode],  # type: ignore
        list[tuple[JsonPath, Any]],
    ]
    empty: "Patches" = None

    def __new__(cls, *args: Union["Patches", T_Patch]) -> "Patches":
        try:
            self = cls._instance_cache[args]
        except KeyError:
            if not args:
                raise ValueError("Use Patches.empty instead")
            nargs = list[T_PatchFull]()
            for patch in args:
                format = "source"
                mode = "value"
                match patch:
                    case Patches() as patches_:
                        nargs.extend(
                            (p, v, f, m)
                            for (f, m), fmv in patches_._patches.items()
                            for p, v in fmv
                        )
                        continue
                    case (JsonPath() | str() as path, value):
                        pass
                    case (JsonPath() | str() as path, value, T_PatchFormat as format):
                        pass
                    case (JsonPath() | str() as path, value, T_PatchMode as mode):
                        pass
                    case (
                        JsonPath() | str() as path,
                        value,
                        T_PatchFormat as format,
                        T_PatchMode as mode,
                    ):
                        pass
                if path.__class__ is str:
                    path = JsonPath(path)
                nargs.append((path, value, format, mode))
            nargs = tuple(nargs)
            try:
                self = cls._instance_cache[nargs]
            except KeyError:
                self = super().__new__(cls)
                self._patches = {}
                for path, value, format, mode in nargs:
                    self._patches.setdefault((format, mode), []).append((path, value))
                cls._instance_cache[args] = self
                cls._instance_cache[nargs] = self
                cls._instance_cache[(self,)] = self
        return self

    def __hash__(self) -> int:
        try:
            return self._hash
        except AttributeError:
            self._hash = hash(tuple(sorted(self._patches.items())))

    def __bool__(self) -> bool:
        return bool(self._patches)

    def have_for(self, format_type: T_PatchFormatType, mode: T_PatchMode) -> bool:
        """Return True if there are any patches for the given filters and False otherwise"""
        if not self._patches:
            return False
        return (format_type, mode) in self._patches

    def patch(
        self,
        format_type: T_PatchFormatType,
        mode: T_PatchMode,
        pointer: JsonPointer | str,
        value: Any,
    ) -> Any:
        """Try to patch the given value, but fallback to returning the value itself 
        if no patch found."""
        if self._patches and (patches := self._patches.get((format_type, mode))):
            cache_key = (format_type, mode, pointer)
            try:
                patch_value = self._cache[cache_key]
            except (AttributeError, KeyError) as exc:
                if exc.__class__ is AttributeError:
                    self._cache = LRU(1024)
                for patch_path, patch_value in patches:
                    if patch_path.matches(pointer):
                        break
                else:
                    patch_value = MISSING
                self._cache[cache_key] = patch_value
            if patch_value is not MISSING:
                return patch_value
        return value


class _EmptyPatches(Patches):
    __slots__ = ()
    _hash = hash(())

    def __bool__(self) -> bool:
        return False

    def have_for(self, format_type, mode):
        return False

    def patch(self, format_type, mode, pointer, value):
        return value


Patches.empty = object.__new__(_EmptyPatches)
