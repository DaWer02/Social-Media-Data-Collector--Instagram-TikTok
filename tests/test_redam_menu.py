from unittest.mock import patch

import pytest

from src.redam.menu import ask_path, run_menu


def inputs(*values):
    iterator = iter(values)
    return lambda _: next(iterator)


def test_main_menu_routes_and_returns(capsys):
    from src.cli import run_cli
    with patch("src.redam.menu.run_menu", return_value=0) as menu:
        assert run_cli(input_fn=inputs("8", "0")) == 0
        menu.assert_called_once()
    assert "8. REDAM.id" in capsys.readouterr().out


def test_direct_entrypoints():
    from main import main
    from src.redam.pipeline import main as dataset_main
    with patch("src.redam.menu.run_menu", return_value=0) as menu:
        assert main(["--redam"]) == 0
        assert dataset_main([]) == 0
        assert dataset_main(["menu"]) == 0
        assert menu.call_count == 3


def test_menu_demo_prepare_validate(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("REDAM_DATASET_SECRET", raising=False)
    source, package = tmp_path / "source", tmp_path / "package"
    assert run_menu(input_fn=inputs("1", str(source), "3", str(source / "manifest.json"), str(package),
                                   "4", "1", "5", "1", "7", "1", "0"),
                    secret_fn=lambda _: "s" * 32, data_dir=tmp_path) == 0
    output = capsys.readouterr().out
    assert "509 komentar" in output
    assert "Anotasi valid: BELUM" in output
    assert "annotations.csv" in output
    assert "s" * 32 not in output
    assert (package / "comments.json").is_file()


def test_invalid_input_missing_file_and_cancel(tmp_path, capsys):
    assert run_menu(input_fn=inputs("99", "3", str(tmp_path / "absent.json"), "2", "", "7", "0", "0"), data_dir=tmp_path) == 0
    output = capsys.readouterr().out
    assert "Pilihan tidak valid" in output
    assert "File manifest tidak ditemukan" in output
    assert "Belum ada paket" in output
    assert ask_path("path", inputs("0"), tmp_path) is None


def test_existing_demo_not_overwritten(tmp_path, capsys):
    existing = tmp_path / "existing"
    existing.mkdir()
    assert run_menu(input_fn=inputs("1", str(existing), "0"), data_dir=tmp_path) == 0
    assert "[ERROR]" in capsys.readouterr().out
    assert not list(existing.iterdir())


@pytest.mark.parametrize("exception", [EOFError, KeyboardInterrupt])
def test_menu_interruption(tmp_path, exception, capsys):
    def interrupt(_):
        raise exception()
    assert run_menu(input_fn=interrupt, data_dir=tmp_path) == 0
    assert "ditutup dengan aman" in capsys.readouterr().out
