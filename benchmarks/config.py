import sys
import platform
import math

import psutil


def print_config():
    print("\nConfig:")
    print(f"- Python: {sys.version}")
    print(f"- OS: {platform.system()} {platform.version()}")
    print(f"- Memory: {math.ceil(psutil.virtual_memory().total / 1024**3)} GB")
    print(f"- CPU: {platform.processor()}")
    print(f"- Frequency: {psutil.cpu_freq().max/1000:.2f} GHz")
    print(f"- Physical Cores: {psutil.cpu_count(logical=False)}")
    print(f"- Logical Cores: {psutil.cpu_count(logical=True)}")


if __name__ == "__main__":
    print_config()
