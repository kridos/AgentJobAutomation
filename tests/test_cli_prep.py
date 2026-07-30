import pytest

from automator.cli import build_parser


def test_prep_dispatches_to_generate_interview_prep_and_prints_path(monkeypatch, capsys):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "ok", "path": "output/2026-07-01/simplify/acme_corp/swe_intern/interview_prep.md"},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp"])
    args.func(args)

    captured = capsys.readouterr()
    assert "interview_prep.md" in captured.out


def test_prep_passes_role_flag_through(monkeypatch):
    captured_kwargs = {}

    def _fake_generate(company, role_hint=""):
        captured_kwargs["company"] = company
        captured_kwargs["role_hint"] = role_hint
        return {"status": "ok", "path": "some/path.md"}

    monkeypatch.setattr("interview_prep.generate_interview_prep", _fake_generate)

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp", "--role", "ML Intern"])
    args.func(args)

    assert captured_kwargs["company"] == "Acme Corp"
    assert captured_kwargs["role_hint"] == "ML Intern"


def test_prep_exits_nonzero_on_not_found(monkeypatch):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "not_found", "path": None},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Nonexistent Co"])

    with pytest.raises(SystemExit):
        args.func(args)


def test_prep_exits_nonzero_on_validation_blocked(monkeypatch):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "validation_blocked", "path": None},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp"])

    with pytest.raises(SystemExit):
        args.func(args)


def test_prep_exits_nonzero_on_generation_failed(monkeypatch):
    monkeypatch.setattr(
        "interview_prep.generate_interview_prep",
        lambda company, role_hint="": {"status": "generation_failed", "path": None},
    )

    parser = build_parser()
    args = parser.parse_args(["prep", "Acme Corp"])

    with pytest.raises(SystemExit):
        args.func(args)
