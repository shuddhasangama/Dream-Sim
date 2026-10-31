"""Private local receipts: Windows user protection or configured Fernet key."""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets


def dpapi(data, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    library = ctypes.WinDLL('crypt32', use_last_error=True)
    function = library.CryptUnprotectData if decrypt else library.CryptProtectData
    function.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                         ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    function.restype = wintypes.BOOL
    if not function(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target)):
        raise ValueError('Windows receipt protection failed')
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        free = ctypes.WinDLL('kernel32').LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        free(target.data)


class ReceiptStore:
    def __init__(self, directory='data/signzy-test-receipts'):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        key = os.getenv('SIGNZY_RECEIPT_ENCRYPTION_KEY')
        if key:
            from cryptography.fernet import Fernet
            self.cipher = Fernet(key.encode())
            self.mode = 'fernet'
        elif os.name == 'nt':
            self.mode = 'windows-dpapi'
        else:
            raise ValueError('Set SIGNZY_RECEIPT_ENCRYPTION_KEY before calling Signzy on this host')
        # Fail before a billable request if encryption or filesystem writes fail.
        self.encrypt(b'preflight')
        check = self.directory / ('.write-check-' + secrets.token_hex(8))
        with check.open('xb'):
            pass
        check.unlink()

    def encrypt(self, value):
        return self.cipher.encrypt(value) if self.mode == 'fernet' else dpapi(value)

    def save(self, evidence):
        path = self.directory / (evidence['receipt_id'] + '.' + self.mode + '.enc')
        encrypted = self.encrypt(json.dumps(evidence, ensure_ascii=False).encode())
        with path.open('xb') as handle:
            handle.write(encrypted)
        return path


def read_private(path):
    path = Path(path)
    data = path.read_bytes()
    if path.name.endswith('.windows-dpapi.enc') and os.name == 'nt':
        raw = dpapi(data, decrypt=True)
    elif path.name.endswith('.fernet.enc'):
        from cryptography.fernet import Fernet
        raw = Fernet(os.environ['SIGNZY_RECEIPT_ENCRYPTION_KEY'].encode()).decrypt(data)
    else:
        raise ValueError('Receipt requires its original protection method and account/key')
    return json.loads(raw)
