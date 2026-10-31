import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "e5_measure.py"
SPEC = importlib.util.spec_from_file_location("e5_measure", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT}")
e5_measure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(e5_measure)


@pytest.mark.parametrize("flag", ["--rows", "--batch"])
@pytest.mark.parametrize("value", ["0", "-1"])
def test_measurement_parser_rejects_non_positive_sizes(flag, value):
    with pytest.raises(SystemExit):
        e5_measure.build_parser().parse_args(["/tmp/model", flag, value])


def test_measurement_parser_accepts_positive_sizes():
    args = e5_measure.build_parser().parse_args(["/tmp/model", "--rows", "1", "--batch", "2"])
    assert (args.rows, args.batch) == (1, 2)
