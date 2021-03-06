# genlib — Copyright (c) 2019, Alex J. Champandard. Code licensed under the GNU AGPLv3.

import pytest
import asyncio
import pathlib
import tempfile

from genlib.core.skills import BaseSkill
from genlib.runtime.registry import LocalRegistry, FileSystemWatcher


# All the tests in this file can be treated as asynchronous.
pytestmark = pytest.mark.asyncio


FAKE_SKILL_CODE = """
class MySkill(s.Skill):
    outputs = [s.Output('o', spec='str')]
    async def compute(self): pass
"""


class TestFileSystemWatcher:
    async def test_start_stop(self):
        watcher = FileSystemWatcher(callback=None)
        watcher.monitor("genlib")
        await asyncio.sleep(1.0)
        watcher.shutdown()

    async def test_modified(self):
        result = []

        def callback(root, path):
            result.append((root, path))

        watcher = FileSystemWatcher(callback=callback)
        watcher.monitor("tests")
        await asyncio.sleep(1.0)

        pathlib.Path("tests/__init__.py").touch()
        await asyncio.sleep(1.0)
        assert len(result) == 1
        assert result[0] == ("tests", "tests/__init__.py")

        watcher.shutdown()

    async def test_exception(self, caplog):
        def throw(*_):
            raise NotImplementedError

        watcher = FileSystemWatcher(callback=throw)
        watcher.monitor("tests")
        await asyncio.sleep(1.0)

        pathlib.Path("tests/__init__.py").touch()
        await asyncio.sleep(1.0)

        assert 'Error while reloading "tests/__init__.py".' in caplog.text
        assert watcher.thread.is_alive()
        watcher.shutdown()


@pytest.fixture
def local_registry():
    registry = LocalRegistry()
    yield registry
    registry.watcher.shutdown()


@pytest.fixture
def temporary_folder():
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


class TestLocalRegistry:
    async def test_instance_create_destroy(self, local_registry):
        pass

    async def test_load_folder_without_skills(self, local_registry, temporary_folder):
        open(f"{temporary_folder}/nothing.py", "w").write("A=123")
        local_registry.load_folder(temporary_folder)
        assert len(local_registry.modules) == 1
        assert "nothing.py" in list(local_registry.modules.keys())[0]
        assert getattr(list(local_registry.modules.values())[0], "A") == 123

    async def test_load_folder_with_one_skill(self, local_registry, temporary_folder):
        open(f"{temporary_folder}/myskill.py", "w").write(
            "import genlib.core.skills as s\n" + FAKE_SKILL_CODE
        )
        local_registry.load_folder(temporary_folder)
        assert len(local_registry.modules) == 1
        assert "myskill.py" in list(local_registry.modules.keys())[0]
        assert len(local_registry.list_skills_schema()) == 1
        assert local_registry.find_skill_schema("myskill.py:MySkill") is not None

    async def test_load_folder_construct_skill(self, local_registry, temporary_folder):
        open(f"{temporary_folder}/myskill.py", "w").write(
            "import genlib.core.skills as s\n" + FAKE_SKILL_CODE
        )
        local_registry.load_folder(temporary_folder)

        schema = local_registry.find_skill_schema("myskill.py:MySkill")
        skill = local_registry.construct(schema)
        assert isinstance(skill, BaseSkill)
        assert skill.__class__.__name__ == "MySkill"

    async def test_load_folder_relative_import(self, local_registry, temporary_folder):
        open(f"{temporary_folder}/helper.py", "w").write("A=456")
        open(f"{temporary_folder}/test.py", "w").write("from .helper import A")
        local_registry.load_folder(temporary_folder)
        assert len(local_registry.modules) == 2
        for module in local_registry.modules.values():
            assert getattr(module, "A") == 456

    async def test_load_folder_reloads_changes(self, local_registry, temporary_folder):
        open(f"{temporary_folder}/myskill.py", "w").write("#\n")
        local_registry.load_folder(temporary_folder, watch=True)
        assert len(local_registry.modules) == 1
        assert len(local_registry.list_skills_schema()) == 0
        await asyncio.sleep(1.0)

        with open(f"{temporary_folder}/myskill.py", "w+") as f:
            f.write("import genlib.core.skills as s\n" + FAKE_SKILL_CODE)
        await asyncio.sleep(1.0)
        assert len(local_registry.list_skills_schema()) == 1
