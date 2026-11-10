"""Finished records on disk, and the command line check that reads them."""
import copy
import json

import pytest

from app.services.game_record import _main, simulate
from app.services.record_store import RecordStore


@pytest.fixture(scope="module")
def sample():
    return simulate(seed=5, players=3)


def test_saved_record_loads_back_unchanged(tmp_path, sample):
    store = RecordStore(tmp_path / "records")
    store.save("abc123", sample)
    assert store.load("abc123") == json.loads(json.dumps(sample))
    # Only the finished file is left behind, never the temporary one
    assert [p.name for p in (tmp_path / "records").iterdir()] == ["abc123.json.gz"]


def test_missing_record_is_none(tmp_path):
    assert RecordStore(tmp_path).load("nothing") is None


@pytest.mark.parametrize("room_id", ["../etc", "a/b", "a.b", "", "x" * 65])
def test_room_ids_cannot_leave_the_directory(tmp_path, room_id):
    with pytest.raises(ValueError):
        RecordStore(tmp_path).path(room_id)


def test_check_reads_gzipped_records(tmp_path, sample, capsys):
    store = RecordStore(tmp_path)
    store.save("game", sample)
    assert _main(["check", str(store.path("game"))]) == 0
    assert capsys.readouterr().out.startswith(f"ok: {len(sample['events'])} events")


def test_check_rejects_a_broken_record(tmp_path, sample, capsys):
    broken = copy.deepcopy(sample)
    del broken["events"][len(broken["events"]) // 2]
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))
    assert _main(["check", str(path)]) == 1
    assert capsys.readouterr().out.startswith("invalid:")
