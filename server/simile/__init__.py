import importlib
import importlib.util
import pkgutil
from collections.abc import Iterator
from types import ModuleType


def submodules(name: str, package: str = __name__) -> Iterator[ModuleType]:
    """Import and yield `<package>.<subpackage>.<name>` for every subpackage that defines it."""
    root = importlib.import_module(package)
    for info in sorted(pkgutil.iter_modules(root.__path__), key=lambda m: m.name):
        qualified = f"{package}.{info.name}.{name}"
        if info.ispkg and importlib.util.find_spec(qualified) is not None:
            yield importlib.import_module(qualified)
