"""Registro en Windows para abrir PDFs con doble clic (con un registro simulado)."""

from anotador.core.windows_integration import (APP_NAME, LEGACY_APP_NAMES, PROG_ID, is_registered,
                                               open_command, register, registered_command,
                                               unregister)

EXE = r"C:\Users\ana\AppData\Local\Programs\Anotop.at\Anotop.at.exe"


class FakeRegistry:
    """Un diccionario {clave: {nombre: valor}} que se comporta como HKEY_CURRENT_USER."""

    def __init__(self, data=None):
        self.data = {k.lower(): dict(v) for k, v in (data or {}).items()}

    def set_value(self, key, name, value):
        self.data.setdefault(key.lower(), {})[name] = value

    def get_value(self, key, name):
        return self.data.get(key.lower(), {}).get(name)

    def delete_value(self, key, name):
        self.data.get(key.lower(), {}).pop(name, None)

    def delete_tree(self, key):
        prefix = key.lower()
        for k in [k for k in self.data if k == prefix or k.startswith(prefix + "\\")]:
            del self.data[k]


def test_command_quotes_paths_with_spaces():
    assert open_command(EXE) == f'"{EXE}" "%1"'


def test_register_makes_app_known_to_windows():
    reg = FakeRegistry()
    register(reg, EXE)
    assert reg.get_value(rf"Software\Classes\{PROG_ID}\shell\open\command", "") == \
        open_command(EXE)
    assert reg.get_value(r"Software\Classes\.pdf\OpenWithProgids", PROG_ID) == ""
    assert reg.get_value(r"Software\Classes\Applications\Anotop.at.exe",
                         "FriendlyAppName") == APP_NAME
    capabilities = reg.get_value(r"Software\RegisteredApplications", APP_NAME)
    assert reg.get_value(capabilities + r"\FileAssociations", ".pdf") == PROG_ID
    assert is_registered(reg, EXE)


def test_moved_folder_is_not_registered_anymore():
    reg = FakeRegistry()
    register(reg, EXE)
    assert not is_registered(reg, r"D:\Otra carpeta\Anotop.at.exe")
    assert registered_command(reg) == open_command(EXE)


def test_unregister_removes_only_our_entries():
    other = {
        # Lo que hay en un Windows real y no es nuestro: no se puede tocar.
        r"Software\Classes\.pdf": {"": "AcroExch.Document.DC"},
        r"Software\Classes\.pdf\OpenWithProgids": {"MSEdgePDF": ""},
        r"Software\RegisteredApplications": {"Microsoft Edge": r"Software\Clients\Edge"},
        # Preferencias de la propia app (QSettings): tampoco.
        r"Software\AnotadorPDF\Anotador PDF": {"night_mode": "true"},
    }
    reg = FakeRegistry(other)
    register(reg, EXE)
    unregister(reg, EXE)
    assert not is_registered(reg, EXE)
    remaining = {k: v for k, v in reg.data.items() if v}
    assert remaining == FakeRegistry(other).data


def test_unregister_when_not_registered_does_nothing():
    reg = FakeRegistry({r"Software\Classes\.pdf": {"": "AcroExch.Document.DC"}})
    unregister(reg, EXE)
    assert reg.data == FakeRegistry({r"Software\Classes\.pdf": {"": "AcroExch.Document.DC"}}).data


def test_app_name_is_the_new_one_and_old_registration_is_replaced():
    assert APP_NAME == "Anotop.at"
    # Así lo dejaba registrado la versión 1.1.0, cuando se llamaba «Anotador PDF».
    reg = FakeRegistry({r"Software\RegisteredApplications":
                        {"Anotador PDF": r"Software\AnotadorPDF\Capabilities"}})
    register(reg, EXE)
    names = reg.data[r"software\registeredapplications"]
    assert APP_NAME in names and not any(old in names for old in LEGACY_APP_NAMES)
    unregister(reg, EXE)
    assert not reg.data[r"software\registeredapplications"]
