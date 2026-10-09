import subprocess
from pathlib import Path

import pytest

import bond_estimator
from estimator import selftest

FIXTURE = Path(__file__).parent / "fixtures" / "fund.toml"


@pytest.fixture
def gate_passes(monkeypatch):
    monkeypatch.setattr(selftest, "run", lambda: selftest.Result(True, "99 passed in 0.01s", ""))


# --- The self-test gate ------------------------------------------------------------------

def test_failing_self_tests_block_the_estimate(monkeypatch, capsys):
    monkeypatch.setattr(selftest, "run", lambda: selftest.Result(False, "1 failed", "FAILED test_x\n"))
    loaded = []
    monkeypatch.setattr(bond_estimator, "load", lambda *a, **k: loaded.append(a))

    assert bond_estimator.main([str(FIXTURE)]) == 1

    out, err = capsys.readouterr()
    assert loaded == []  # the fund file is never even read
    assert out == ""
    assert "FAILED test_x" in err
    assert "Self-tests failed, so no estimate was produced." in err


def test_self_tests_run_before_the_fund_file_is_read(monkeypatch):
    order = []

    def fake_run():
        order.append("tests")
        return selftest.Result(True, "ok", "")

    def fake_load(*args, **kwargs):
        order.append("load")
        raise bond_estimator.ConfigError("stop here")

    monkeypatch.setattr(selftest, "run", fake_run)
    monkeypatch.setattr(bond_estimator, "load", fake_load)
    bond_estimator.main([str(FIXTURE)])
    assert order == ["tests", "load"]


def test_gate_runs_pytest_in_a_separate_process(monkeypatch):
    calls = []

    def fake_subprocess_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return subprocess.CompletedProcess(cmd, 0, stdout="....\n4 passed in 0.10s\n", stderr="")

    monkeypatch.delenv(selftest.RUNNING_FLAG, raising=False)
    monkeypatch.setattr(selftest.subprocess, "run", fake_subprocess_run)
    result = selftest.run()

    [(cmd, kwargs)] = calls
    assert cmd[1:3] == ["-m", "pytest"]
    assert kwargs["cwd"] == selftest.ROOT
    assert kwargs["env"][selftest.RUNNING_FLAG] == "1"
    assert result == selftest.Result(True, "4 passed in 0.10s", "....\n4 passed in 0.10s\n")


@pytest.mark.parametrize("returncode", [1, 2, 5])  # failures, interrupted, no tests collected
def test_gate_fails_on_any_nonzero_pytest_exit(monkeypatch, returncode):
    monkeypatch.delenv(selftest.RUNNING_FLAG, raising=False)
    monkeypatch.setattr(
        selftest.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, returncode, stdout="x\n", stderr=""),
    )
    assert selftest.run().passed is False


def test_gate_refuses_to_start_itself_from_inside_the_tests(monkeypatch):
    monkeypatch.setenv(selftest.RUNNING_FLAG, "1")
    with pytest.raises(RuntimeError, match="self-tests tried to start the self-tests again"):
        selftest.run()


# --- End to end, with the gate passing ---------------------------------------------------

def test_prints_irr_table(gate_passes, capsys):
    assert bond_estimator.main([str(FIXTURE)]) == 0
    out = capsys.readouterr().out
    assert "Self-tests: 99 passed in 0.01s" in out
    assert "Test High Yield Fund: fund data as of 2026-01-15" in out
    assert "Expected IRR over the next ~5 years (5.00 = 2 × 3 − 1)" in out
    # benign: 7.2 − 0.1 − 0.03 − (1 × 0.6 + 1 × 7.2 / 2 / 100) = 6.434%
    assert "  benign         1.00%    40.00%   6.43%" in out
    # stress: 7.2 − 0.13 − (8 × 0.75 + 8 × 7.2 / 2 / 100) = 0.782%
    assert "  stress         8.00%    25.00%   0.78%" in out


def test_set_changes_the_result_and_is_shown(gate_passes, capsys):
    assert bond_estimator.main([str(FIXTURE), "--set", "stress.default_rate=0.02"]) == 0
    out = capsys.readouterr().out
    assert "Changed with --set: stress.default_rate = 0.02" in out
    # 7.2 − 0.13 − (2 × 0.75 + 2 × 7.2 / 2 / 100) = 5.498%
    assert "  stress         2.00%    25.00%   5.50%" in out


def test_config_problem_exits_2_with_the_reason(gate_passes, capsys):
    assert bond_estimator.main([str(FIXTURE), "--set", "yield_to_worst=7.2"]) == 2
    out, err = capsys.readouterr()
    assert "Expected IRR" not in out
    assert "Enter it as a decimal: 0.072 for 7.2%." in err
