"""Preferencias de las barras de herramientas."""

from anotador.core.toolbar_layout import (DEFAULT_ANNOTATION_POSITION, DEFAULT_HIDDEN,
                                          AnnotationBarPosition, annotation_position,
                                          hidden_items, separators_visible)

KNOWN = {"open", "save", "save_as", "undo"}


def test_nothing_saved_uses_defaults():
    assert hidden_items(None, KNOWN) == set(DEFAULT_HIDDEN) & KNOWN


def test_saved_empty_list_means_everything_visible():
    # El usuario lo ha mostrado todo: no hay que volver a los valores por defecto.
    assert hidden_items([], KNOWN) == set()
    assert hidden_items("", KNOWN) == set()


def test_single_value_comes_as_text():
    assert hidden_items("undo", KNOWN) == {"undo"}


def test_unknown_keys_are_ignored():
    assert hidden_items(["undo", "boton_de_una_version_vieja"], KNOWN) == {"undo"}


def test_annotation_position():
    assert annotation_position("top") == AnnotationBarPosition.TOP
    assert annotation_position("hidden") == AnnotationBarPosition.HIDDEN
    assert annotation_position(None) == DEFAULT_ANNOTATION_POSITION
    assert annotation_position("diagonal") == DEFAULT_ANNOTATION_POSITION


def test_separators_only_between_visible_groups():
    assert separators_visible([True, True, True]) == [True, True]
    # Grupo del medio vacío: un solo separador, no dos seguidos.
    assert separators_visible([True, False, True]) == [True, False]
    # Nada antes o nada después: sin separador en el borde.
    assert separators_visible([False, True, True]) == [False, True]
    assert separators_visible([True, False, False]) == [False, False]
    assert separators_visible([True]) == []
    assert separators_visible([]) == []
