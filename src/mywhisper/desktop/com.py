"""Minimal COM through ctypes: enough for a few Windows interfaces, without pywin32.

A COM interface pointer points to a table of function pointers (the vtable); its
methods are called by their index in that table, in the order of the interface's
declaration in the Windows SDK headers (IUnknown's QueryInterface, AddRef and
Release always come first, as 0, 1 and 2). Each caller documents its indices.
"""

from __future__ import annotations

import ctypes
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from ctypes import POINTER, byref, c_void_p, wintypes

COINIT_MULTITHREADED = 0x0
COINIT_APARTMENTTHREADED = 0x2
CLSCTX_INPROC_SERVER = 0x1
CLSCTX_ALL = 0x17
RPC_E_CHANGED_MODE = -2147417850  # 0x80010106 as a signed HRESULT


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    @classmethod
    def of(cls, text: str) -> GUID:
        return cls.from_buffer_copy(uuid.UUID(text).bytes_le)


class Com:
    """A COM interface pointer: methods are called by their vtable index."""

    def __init__(self, pointer: c_void_p) -> None:
        self.ptr = pointer

    def call(self, index: int, *args, argtypes=()):
        vtable = ctypes.cast(self.ptr, POINTER(POINTER(c_void_p)))[0]
        prototype = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)
        return prototype(vtable[index])(self.ptr, *args)  # raises OSError on a failed HRESULT

    def query(self, iid: str) -> Com:
        """IUnknown::QueryInterface: the same object seen through another interface."""
        pointer = c_void_p()
        self.call(0, byref(GUID.of(iid)), byref(pointer), argtypes=(POINTER(GUID), POINTER(c_void_p)))
        return Com(pointer)

    def release(self) -> None:
        if self.ptr:
            vtable = ctypes.cast(self.ptr, POINTER(POINTER(c_void_p)))[0]
            ctypes.WINFUNCTYPE(wintypes.ULONG, c_void_p)(vtable[2])(self.ptr)
            self.ptr = c_void_p()


def create(clsid: str, iid: str, context: int = CLSCTX_INPROC_SERVER) -> Com:
    """CoCreateInstance: a new object of class clsid, seen through interface iid."""
    pointer = c_void_p()
    ctypes.OleDLL("ole32").CoCreateInstance(
        byref(GUID.of(clsid)), None, context, byref(GUID.of(iid)), byref(pointer)
    )
    return Com(pointer)


@contextmanager
def apartment(mode: int = COINIT_APARTMENTTHREADED) -> Iterator[None]:
    """COM initialised on this thread for the block. The Qt main thread is already an
    apartment (Qt initialises OLE): joining it is fine, whatever its mode."""
    ole32 = ctypes.OleDLL("ole32")
    try:
        ole32.CoInitializeEx(None, mode)
        joined = True
    except OSError as exc:
        if exc.winerror != RPC_E_CHANGED_MODE:
            raise
        joined = False  # already initialised in the other mode: usable, not ours to end
    try:
        yield
    finally:
        if joined:
            ctypes.WinDLL("ole32").CoUninitialize()
