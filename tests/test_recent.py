"""Lista de archivos recientes."""

import os

from anotador.core.recent import MAX_RECENT, add_recent, recent_labels, remove_recent


def test_add_puts_newest_first(tmp_path):
    a, b = str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")
    recent = add_recent([], a)
    recent = add_recent(recent, b)
    assert recent == [b, a]


def test_reopening_moves_to_front_without_duplicates(tmp_path):
    a, b = str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")
    recent = add_recent(add_recent([], a), b)
    assert add_recent(recent, a) == [a, b]


def test_same_file_written_differently_is_not_duplicated(tmp_path):
    a = str(tmp_path / "Informe.pdf")
    other_spelling = a.upper() if os.name == "nt" else a
    recent = add_recent([a], other_spelling)
    assert len(recent) == 1


def test_relative_paths_are_made_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert add_recent([], "x.pdf") == [str(tmp_path / "x.pdf")]


def test_list_is_limited(tmp_path):
    recent = []
    for i in range(MAX_RECENT + 5):
        recent = add_recent(recent, tmp_path / f"{i}.pdf")
    assert len(recent) == MAX_RECENT
    assert recent[0] == str(tmp_path / f"{MAX_RECENT + 4}.pdf")  # el último abierto


def test_remove(tmp_path):
    a, b = str(tmp_path / "a.pdf"), str(tmp_path / "b.pdf")
    assert remove_recent([b, a], a) == [b]
    assert remove_recent([b], a) == [b]  # si no está, no pasa nada


def test_labels_show_folder_only_for_repeated_names():
    recent = [r"C:\Trabajo\informe.pdf", r"C:\Casa\Informe.pdf", r"C:\Casa\recetas.pdf"]
    assert recent_labels(recent) == ["informe.pdf — Trabajo", "Informe.pdf — Casa",
                                     "recetas.pdf"]
