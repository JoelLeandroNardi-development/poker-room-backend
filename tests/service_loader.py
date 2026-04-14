from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

SERVICE_DIRNAME = "services"
APP_DIRNAME = "app"
GATEWAY_SERVICE_DIR = "gateway-service"
PACKAGE_SUFFIX_APP = "_app"


def load_service_app_module(
    service_dir: str,
    module_name: str,
    *,
    package_name: str | None = None,
    reload_modules: bool = False,
):
    app_dir = REPO_ROOT / SERVICE_DIRNAME / service_dir / APP_DIRNAME

    if service_dir == GATEWAY_SERVICE_DIR:
        parent_dir = str(app_dir.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

    resolved_package = package_name or f"{service_dir.replace('-', '_')}{PACKAGE_SUFFIX_APP}"

    app_dir_str = str(app_dir)
    if app_dir_str not in sys.path:
        sys.path.insert(0, app_dir_str)

    if reload_modules:
        for name in list(sys.modules):
            if name == resolved_package or name.startswith(f"{resolved_package}."):
                sys.modules.pop(name, None)

    if resolved_package not in sys.modules:
        package = types.ModuleType(resolved_package)
        package.__path__ = [app_dir_str]
        sys.modules[resolved_package] = package

    module_parts = module_name.split("/")
    dotted_module_name = ".".join(module_parts)
    full_name = f"{resolved_package}.{dotted_module_name}"

    if full_name in sys.modules:
        return sys.modules[full_name]

    current_path = app_dir
    for i in range(1, len(module_parts)):
        pkg_name = ".".join([resolved_package] + module_parts[:i])
        current_path = current_path / module_parts[i - 1]
        if pkg_name not in sys.modules:
            pkg = types.ModuleType(pkg_name)
            pkg.__path__ = [str(current_path)]
            sys.modules[pkg_name] = pkg

    file_path = app_dir / Path(*module_parts).with_suffix(".py")
    spec = importlib.util.spec_from_file_location(full_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load module from {file_path}")

    module = importlib.util.module_from_spec(spec)

    if len(module_parts) > 1:
        module.__package__ = ".".join([resolved_package] + module_parts[:-1])
    else:
        module.__package__ = resolved_package

    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module
