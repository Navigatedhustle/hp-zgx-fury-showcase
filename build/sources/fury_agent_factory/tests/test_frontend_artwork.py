import json
from pathlib import Path

import pytest
import frontend_artwork as artwork


def test_new_run_pins_artwork_and_versions_survive_source_asset_changes(tmp_path,monkeypatch):
    source=tmp_path/'source.webp';source.write_bytes(b'first public illustration')
    monkeypatch.setattr(artwork,'SOURCE',source)
    run=tmp_path/'run';run.mkdir();version=run/'version-1';version.mkdir()
    artwork.pin_artwork(run);original=(run/artwork.NAME).read_bytes()
    source.write_bytes(b'a different future illustration')
    artwork.pin_artwork(run)
    assert (run/artwork.NAME).read_bytes()==original
    assert artwork.artwork_for(version)['hero'].endswith('Zmlyc3QgcHVibGljIGlsbHVzdHJhdGlvbg==')


def test_existing_runs_without_artwork_keep_their_original_environment(tmp_path):
    candidate=tmp_path/'legacy'/'candidate';candidate.mkdir(parents=True)
    assert artwork.artwork_for(candidate)=={}
    assert artwork.artwork_script(candidate)==''
    assert not (candidate.parent/artwork.NAME).exists()


def test_modified_pinned_artwork_is_refused_instead_of_silently_replaced(tmp_path,monkeypatch):
    source=tmp_path/'source.webp';source.write_bytes(b'public illustration')
    monkeypatch.setattr(artwork,'SOURCE',source);artwork.pin_artwork(tmp_path)
    path=tmp_path/artwork.NAME;data=json.loads(path.read_text());data['sha256']='0'*64;path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='checksum'):artwork.artwork_for(tmp_path)
