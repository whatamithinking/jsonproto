import json
import timeit
from typing import List, Optional, Dict, Any
import sys
import os

# --- Constants for Conversion ---
BYTES_TO_GB = 1024**3
MICROSECONDS_PER_SECOND = 1_000_000

# --- Helper to convert bytes to GB ---
def bytes_to_gb(bytes_value):
    return round(bytes_value / BYTES_TO_GB, 2)

# --- Benchmarking Configuration ---
NUMBER_OF_EXECUTIONS = 10000 # Number of times to run the code snippet in each trial
REPEAT_TIMES = 5             # Number of times to repeat the entire benchmark (best result taken)

# --- Input Data (Common to all benchmarks) ---
VALID_DATA_DICT = {
    "id": 123,
    "name": "Alice Smith",
    "email": "alice@example.com",
    "active": True,
    "tags": ["admin", "developer"],
    "address": {
        "street": "123 Main St",
        "city": "Anytown",
        "zip": "12345"
    }
}
VALID_JSON_STRING = json.dumps(VALID_DATA_DICT)

INVALID_DATA_DICT = {
    "id": "not_an_int",  # Wrong type
    "email": "bob@example.com",
    # 'name' is missing (required field)
    "active": False,
    "address": {
        "street": "456 Oak Ave",
        "city": "Otherville",
        "zip": 98765 # Wrong type (int instead of str)
    }
}
INVALID_JSON_STRING = json.dumps(INVALID_DATA_DICT)

# --- MODEL GENERATION FUNCTIONS ---
# Each function returns a string of the Python code for defining the models
# for a specific library, with correct leading indentation.

def _generate_jsonproto_models_code():
    return """
    from typing import Annotated
    import whatamithinking.jsonproto as jp
    

    @jp.struct
    class JsonProtoAddress:
        street: str
        city: str
        zip: str

    
    @jp.struct
    class JsonProtoUser:
        id: int
        name: str
        email: str
        active: bool = True
        tags: Annotated[list[str], jp.DefaultFactory(list)]
        address: Optional[JsonProtoAddress] = None
    """


def _generate_attrs_models_code():
    return """
    import attr
    @attr.s(auto_attribs=True)
    class AttrsAddress:
        street: str
        city: str
        zip: str

    @attr.s(auto_attribs=True)
    class AttrsUser:
        id: int
        name: str
        email: str
        active: bool = True
        tags: list[str] = attr.ib(factory=list)
        address: Optional[AttrsAddress] = None
    """

def _generate_pydantic_models_code():
    return """
    from pydantic import BaseModel, Field
    class PydanticAddress(BaseModel):
        street: str
        city: str
        zip: str

    class PydanticUser(BaseModel):
        id: int
        name: str
        email: str
        active: bool = True
        tags: list[str] = Field(default_factory=list)
        address: Optional[PydanticAddress] = None
    """

def _generate_pyserde_models_code():
    return """
    import dataclasses
    from serde import serde

    @serde
    @dataclasses.dataclass
    class PyserdeAddress:
        street: str
        city: str
        zip: str

    @serde
    @dataclasses.dataclass
    class PyserdeUser:
        id: int
        name: str
        email: str
        active: bool = True
        tags: list[str] = dataclasses.field(default_factory=list)
        address: Optional[PyserdeAddress] = None
    """

def _generate_mashumaro_models_code():
    return """
    from dataclasses import dataclass
    from mashumaro import DataClassDictMixin
    from mashumaro.config import BaseConfig

    @dataclass
    class MashumaroAddress(DataClassDictMixin):
        street: str
        city: str
        zip: str
        class Config(BaseConfig):
            allow_extra_fields = False

    @dataclass
    class MashumaroUser(DataClassDictMixin):
        id: int
        name: str
        email: str
        active: bool = True
        tags: list[str] = dataclasses.field(default_factory=list)
        address: Optional[MashumaroAddress] = None
        class Config(BaseConfig):
            allow_extra_fields = False
    """

def _generate_msgspec_models_code():
    return """
    import msgspec.json
    from msgspec import Struct, field

    class MsgspecAddress(Struct):
        street: str
        city: str
        zip: str

    class MsgspecUser(Struct):
        id: int
        name: str
        email: str
        active: bool = True
        tags: list[str] = field(default_factory=list)
        address: Optional[MsgspecAddress] = None

    _msgspec_decoder = msgspec.json.Decoder(MsgspecUser)
    """

def _generate_apischema_models_code():
    return """
    from dataclasses import dataclass

    @dataclass
    class ApischemaAddress:
        street: str
        city: str
        zip: str

    @dataclass
    class ApischemaUser:
        id: int
        name: str
        email: str
        active: bool = True
        tags: list[str] = dataclasses.field(default_factory=list)
        address: Optional[ApischemaAddress] = None
    """

# --- SETUP CODE FOR timeit (Dynamically built) ---
setup_code_template = f"""
import orjson as json
from typing import List, Optional, Dict, Any
import dataclasses # Built-in, always available and required by many

# --- Conditional Imports for Libraries (for timeit environment) ---
# These imports are wrapped in try-except to allow the benchmark to run
# even if some optional libraries are not installed.
# We also import their specific ValidationError types/aliases here for consistent catching.

import whatamithinking.jsonproto as jp
jsonproto_codec = jp.Codec()

attr = None
try:
    import attr
except ImportError:
    pass

pydantic = None
PydanticValidationError = Exception # Default to a generic Exception if Pydantic isn't loaded
try:
    import pydantic
    from pydantic import ValidationError as PydanticValidationError
except ImportError:
    pass

serde = None
try:
    import serde
    from serde.json import from_json # Pyserde's main deserializer
except ImportError:
    pass

mashumaro = None
MashumaroMissingFields = Exception
MashumaroInvalidFieldValue = Exception
try:
    import mashumaro
    from mashumaro.exceptions import MissingFields as MashumaroMissingFields
    from mashumaro.exceptions import InvalidFieldValue as MashumaroInvalidFieldValue
except ImportError:
    pass

msgspec = None
MsgspecValidationError = Exception # Default to generic exception
try:
    import msgspec
    import msgspec.json
    from msgspec import ValidationError as MsgspecValidationError # Msgspec's specific ValidationError
except ImportError:
    pass

apischema = None
ApischemaValidationError = Exception # Default to generic exception
try:
    import apischema
    from apischema import deserialize # Apischema's main deserializer
    from apischema import ValidationError as ApischemaValidationError # Apischema's specific ValidationError
except ImportError:
    pass


# --- Include Model Definitions if Library is Available ---
# Models are only defined if their corresponding library was successfully imported
if jp:
    {_generate_jsonproto_models_code()}
if attr:
    {_generate_attrs_models_code()}
if pydantic:
    {_generate_pydantic_models_code()}
if serde:
    {_generate_pyserde_models_code()}
if mashumaro:
    {_generate_mashumaro_models_code()}
if msgspec:
    {_generate_msgspec_models_code()}
if apischema:
    {_generate_apischema_models_code()}


VALID_JSON_STRING = {json.dumps(VALID_JSON_STRING)}
INVALID_JSON_STRING = {json.dumps(INVALID_JSON_STRING)}
"""

# --- Benchmarking Functions Dictionary ---
# Each entry specifies the library name, and the code snippets for valid and invalid inputs.
# The code snippets perform JSON decoding + model validation/conversion.
# Exceptions are caught to ensure consistent benchmark behavior.
# Note on data conversion: All libraries will convert from JSON string input.
# Some prefer dict (attrs, dataclasses, mashumaro, apischema), some prefer raw JSON string (pydantic, msgspec).
# json.loads() is included in the benchmark snippet for libraries that require a dict.

benchmarks = {
    "Pydantic (BaseModel)": {
        "valid_code": """
if pydantic: # Guard execution if library not imported
    user = PydanticUser.model_validate_json(VALID_JSON_STRING)
""",
        "invalid_code": """
if pydantic:
    try:
        user = PydanticUser.model_validate_json(INVALID_JSON_STRING)
    except PydanticValidationError:
        pass
""",
        "exception_type": "pydantic.ValidationError",
        "requires_library_variable": "pydantic" # Reference to the variable in setup_code_template
    },
    "JsonProto": {
        "valid_code": """
if jp:
    user = jsonproto_codec.execute(
        VALID_JSON_STRING,
        source="jsonstr",
        target="struct",
        convert=True,
        validate=True,
        type_hint=JsonProtoUser,
    )
""",
        "invalid_code": """
if jp:
    try:
        user = jsonproto_codec.execute(
            INVALID_JSON_STRING,
            source="jsonstr",
            target="struct",
            convert=True,
            validate=True,
            type_hint=JsonProtoUser,
        )
    except jp.ValidationError:
        pass
""",
        "exception_type": "jp.ValidationError",
        "requires_library_variable": "jp"
    },
    "Attrs": {
        "valid_code": """
if attr:
    data = json.loads(VALID_JSON_STRING)
    user = AttrsUser(**data)
""",
        "invalid_code": """
if attr:
    try:
        data = json.loads(INVALID_JSON_STRING)
        user = AttrsUser(**data)
    except Exception:
        pass
""",
        "exception_type": "TypeError / ValueError",
        "requires_library_variable": "attr"
    },
    "Pyserde": { # Benchmarks deserialization which includes validation for dataclass structure
        "valid_code": """
if serde:
    user = from_json(PyserdeUser, VALID_JSON_STRING)
""",
        "invalid_code": """
if serde:
    try:
        user = from_json(PyserdeUser, INVALID_JSON_STRING)
    except Exception:
        pass
""",
        "exception_type": "serde.SerdeError / TypeError",
        "requires_library_variable": "serde"
    },
    "Mashumaro": {
        "valid_code": """
if mashumaro:
    data = json.loads(VALID_JSON_STRING)
    user = MashumaroUser.from_dict(data)
""",
        "invalid_code": """
if mashumaro:
    try:
        data = json.loads(INVALID_JSON_STRING)
        user = MashumaroUser.from_dict(data)
    except (MashumaroMissingFields, MashumaroInvalidFieldValue, TypeError, ValueError):
        pass
""",
        "exception_type": "MissingFields / InvalidFieldValue / TypeError / ValueError",
        "requires_library_variable": "mashumaro"
    },
    "Msgspec": {
        "valid_code": """
if msgspec:
    user = _msgspec_decoder.decode(VALID_JSON_STRING.encode('utf-8'))
""",
        "invalid_code": """
if msgspec:
    try:
        user = _msgspec_decoder.decode(INVALID_JSON_STRING.encode('utf-8'))
    except MsgspecValidationError:
        pass
""",
        "exception_type": "msgspec.ValidationError",
        "requires_library_variable": "msgspec"
    },
    "Apischema": {
        "valid_code": """
if apischema:
    data = json.loads(VALID_JSON_STRING)
    user = deserialize(ApischemaUser, data, coerce=True, no_copy=False)
""",
        "invalid_code": """
if apischema:
    try:
        data = json.loads(INVALID_JSON_STRING)
        user = deserialize(ApischemaUser, data, coerce=True, no_copy=False)
    except ApischemaValidationError:
        pass
""",
        "exception_type": "apischema.ValidationError",
        "requires_library_variable": "apischema"
    },
}

# --- System Information (for context) ---
import psutil
import platform

def get_system_info():
    info = {}
    info['Python Version'] = sys.version.splitlines()[0]
    info['OS'] = platform.system()
    info['OS Release'] = platform.release()
    info['Machine'] = platform.machine()
    info['Processor'] = platform.processor()

    # Memory info
    try:
        mem = psutil.virtual_memory()
        info['Total RAM'] = f"{bytes_to_gb(mem.total)} GB"
    except Exception:
        info['Total RAM'] = "N/A (psutil issue)"


    return info


# --- Main Benchmarking Logic ---
if __name__ == "__main__":
    system_info = get_system_info()
    print("--- System Information ---")
    for key, value in system_info.items():
        print(f"{key}: {value}")
    print("\n")

    print("--- Benchmarking JSON String Validation ---")
    print(f"Number of executions per trial: {NUMBER_OF_EXECUTIONS}")
    print(f"Number of repeated trials: {REPEAT_TIMES} (best time taken)\n")

    results = {}

    for library_name, codes in benchmarks.items():
        print(f"Benchmarking {library_name}...")

        # Benchmark VALID input
        
        try:
            valid_times = timeit.repeat(
                codes["valid_code"],
                setup=setup_code_template,
                number=NUMBER_OF_EXECUTIONS,
                repeat=REPEAT_TIMES
            )
            min_valid_time = min(valid_times)
            avg_valid_us = (min_valid_time / NUMBER_OF_EXECUTIONS) * MICROSECONDS_PER_SECOND
            results[library_name] = {
                "valid_success_avg_us": avg_valid_us
            }
            print(f"  Valid Data Success:     {avg_valid_us:.2f} µs/op")
        except Exception as e:
            # Capture the actual exception type and message for better debugging
            error_type = type(e).__name__
            error_message = str(e)
            results[library_name] = {"valid_success_avg_us": "ERROR"}
            print(f"  Valid Data Success:     ERROR ({error_type}: {error_message})")
            # Provide more specific guidance if it's a known library loading issue
            if "not defined" in error_message or "cannot import" in error_message or "has no attribute" in error_message:
                lib_var = codes.get('requires_library_variable', 'N/A')
                if lib_var != 'N/A' and lib_var != 'dataclasses': # dataclasses is built-in
                     print(f"    Likely cause: Library '{lib_var}' (e.g., '{lib_var}') is not installed or its models could not be defined in the benchmark environment.")
                     print(f"    Please ensure you run 'pip install {lib_var}' if you want to benchmark it.")
                else:
                    print("    Cause: Model definition or import issue within the benchmark's setup string.")


        # # Benchmark INVALID input
        # try:
        #     invalid_times = timeit.repeat(
        #         codes["invalid_code"],
        #         setup=setup_code_template,
        #         number=NUMBER_OF_EXECUTIONS,
        #         repeat=REPEAT_TIMES
        #     )
        #     min_invalid_time = min(invalid_times)
        #     avg_invalid_us = (min_invalid_time / NUMBER_OF_EXECUTIONS) * MICROSECONDS_PER_SECOND
        #     results[library_name]["invalid_failure_avg_us"] = avg_invalid_us
        #     print(f"  Invalid Data Failure ({codes['exception_type']}): {avg_invalid_us:.2f} µs/op")
        # except Exception as e:
        #     error_type = type(e).__name__
        #     error_message = str(e)
        #     results[library_name]["invalid_failure_avg_us"] = "ERROR"
        #     print(f"  Invalid Data Failure:   ERROR ({error_type}: {error_message})")
        #     if "not defined" in error_message or "cannot import" in error_message or "has no attribute" in error_message:
        #         lib_var = codes.get('requires_library_variable', 'N/A')
        #         if lib_var != 'N/A' and lib_var != 'dataclasses':
        #             print(f"    Likely cause: Library '{lib_var}' (e.g., '{lib_var}') is not installed or its models could not be defined in the benchmark environment.")
        #             print(f"    Please ensure you run 'pip install {lib_var}' if you want to benchmark it.")
        #         else:
        #             print("    Cause: Model definition or import issue within the benchmark's setup string.")
        # print("-" * 30)

    # print("\n--- Benchmark Summary (Average time per operation in microseconds) ---")
    # print(f"{'Library':<25} | {'Valid Success':<15} | {'Invalid Failure':<17}")
    # print("-" * 60)
    # for library_name, data in results.items():
    #     valid_str = f"{data['valid_success_avg_us']:.2f}" if isinstance(data['valid_success_avg_us'], float) else str(data['valid_success_avg_us'])
        # invalid_str = f"{data['invalid_failure_avg_us']:.2f}" if isinstance(data['invalid_failure_avg_us'], float) else str(data['invalid_failure_avg_us'])
        # print(f"{library_name:<25} | {valid_str:<15} | {invalid_str:<17}")
