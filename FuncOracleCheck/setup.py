"""
Cython build script for FuncOracleCheck.
"""
import os
import shutil
from pathlib import Path

from Cython.Build import cythonize
from setuptools import Extension, setup

SOURCE_DIR = Path("")
COMPILED_DIR = Path("compiled")

EXCLUDE_FILES = {
    "config.py",
    "setup.py",
    "main.py",
    "api_client.py",

    "ui_tars.py",
    "ui_tars_output_parser.py",
    "ui_tars_prompts.py",
    "function_oracle_prompts.py",
    "ocr_util.py",
    "decorators.py",
    "logging_config.py",
    "ocr.py",
}
IGNORE_FILE = {
    "setup.py",

    "ui_tars.py",
    "ui_tars_output_parser.py",
    "ui_tars_prompts.py",
    "function_oracle_prompts.py",
    "main.py",
    "service.sh",
    "README.md",
    "build.sh",
}


def delete_c_so_pycache(is_delete_compiled=True):
    if is_delete_compiled:
        shutil.rmtree(COMPILED_DIR, ignore_errors=True)
    shutil.rmtree("build", ignore_errors=True)

    def __delete_c_so(path: Path):
        if path == COMPILED_DIR:
            return
        for c_so_file in path.iterdir():
            if c_so_file.is_dir():
                if c_so_file.name == "__pycache__":
                    shutil.rmtree(c_so_file)
                else:
                    __delete_c_so(c_so_file)
            elif c_so_file.suffix in {".c", ".so", ".pyd"}:
                os.remove(c_so_file)

    __delete_c_so(SOURCE_DIR)


def create_extensions():
    extensions = []
    exclude = {"file": [], "dir": []}

    def __create_extensions(path: Path):
        for py_file in path.iterdir():
            rel_path = py_file.relative_to(SOURCE_DIR)
            if py_file.is_dir():
                if py_file.name in EXCLUDE_FILES:
                    exclude["dir"].append(rel_path)
                    continue
                __create_extensions(py_file)
            else:
                if py_file.name in EXCLUDE_FILES or py_file.suffix != ".py" or py_file == SOURCE_DIR / "__init__.py":
                    exclude["file"].append(rel_path)
                    continue
                module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")
                c_file = COMPILED_DIR / rel_path.with_suffix(".c")
                c_file.parent.mkdir(parents=True, exist_ok=True)
                extensions.append(
                    Extension(
                        name=module_name,
                        sources=[str(py_file)],
                        extra_compile_args=["-O3", "-march=native"],
                        define_macros=[("CYTHON_TRACE", "0")],
                    )
                )

    __create_extensions(Path(SOURCE_DIR))
    return extensions, exclude


delete_c_so_pycache()
_extensions, _exclude = create_extensions()

setup(
    name="FuncOracleCheck",
    ext_modules=cythonize(
        _extensions,
        compiler_directives={
            "language_level": "3",
            "boundscheck": False,
            "wraparound": False,
            "initializedcheck": False,
        },
    ),
    zip_safe=False,
)

delete_c_so_pycache(is_delete_compiled=False)

for file in _exclude["file"]:
    if file.name in IGNORE_FILE or file.suffix in {".pyc"}:
        continue
    os.makedirs((COMPILED_DIR / file).parent, exist_ok=True)
    shutil.copyfile(SOURCE_DIR / file, COMPILED_DIR / file)

for file in _exclude["dir"]:
    if file.name in IGNORE_FILE:
        continue
    shutil.copytree(SOURCE_DIR / file, COMPILED_DIR / file)
