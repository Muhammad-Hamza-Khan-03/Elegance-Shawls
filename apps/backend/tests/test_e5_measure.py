import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from e5_measure import build_parser  # noqa: E402


def test_defaults_and_valid_values():
    a = build_parser().parse_args(["m"])
    assert (a.rows, a.batch) == (500, 32)
    a = build_parser().parse_args(["m", "--rows", "1", "--batch", "7"])
    assert (a.rows, a.batch) == (1, 7)


@pytest.mark.parametrize("flag", ["--rows", "--batch"])
@pytest.mark.parametrize("bad", ["0", "-1", "1.5", "abc", ""])
def test_rows_and_batch_reject_non_positive_or_non_integer(flag, bad, capsys):
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["m", flag, bad])
    assert e.value.code == 2 and "positive integer" in capsys.readouterr().err
