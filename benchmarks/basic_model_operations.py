# type: ignore
from time import perf_counter
import importlib.metadata
from typing import NamedTuple, Callable
import textwrap


def get_standard_classes_template(frozen: bool, slots: bool) -> str:
    order_template = """
        def __{method}__(self, other):
            if type(self) is not type(other):
                return NotImplemented
            return (
                (self.a, self.b, self.c, self.d, self.e) {op}
                (other.a, other.b, other.c, other.d, other.e)
            )
    """

    classes_template = f"""        
    class C{{n}}:
        {"__slots__='a','b','c','d','e'" if slots else ''}
        
        def __init__(self, *, a, b, c, d, e):
            {"object.__setattr__(self, 'a', a)" if frozen else 'self.a = a'}
            {"object.__setattr__(self, 'b', b)" if frozen else 'self.b = b'}
            {"object.__setattr__(self, 'c', c)" if frozen else 'self.c = c'}
            {"object.__setattr__(self, 'd', d)" if frozen else 'self.d = d'}
            {"object.__setattr__(self, 'e', e)" if frozen else 'self.e = e'}

        {"def __setattr__(self, attr, value):" if frozen else ""}
        {"    raise AttributeError" if frozen else ""}

        def __repr__(self):
            return (
                f"{{{{type(self).__name__}}}}(a={{{{self.a!r}}}}, b={{{{self.b!r}}}}, "
                f"c={{{{self.c!r}}}}, d={{{{self.d!r}}}}, e={{{{self.e!r}}}})"
            )

        def __hash__(self):
            return hash((
                self.a,
                self.b,
                self.c,
                self.d,
                self.e,
            ))

        def __eq__(self, other):
            if type(self) is not type(other):
                return NotImplemented
            return (
                self.a == other.a and
                self.b == other.b and
                self.c == other.c and
                self.d == other.d and
                self.e == other.e
            )
    """ + "".join(
        [
            order_template.format(method="lt", op="<"),
            order_template.format(method="le", op="<="),
            order_template.format(method="gt", op=">"),
            order_template.format(method="ge", op=">="),
        ]
    )

    return classes_template


def get_attrs_template(frozen: bool, slots: bool) -> str:
    return f"""
    from attr import define

    
    @define(init=True, repr=True, eq=True, order=True, unsafe_hash=True, hash=True, kw_only=True, frozen={frozen}, slots={slots})
    class C{{n}}:
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_pyserde_template(frozen: bool, slots: bool) -> str:
    return f"""
    from serde import serde
    from dataclasses import dataclass
    
    @serde
    @dataclass(init=True, repr=True, eq=True, order=True, unsafe_hash=True, kw_only=True, frozen={frozen}, slots={slots})
    class C{{n}}:
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_dataclasses_template(frozen: bool, slots: bool) -> str:
    return f"""
    from dataclasses import dataclass

    
    @dataclass(init=True, repr=True, eq=True, order=True, unsafe_hash=True, kw_only=True, frozen={frozen}, slots={slots})
    class C{{n}}:
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_pydantic_basemodel_template(frozen: bool, slots: bool) -> str:
    if slots:
        return "raise NotImplementedError"

    return f"""
    from pydantic import BaseModel, ConfigDict

    
    class C{{n}}(BaseModel):
        model_config = ConfigDict(frozen={frozen}, defer_build=True)
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_pydantic_dataclasses_template(frozen: bool, slots: bool) -> str:
    return f"""
    from pydantic.dataclasses import dataclass

    
    # init has to be false here per pydantic restrictions
    @dataclass(init=False, repr=True, eq=True, order=True, unsafe_hash=True, kw_only=True, frozen={frozen}, slots={slots})
    class C{{n}}:
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_mashumaro_template(frozen: bool, slots: bool) -> str:
    return f"""
    from mashumaro import DataClassDictMixin
    from dataclasses import dataclass

    @dataclass(init=True, repr=True, eq=True, order=True, unsafe_hash=True, kw_only=True, frozen={frozen}, slots={slots})
    class C{{n}}(DataClassDictMixin):
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_dataclassy_template(frozen: bool, slots: bool) -> str:
    return f"""
    from dataclassy import dataclass

    
    @dataclass(init=True, repr=True, eq=True, order=True, unsafe_hash=True, kw_only=True, frozen={frozen}, slots={slots})
    class C{{n}}:
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_msgspec_template(frozen: bool, slots: bool) -> str:
    return f"""
    from msgspec import Struct


    class C{{n}}(Struct, frozen={frozen}, eq=True, order=True, kw_only=True, gc={slots}, cache_hash={frozen}):
        a: int
        b: int
        c: int
        d: int
        e: int
    """


def get_jsonproto_template(frozen: bool, slots: bool) -> str:
    return f"""
    import whatamithinking.jsonproto as jp
    
    
    @jp.struct(init=True, repr=True, eq=True, order=True, frozen={frozen}, kw_only=True, hash=True, slots={slots})
    class C{{n}}:
        a: int
        b: int
        c: int
        d: int
        e: int
    """


class Benchmark(NamedTuple):
    name: str
    library: str | None
    get_template: Callable[[bool], str]
    n_classes: int = 50
    n: int = 100
    m: int = 100


BENCHMARKS = [
    Benchmark("standard classes", None, get_standard_classes_template),
    Benchmark("dataclasses", None, get_dataclasses_template),
    Benchmark("pydantic", "pydantic", get_pydantic_basemodel_template),
    Benchmark("pydantic.dataclasses", "pydantic", get_pydantic_dataclasses_template),
    Benchmark("dataclassy", "dataclassy", get_dataclassy_template),
    Benchmark("attrs", "attrs", get_attrs_template),
    Benchmark("pyserde", "pyserde", get_pyserde_template),
    Benchmark("mashumaro", "mashumaro", get_mashumaro_template),
    Benchmark("msgspec", "msgspec", get_msgspec_template),
    Benchmark("jsonproto", "whatamithinking.jsonproto", get_jsonproto_template),
]


def benchpress(name, template, n_classes, n, m):
    source = textwrap.dedent("\n".join(template.format(n=i) for i in range(n_classes)))
    code_obj = compile(source, "__main__", "exec")

    define_time = init_time = equality_time = order_time = repr_time = hash_time = (
        getattr_time
    ) = setattr_time = None

    # Benchmark defining new types
    start = perf_counter()
    for _ in range(n):
        ns = {}
        try:
            exec(code_obj, ns)
        except NotImplementedError:
            return (
                name,
                define_time,
                init_time,
                equality_time,
                order_time,
                repr_time,
                hash_time,
                getattr_time,
                setattr_time,
            )
    end = perf_counter()
    define_time = ((end - start) / (n * n_classes)) * 1e6

    C = ns["C0"]

    # Benchmark creating new instances
    start = perf_counter()
    for _ in range(n):
        [C(a=i, b=i, c=i, d=i, e=i) for i in range(m)]
    end = perf_counter()
    init_time = ((end - start) / (n * m)) * 1e6

    # Benchmark equality
    val = m - 1
    needle = C(a=val, b=val, c=val, d=val, e=val)
    haystack = [C(a=i, b=i, c=i, d=i, e=i) for i in range(m)]
    start = perf_counter()
    for _ in range(n):
        haystack.index(needle)
    end = perf_counter()
    equality_time = ((end - start) / (n * m)) * 1e6

    # Benchmark order
    try:
        needle < needle
    except TypeError:
        order_time = None
    else:
        start = perf_counter()
        for _ in range(n):
            for obj in haystack:
                if obj >= needle:
                    break
        end = perf_counter()
        order_time = ((end - start) / (n * m)) * 1e6

    # Benchmark repr
    start = perf_counter()
    inst = C(a=1, b=2, c=3, d=4, e=5)
    for _ in range(n * m):
        repr(inst)
    end = perf_counter()
    repr_time = ((end - start) / (n * m)) * 1e6

    # Benchmark hash
    inst = C(a=1, b=2, c=3, d=4, e=5)
    try:
        hash(inst)
    except TypeError:
        hash_time = None
    else:
        start = perf_counter()
        for _ in range(n * m):
            hash(inst)
        end = perf_counter()
        hash_time = ((end - start) / (n * m)) * 1e6

    # Benchmark getattr
    start = perf_counter()
    inst = C(a=1, b=2, c=3, d=4, e=5)
    for _ in range(n * m):
        inst.a
        inst.b
        inst.c
        inst.d
        inst.e
    end = perf_counter()
    getattr_time = ((end - start) / (n * m)) * 1e6

    # Benchmark setattr
    start = perf_counter()
    inst = C(a=1, b=2, c=3, d=4, e=5)
    try:
        for _ in range(n * m):
            inst.a = 10
            inst.b = 10
            inst.c = 10
            inst.d = 10
            inst.e = 10
    except:
        setattr_time = None
    else:
        end = perf_counter()
        setattr_time = ((end - start) / (n * m)) * 1e6

    return (
        name,
        define_time,
        init_time,
        equality_time,
        order_time,
        repr_time,
        hash_time,
        getattr_time,
        setattr_time,
    )


def format_table(results, frozen: bool, slots: bool):
    columns = (
        "",
        "import (μs)",
        "create (μs)",
        "equal (μs)",
        "order (μs)",
        "repr (us)",
        "hash (us)",
        "getattr (us)",
        "setattr (us)",
    )

    def f(n):
        return "N/A" if n is None else f"{n:.2f}"

    rows = []
    for name, *times in results:
        rows.append((f"**{name}**", *(f(t) for t in times)))

    title = f"\n{'Frozen' if frozen else 'Mutable'} {'Slotted' if slots else 'Unslotted'} Basic Model Operations"
    widths = tuple(max(max(map(len, x)), len(c)) for x, c in zip(zip(*rows), columns))
    row_template = ("|" + (" %%-%ds |" * len(columns))) % widths
    header = row_template % tuple(columns)
    bar_underline = "+%s+" % "+".join("=" * (w + 2) for w in widths)
    bar = "+%s+" % "+".join("-" * (w + 2) for w in widths)
    parts = [title, bar, header, bar_underline]
    for r in rows:
        parts.append(row_template % r)
        parts.append(bar)
    return "\n".join(parts)


def main():
    print("\nLibraries:")
    seen = set()
    for benchmark in BENCHMARKS:
        if benchmark.library is not None and not benchmark.library in seen:
            seen.add(benchmark.library)
            version = importlib.metadata.version(benchmark.library)
            print(f"- {benchmark.library}: {version}")

    # check all libraries installed
    missing = []
    for benchmark in BENCHMARKS:
        if benchmark.library is not None:
            try:
                version = importlib.metadata.version(benchmark.library)
            except importlib.metadata.PackageNotFoundError:
                missing.append(benchmark.library)
    if missing:
        raise Exception(
            f"Cannot run benchmark until packages installed: {' '.join(missing)}"
        )

    for frozen, slots in [(False, False), (True, False), (False, True)]:
        results = []
        for benchmark in BENCHMARKS:
            results.append(
                benchpress(
                    name=benchmark.name,
                    template=benchmark.get_template(frozen, slots),
                    n_classes=benchmark.n_classes,
                    n=benchmark.n,
                    m=benchmark.m,
                )
            )
        print(format_table(results=results, frozen=frozen, slots=slots))


if __name__ == "__main__":
    main()
