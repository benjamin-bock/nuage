"""Windows system-tray icon for the GUI (stdlib only: ctypes + Shell_NotifyIconW).

A hidden message-only window receives the tray callbacks; its messages are
pumped from the Tk main loop (TrayIcon.start_pump), so all callbacks run on
the main thread and may touch Tk directly.

Non-Windows platforms: available() is False and TrayIcon is a no-op stub
(closing the window keeps quitting the app there).
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WIN = sys.platform == "win32"


def available() -> bool:
    return IS_WIN


if IS_WIN:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    WM_DESTROY = 0x0002
    WM_QUIT = 0x0012
    WM_COMMAND = 0x0111
    WM_USER = 0x0400
    TRAY_CALLBACK = WM_USER + 20
    WM_LBUTTONUP = 0x0202
    WM_LBUTTONDBLCLK = 0x0203
    WM_RBUTTONUP = 0x0205
    PM_REMOVE = 0x0001

    NIM_ADD = 0x00000000
    NIM_MODIFY = 0x00000001
    NIM_DELETE = 0x00000002
    NIF_MESSAGE = 0x00000001
    NIF_ICON = 0x00000002
    NIF_TIP = 0x00000004

    MF_STRING = 0x0000
    MF_SEPARATOR = 0x0800
    MF_CHECKED = 0x0008
    TPM_RIGHTBUTTON = 0x0002
    IDI_APPLICATION = 32512

    def _res(i: int):
        return ctypes.cast(i, wintypes.LPCWSTR)

    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    class MSG(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                    ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                    ("time", wintypes.DWORD), ("pt", POINT)]

    WNDPROC = ctypes.WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)

    class WNDCLASSEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("style", wintypes.UINT),
                    ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                    ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                    ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE),
                    ("hbrBackground", wintypes.HBRUSH), ("lpszMenuName", wintypes.LPCWSTR),
                    ("lpszClassName", wintypes.LPCWSTR), ("hIconSm", wintypes.HICON)]

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                    ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                    ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                    ("szTip", ctypes.c_wchar * 128), ("dwState", wintypes.DWORD),
                    ("dwStateMask", wintypes.DWORD), ("szInfo", ctypes.c_wchar * 256),
                    ("uVersion", wintypes.UINT), ("szInfoTitle", ctypes.c_wchar * 64),
                    ("dwInfoFlags", wintypes.DWORD), ("guidItem", ctypes.c_byte * 16),
                    ("hBalloonIcon", wintypes.HICON)]

    user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
    user32.RegisterClassExW.restype = wintypes.WORD
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                       wintypes.DWORD, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, wintypes.HWND, wintypes.HMENU,
                                       wintypes.HINSTANCE, wintypes.LPVOID]
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.DefWindowProcW.restype = wintypes.LRESULT
    user32.PeekMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND, wintypes.UINT,
                                    wintypes.UINT, wintypes.UINT]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.TranslateMessage.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.argtypes = [ctypes.POINTER(MSG)]
    user32.DispatchMessageW.restype = wintypes.LRESULT
    user32.CreatePopupMenu.restype = wintypes.HMENU
    user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.WPARAM, wintypes.LPCWSTR]
    user32.TrackPopupMenu.argtypes = [wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int,
                                      ctypes.c_int, wintypes.HWND, ctypes.c_void_p]
    user32.TrackPopupMenu.restype = wintypes.BOOL
    user32.DestroyMenu.argtypes = [wintypes.HMENU]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(POINT)]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.LoadIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR]
    user32.LoadIconW.restype = wintypes.HICON
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    shell32.ExtractIconW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT]
    shell32.ExtractIconW.restype = wintypes.HICON
    shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wintypes.BOOL
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE

    _handler: "TrayIcon | None" = None

    @WNDPROC
    def _wnd_proc(hwnd, msg, wParam, lParam):
        if _handler is not None and _handler.hwnd == hwnd:
            r = _handler._on_message(hwnd, msg, wParam, lParam)
            if r is not None:
                return r
        return user32.DefWindowProcW(hwnd, msg, wParam, lParam)

    class TrayIcon:
        """System-tray icon with a right-click menu.

        Callbacks (on_show/on_sync/on_toggle_auto/on_exit) run on the Tk main thread.
        """
        MENU_SHOW, MENU_SYNC, MENU_AUTO, MENU_EXIT = 1, 2, 3, 4
        _CLASS = "CloudSaveSyncTrayWnd"

        def __init__(self, tooltip: str, on_show, on_sync, on_toggle_auto, on_exit, is_auto_on):
            self.tooltip = tooltip
            self.on_show = on_show
            self.on_sync = on_sync
            self.on_toggle_auto = on_toggle_auto
            self.on_exit = on_exit
            self.is_auto_on = is_auto_on
            self.hwnd = None
            self._hicon = None
            self._added = False
            global _handler
            _handler = self

        def create(self):
            """Hidden message-only window + NIM_ADD. Must run on the Tk main thread."""
            hinst = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = _wnd_proc
            wc.hInstance = hinst
            wc.lpszClassName = self._CLASS
            atom = user32.RegisterClassExW(ctypes.byref(wc))
            if not atom and ctypes.get_last_error() != 1410:  # 1410 = class already exists
                raise ctypes.WinError()
            self.hwnd = user32.CreateWindowExW(
                0, self._CLASS, "CloudSaveSyncTray", 0,
                0, 0, 0, 0, None, None, hinst, None)
            if not self.hwnd:
                raise ctypes.WinError()
            hicon = shell32.ExtractIconW(None, sys.executable, 0)
            if not hicon or hicon == 1:  # 1 = "no icon in file" -> system default
                hicon = user32.LoadIconW(None, _res(IDI_APPLICATION))
            self._hicon = hicon
            nid = NOTIFYICONDATAW()
            nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
            nid.hWnd = self.hwnd
            nid.uID = 1
            nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            nid.uCallbackMessage = TRAY_CALLBACK
            nid.hIcon = hicon
            nid.szTip = self.tooltip[:127]
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid)):
                raise ctypes.WinError()
            self._added = True

        def start_pump(self, root):
            """Pump the hidden window's messages from the Tk main loop."""
            def pump():
                if self.hwnd:
                    msg = MSG()
                    while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                        if msg.message == WM_QUIT:
                            break
                        user32.TranslateMessage(ctypes.byref(msg))
                        user32.DispatchMessageW(ctypes.byref(msg))
                try:
                    root.after(100, pump)
                except Exception:
                    pass  # root destroyed (app quit from the tray menu)
            try:
                root.after(100, pump)
            except Exception:
                pass

        def remove(self):
            if self._added and self.hwnd:
                nid = NOTIFYICONDATAW()
                nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
                nid.hWnd = self.hwnd
                nid.uID = 1
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
                self._added = False
            if self.hwnd:
                user32.DestroyWindow(self.hwnd)
                self.hwnd = None
            if self._hicon:
                user32.DestroyIcon(self._hicon)
                self._hicon = None

        def _on_message(self, hwnd, msg, wParam, lParam):
            if msg == TRAY_CALLBACK:
                if lParam == WM_RBUTTONUP:
                    self._show_menu()
                    return 0
                if lParam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self.on_show()
                    return 0
                return 0
            if msg == WM_COMMAND:
                cmd = wParam & 0xFFFF
                if cmd == self.MENU_SHOW:
                    self.on_show()
                elif cmd == self.MENU_SYNC:
                    self.on_sync()
                elif cmd == self.MENU_AUTO:
                    self.on_toggle_auto()
                elif cmd == self.MENU_EXIT:
                    self.on_exit()
                return 0
            return None  # -> DefWindowProcW

        def _show_menu(self):
            menu = user32.CreatePopupMenu()
            user32.AppendMenuW(menu, MF_STRING, self.MENU_SHOW, "Show Cloud Save Sync")
            user32.AppendMenuW(menu, MF_STRING, self.MENU_SYNC, "Sync now")
            flags = MF_STRING | (MF_CHECKED if self.is_auto_on() else 0)
            user32.AppendMenuW(menu, flags, self.MENU_AUTO, "Auto-sync")
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, self.MENU_EXIT, "Exit")
            pt = POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(self.hwnd)
            user32.TrackPopupMenu(menu, TPM_RIGHTBUTTON, pt.x, pt.y, 0, self.hwnd, None)
            user32.DestroyMenu(menu)

else:
    class TrayIcon:  # no-op stub on Linux/macOS
        def __init__(self, *args, **kwargs):
            pass

        def create(self):
            pass

        def start_pump(self, root):
            pass

        def remove(self):
            pass
