# WhatAmIThinking-JsonProto

Declarative json modeler, validator, encoder, and decoder

## Table of Contents

- [WhatAmIThinking-JsonProto](#whatamithinking-jsonproto)
  - [Table of Contents](#table-of-contents)
  - [Reference](#reference)
    - [Reference - Required, Nullable, and Non-Nullable Fields](#reference---required-nullable-and-non-nullable-fields)
    - [Reference - Format Inference](#reference---format-inference)
      - [Reference - Format Inference - Type Hint](#reference---format-inference---type-hint)
      - [Reference - Format Inference - Source](#reference---format-inference---source)
      - [Reference - Format Inference - Target](#reference---format-inference---target)
  - [Benchmarks](#benchmarks)
    - [Benchmarks - Config](#benchmarks---config)
    - [Benchmarks - Basic Model Operations](#benchmarks---basic-model-operations)
    - [Benchmarks - Validation and Conversion](#benchmarks---validation-and-conversion)

## Reference

### Reference - Required, Nullable, and Non-Nullable Fields

There are a few subtly different scenarios which can come up when working with structs/models, especially when handling things like updates. An update structure usually consists of a lot of optional fields. 

```python
from typing import Annotated
from whatamithinking.jsonproto import struct, Required, Pattern


T_Username = Annotated[str, Pattern(r"[a-z0-9-\._']{,20}")]


@struct
class UpdateUserModel:
    a: T_Username | None  # required, nullable
    b: T_Username  # required, non-nullable
    c: T_Username | None = None  # optional, nullable
    d: Annotated[T_Username, Required(False)]  # optional, non-nullable


print(UpdateUserModel(a=None, b="myuser001"))  # UpdateUserModel(a=None,b="myuser001",c=None,d=<Empty>)
```

Some fields may support being set to None, which might be interpreted as setting to NULL in a database or deleting the data entirely, and in these cases we can usually setup the field as `field_name: FieldType | None = None` and having it default to `None` is fine because that is a valid possible value. 

Other fields may not support being set to None and must always be set to a value of the appropriate type and meeting validation requirements or else not set at all. The code below of updating a username for an account is a good example of such a situation, where:
- We cannot allow the user to set username to None/NULL, it must always be a valid username string value
- There is no obvious choice for a default value for the username, which is what we normally do to make a field optional/not-required.  

To cover this scenario, the `Required` constraint was required, which can be added in an annotation and set to `Required(False)` to make the field optional but not nullable and without specifying a default. The struct object will represent the absence of this value as the `Empty` class if not provided. The `Empty` value only shows up when using a struct object; otherwise, fields with this value are stripped out by the `Codec`.

### Reference - Format Inference

TLDR: you can skip providing `source` unless `value` is a `dict` and you can skip providing `target` unless you are trying to convert to something other than the `source` format.

In order for anything to work, we need to know the source format of the data we have and the target format of the data we want to go to. In some cases these may be the same, such as when we only want to validate data against the `type_hint` but otherwise skip any kind of conversion. `Codec.execute` has a param called `source` and another called `target` referring to the format before and after. The possible values are:

- `struct`: a struct/model instance using python native types
- `unstruct`: a dict/list/etc. of python native types. basically just unwrapping the struct/model from the data
- `json`: json-encoded form of the data, using only json-supported types (str, int, list, dict, etc.)
- `jsonstr`: string json-serialized data
- `jsonbytes`: bytes json-serialized data

To cut down on typing, a minor amount of format inference is supported, allowing the codec to guess the type_hint, source format, and target format under certain circumstances.

#### Reference - Format Inference - Type Hint

| Condition           | Inference          |
| ------------------- | ------------------ |
| `value` is `struct` | `type(value)`      |
| Fallback            | raise `ValueError` |

#### Reference - Format Inference - Source

A notable exception to `source` format inference at the moment is when the value given is a `dict`. A `dict` could be either `json` or `unstruct` format, so the caller needs to explicitly provide the format.

| Condition                                      | Inference          |
| ---------------------------------------------- | ------------------ |
| `value` is `struct`                            | `struct`           |
| `type_hint` is `struct` and `value` is `str`   | `jsonstr`          |
| `type_hint` is `struct` and `value` is `bytes` | `jsonbytes`        |
| Fallback                                       | raise `ValueError` |

#### Reference - Format Inference - Target

There is no way to infer the target when conversion/coercion is desired. When doing validation we probably just want source=target since we are not doing anything with the target format. 

| Condition | Inference |
| --------- | --------- |
| Fallback  | `source`  |

## Benchmarks

Please take all benchmarks with a grain of salt. Results depend heavily on what you are doing. Different libraries may be optimized for certain situations, such as simplistic benchmarking approachs (including this library). It is always best to do your own benchmarking for the kinds of data models and validation you expect to encounter in your project. That said, I usually like seeing benchmarks on infrastructure stuff which I will use everywhere as a quick gut check. If you have suggestions on how to improve these benchmarks, please open an issue.

Also worth mentioning I do what I can to use the best available settings for each library which I found in the docs. I am no doubt a bit biased towards making my own library perform well, but I try to avoid doing any kind of "bending over backwards" to make things optimal unless the docs suggest it. Again, everyone is biased and you should do your own benchmarking.

### Benchmarks - Config

-   Python: 3.13.3 (tags/v3.13.3:6280bb5, Apr 8 2025, 14:47:33) [MSC v.1943 64 bit (AMD64)]
-   OS: Windows 10.0.19045
-   Memory: 32 GB
-   CPU: Intel64 Family 6 Model 94 Stepping 3, GenuineIntel
-   Frequency: 2.81 GHz
-   Physical Cores: 4
-   Logical Cores: 8

### Benchmarks - Basic Model Operations

This covers just working with the models themselves (classes decorated with `@jsonproto`) directly and does not cover time the `Codec` would spend performing various operations, including constructing. One of the areas for improvement noted when auditing modeling libraries was that the time just to define the model class was quite large and significantly slowed down the debugger in an IDE when a large number of models (a few hundred in one project) were created, making it cumbersome to debug the code at all. The time spent building the model is a central focus of this library so it can scale well even with large numbers of models.

```text
Libraries:
- pydantic: 2.11.7
- dataclassy: 1.0.1
- attrs: 25.3.0    
- pyserde: 0.24.0  
- mashumaro: 3.16
- msgspec: 0.19.0
- whatamithinking.jsonproto: 1.0.3

Mutable Unslotted Basic Model Operations
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
|                          | import (μs) | create (μs) | equal (μs) | order (μs) | repr (us) | hash (us) | getattr (us) | setattr (us) |
+==========================+=============+=============+============+============+===========+===========+==============+==============+
| **standard classes**     | 9.70        | 0.57        | 0.12       | 0.29       | 0.90      | 0.32      | 0.10         | 0.09         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **dataclasses**          | 1051.32     | 0.68        | 0.12       | 0.26       | 1.28      | 0.23      | 0.08         | 0.10         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **pydantic**             | 398.38      | 3.78        | 3.40       | N/A        | 9.40      | N/A       | 0.27         | 4.00         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **pydantic.dataclasses** | 4339.92     | 1.88        | 0.13       | 0.39       | 1.01      | 0.32      | 0.10         | 0.15         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **dataclassy**           | 335.11      | 0.55        | 0.44       | 0.55       | 6.53      | 0.22      | 0.08         | 0.09         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **attrs**                | 831.75      | 0.63        | 0.12       | 4.99       | 1.39      | 0.33      | 0.09         | 0.11         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **pyserde**              | 5897.08     | 5.04        | 0.32       | 0.90       | 2.25      | 0.70      | 0.22         | 0.25         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **mashumaro**            | 4239.44     | 0.97        | 0.45       | 0.85       | 1.45      | 0.25      | 0.09         | 0.08         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **msgspec**              | 34.32       | 0.39        | 0.08       | 0.21       | 1.06      | N/A       | 0.10         | 0.25         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
| **jsonproto**            | 41.71       | 1.64        | 0.42       | 0.75       | 1.34      | 0.57      | 0.20         | 0.11         |
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+

Frozen Unslotted Basic Model Operations
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
|                          | import (μs) | create (μs) | equal (μs) | order (μs) | repr (us) | hash (us) | getattr (us) | setattr (us) |
+==========================+=============+=============+============+============+===========+===========+==============+==============+   
| **standard classes**     | 22.84       | 2.78        | 0.38       | 0.43       | 1.23      | 0.24      | 0.08         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **dataclasses**          | 1293.65     | 1.46        | 0.26       | 0.43       | 1.24      | 0.42      | 0.19         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **pydantic**             | 309.05      | 1.81        | 2.21       | N/A        | 4.33      | 0.46      | 0.08         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **pydantic.dataclasses** | 6176.76     | 1.84        | 0.12       | 0.27       | 1.04      | 0.24      | 0.08         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **dataclassy**           | 344.79      | 2.48        | 0.99       | 1.31       | 9.94      | 0.39      | 0.08         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **attrs**                | 925.34      | 0.85        | 0.11       | 2.99       | 1.09      | 0.29      | 0.07         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **pyserde**              | 6779.41     | 2.79        | 0.17       | 0.28       | 1.07      | 0.25      | 0.09         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **mashumaro**            | 4910.14     | 1.61        | 0.11       | 0.40       | 1.05      | 0.24      | 0.09         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **msgspec**              | 21.65       | 0.12        | 0.02       | 0.07       | 0.85      | 0.09      | 0.08         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **jsonproto**            | 24.05       | 1.18        | 0.12       | 0.47       | 0.20      | 0.26      | 0.16         | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   

Mutable Slotted Basic Model Operations
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
|                          | import (μs) | create (μs) | equal (μs) | order (μs) | repr (us) | hash (us) | getattr (us) | setattr (us) |   
+==========================+=============+=============+============+============+===========+===========+==============+==============+   
| **standard classes**     | 13.97       | 0.60        | 0.49       | 0.97       | 0.81      | 0.31      | 0.08         | 0.08         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **dataclasses**          | 1328.20     | 0.48        | 0.11       | 0.34       | 1.07      | 0.25      | 0.08         | 0.09         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **pydantic**             | N/A         | N/A         | N/A        | N/A        | N/A       | N/A       | N/A          | N/A          |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **pydantic.dataclasses** | 2609.85     | 2.05        | 0.13       | 0.37       | 1.06      | 0.24      | 0.08         | 0.10         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **dataclassy**           | 355.72      | 1.48        | 1.40       | 1.36       | 19.29     | 0.60      | 0.45         | 0.24         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **attrs**                | 1241.92     | 1.05        | 0.29       | 4.59       | 2.83      | 0.27      | 0.08         | 0.08         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **pyserde**              | 5859.96     | 5.38        | 0.43       | 0.91       | 3.41      | 0.88      | 0.33         | 0.38         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **mashumaro**            | 6719.33     | 1.27        | 0.45       | 0.72       | 3.27      | 0.39      | 0.14         | 0.12         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **msgspec**              | 31.17       | 0.27        | 0.02       | 0.05       | 0.63      | N/A       | 0.08         | 0.21         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+   
| **jsonproto**            | 61.26       | 0.55        | 0.11       | 0.48       | 0.72      | 0.26      | 0.08         | 0.10         |   
+--------------------------+-------------+-------------+------------+------------+-----------+-----------+--------------+--------------+
```

### Benchmarks - Validation and Conversion

```text
Benchmarking Pydantic (BaseModel)...
  Valid Data Success:     4.95 µs/op
Benchmarking JsonProto...
  Valid Data Success:     35.40 µs/op
Benchmarking Attrs...
  Valid Data Success:     2.62 µs/op
Benchmarking Pyserde...
  Valid Data Success:     11.70 µs/op
Benchmarking Mashumaro...
  Valid Data Success:     4.43 µs/op
Benchmarking Msgspec...
  Valid Data Success:     0.85 µs/op
Benchmarking Apischema...
  Valid Data Success:     14.68 µs/op
```
