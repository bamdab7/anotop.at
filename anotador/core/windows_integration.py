"""Registrar la aplicación en Windows para abrir PDFs con doble clic.

Desde Windows 10, ninguna aplicación puede ponerse sola como predeterminada para
un tipo de archivo: lo decide el usuario. Lo que sí podemos hacer (y es lo que
hacen los instaladores) es *registrarla*: así aparece en «Abrir con» y en
Configuración > Aplicaciones predeterminadas, donde el usuario la elige.

Todo se escribe en HKEY_CURRENT_USER (solo para el usuario actual, sin permisos
de administrador). Las claves se construyen aquí, sin tocar el registro, para
poder probarlas; ``WindowsRegistry`` es quien las escribe de verdad.
"""

from dataclasses import dataclass
from typing import Protocol

APP_NAME = "Anotador PDF"
PROG_ID = "AnotadorPDF.Document"
CAPABILITIES_KEY = r"Software\AnotadorPDF\Capabilities"
CLASSES = r"Software\Classes"


@dataclass(frozen=True)
class RegistryValue:
    key: str    # ruta dentro de HKEY_CURRENT_USER
    name: str   # "" es el valor «(Predeterminado)» de la clave
    value: str


class Registry(Protocol):
    def set_value(self, key: str, name: str, value: str) -> None: ...
    def get_value(self, key: str, name: str) -> str | None: ...
    def delete_value(self, key: str, name: str) -> None: ...
    def delete_tree(self, key: str) -> None: ...


def _exe_name(exe_path: str) -> str:
    return exe_path.replace("/", "\\").rsplit("\\", 1)[-1]


def open_command(exe_path: str) -> str:
    """Orden que ejecuta Windows al hacer doble clic: comillas por si hay espacios."""
    return f'"{exe_path}" "%1"'


def association_values(exe_path: str) -> list[RegistryValue]:
    """Lo que hay que escribir para que Windows conozca la aplicación."""
    exe = _exe_name(exe_path)
    command = open_command(exe_path)
    icon = f'"{exe_path}",0'
    prog = rf"{CLASSES}\{PROG_ID}"
    app = rf"{CLASSES}\Applications\{exe}"
    return [
        # Tipo de documento propio, con su icono y la orden para abrirlo.
        RegistryValue(prog, "", "Documento PDF"),
        RegistryValue(prog, "FriendlyTypeName", "Documento PDF"),
        RegistryValue(rf"{prog}\DefaultIcon", "", icon),
        RegistryValue(rf"{prog}\shell\open\command", "", command),
        # Que aparezca en «Abrir con» para los .pdf.
        RegistryValue(rf"{CLASSES}\.pdf\OpenWithProgids", PROG_ID, ""),
        RegistryValue(app, "FriendlyAppName", APP_NAME),
        RegistryValue(rf"{app}\SupportedTypes", ".pdf", ""),
        RegistryValue(rf"{app}\shell\open\command", "", command),
        # Que aparezca en Configuración > Aplicaciones predeterminadas.
        RegistryValue(CAPABILITIES_KEY, "ApplicationName", APP_NAME),
        RegistryValue(CAPABILITIES_KEY, "ApplicationDescription",
                      "Visor de PDF para resaltar, subrayar, escribir notas y dibujar"),
        RegistryValue(rf"{CAPABILITIES_KEY}\FileAssociations", ".pdf", PROG_ID),
        RegistryValue(r"Software\RegisteredApplications", APP_NAME, CAPABILITIES_KEY),
    ]


def register(registry: Registry, exe_path: str) -> None:
    for item in association_values(exe_path):
        registry.set_value(item.key, item.name, item.value)


def unregister(registry: Registry, exe_path: str) -> None:
    """Quita exactamente lo que escribe ``register``, nada más.

    Ojo: ``Software\\AnotadorPDF`` también guarda las preferencias de la app; de
    ahí solo se borra la subclave ``Capabilities``. Y de ``.pdf`` solo nuestro
    valor: la clave es de Windows y la comparten todos los programas.
    """
    exe = _exe_name(exe_path)
    registry.delete_tree(rf"{CLASSES}\{PROG_ID}")
    registry.delete_tree(rf"{CLASSES}\Applications\{exe}")
    registry.delete_tree(CAPABILITIES_KEY)
    registry.delete_value(rf"{CLASSES}\.pdf\OpenWithProgids", PROG_ID)
    registry.delete_value(r"Software\RegisteredApplications", APP_NAME)


def registered_command(registry: Registry) -> str | None:
    """La orden registrada ahora mismo (``None`` si la app no está registrada)."""
    return registry.get_value(rf"{CLASSES}\{PROG_ID}\shell\open\command", "")


def is_registered(registry: Registry, exe_path: str) -> bool:
    """¿Registrada y apuntando a este .exe? (si se movió la carpeta, hay que repetirlo)."""
    command = registered_command(registry)
    return command is not None and command.lower() == open_command(exe_path).lower()


class WindowsRegistry:
    """El registro de verdad (HKEY_CURRENT_USER). Solo funciona en Windows."""

    def __init__(self):
        import winreg
        self._winreg = winreg

    def set_value(self, key: str, name: str, value: str) -> None:
        winreg = self._winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)

    def get_value(self, key: str, name: str) -> str | None:
        winreg = self._winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key) as k:
                return winreg.QueryValueEx(k, name)[0]
        except OSError:
            return None

    def delete_value(self, key: str, name: str) -> None:
        winreg = self._winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_SET_VALUE) as k:
                winreg.DeleteValue(k, name)
        except OSError:
            pass  # ya no estaba

    def delete_tree(self, key: str) -> None:
        winreg = self._winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0,
                                winreg.KEY_READ | winreg.KEY_WRITE) as k:
                while True:
                    try:
                        child = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    self.delete_tree(rf"{key}\{child}")
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key)
        except OSError:
            pass  # ya no estaba


def notify_shell() -> None:
    """Avisa al Explorador de que han cambiado las asociaciones (para que se note
    sin reiniciar)."""
    try:
        import ctypes
        SHCNE_ASSOCCHANGED, SHCNF_IDLIST = 0x08000000, 0
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass
