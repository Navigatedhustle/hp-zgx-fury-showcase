import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('model_directory',ROOT/'ops/model-directory.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_explicit_reuse_is_persistent_and_never_replaces_models(tmp_path):
    checkout=tmp_path/'checkout';checkout.mkdir()
    shared=tmp_path/'shared';shared.mkdir();(shared/'weight').write_bytes(b'fictional')
    assert m.configure(checkout,str(shared))==shared
    assert (checkout/'models').is_symlink()
    assert m.configure(checkout,str(shared))==shared
    other=tmp_path/'other';other.mkdir()
    with pytest.raises(ValueError,match='will not be replaced'):m.configure(checkout,str(other))
    assert (shared/'weight').read_bytes()==b'fictional'


def test_relative_missing_and_conflicting_paths_fail_closed(tmp_path):
    with pytest.raises(ValueError,match='absolute'):m.configure(tmp_path,'relative')
    with pytest.raises(FileNotFoundError):m.configure(tmp_path,str(tmp_path/'absent'))
    (tmp_path/'models').mkdir();shared=tmp_path.parent/(tmp_path.name+'-shared');shared.mkdir()
    with pytest.raises(ValueError,match='will not be replaced'):m.configure(tmp_path,str(shared))
