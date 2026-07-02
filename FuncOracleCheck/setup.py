"""
@Project : AutoAgentService
@File    : setup.py
@Author  : c30064476
@Date    : 2025/6/30 11:22

编译 cython
"""
import os
import shutil

from setuptools import setup, Extension
from Cython.Build import cythonize
from pathlib import Path

# 配置参数
SOURCE_DIR = Path("")  # 源代码目录
COMPILED_DIR = Path("compiled")  # 编译输出目录
# 排除的文件：不需要编译
EXCLUDE_FILES = {"config.py", "main_endside.py", "server_api.py", "setup.py", "func_check.py", "mlops_mllms.py", "ui_tars.py", "ui_tars_output_parser.py", "ui_tars_prompts.py",
                 "function_oracle_prompts.py", "main.py", "ocr_util.py", "decorators.py", "logging_config.py", "ocr.py", "api_client.py"}
# EXCLUDE_FILES = {"setup.py"}
# IGNORE_FILE = {"setup.py"}
# 打包后不需要的文件
IGNORE_FILE = {"setup.py", "mlops_mllms.py", "ui_tars.py", "ui_tars_output_parser.py", "ui_tars_prompts.py",
                 "function_oracle_prompts.py", "main.py", "service.sh", "README.md", "build.sh"}


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
            else:
                if c_so_file.suffix in {".c", ".so", ".pyd"}:
                    os.remove(c_so_file)

    __delete_c_so(SOURCE_DIR)


def create_extensions():
    """自动创建Cython扩展列表"""
    extensions = []
    exclude = {"file": [], "dir": []}

    def __create_extensions(path: Path):
        for py_file in path.iterdir():
            # 计算相对路径
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
                # 生成模块名 (如 'src.module1')
                module_name = str(rel_path.with_suffix("")).replace(os.sep, ".")

                # 生成输出路径 (如 'compiled/src/module1.c')
                c_file = COMPILED_DIR / rel_path.with_suffix(".c")

                # 确保输出目录存在
                c_file.parent.mkdir(parents=True, exist_ok=True)

                extensions.append(Extension(
                    name=module_name,
                    sources=[str(py_file)],
                    extra_compile_args=["-O3", "-march=native"],  # 优化选项
                    define_macros=[("CYTHON_TRACE", "0")]  # 禁用调试
                ))

    __create_extensions(Path(SOURCE_DIR))
    return extensions, exclude


delete_c_so_pycache()
_extensions, _exclude = create_extensions()

setup(
    name="SceneClsDevice",
    ext_modules=cythonize(
        _extensions,
        compiler_directives={
            "language_level": "3",  # 指定 Python 3
            "boundscheck": False,  # 提升性能
            "wraparound": False,  # 提升性能
            "initializedcheck": False  # 提升性能
        }
    ),
    zip_safe=False,  # 避免打包为 zip
)

# 删除编译产生的临时文件
delete_c_so_pycache(is_delete_compiled=False)

# 复制相关文件到编译后的文件夹
for file in _exclude["file"]:
    if file.name in IGNORE_FILE or file.suffix in {".pyc"}:
        continue
    os.makedirs((COMPILED_DIR / file).parent, exist_ok=True)
    shutil.copyfile(SOURCE_DIR / file, COMPILED_DIR / file)

for file in _exclude["dir"]:
    if file.name in IGNORE_FILE:
        continue
    shutil.copytree(SOURCE_DIR / file, COMPILED_DIR / file)
