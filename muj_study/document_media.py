"""Normalize embedded Office media without changing the source document."""
import io
import os
from pathlib import Path
import tempfile
import struct
import ctypes
import uuid


def placeable_wmf(blob):
    """Add the missing display bounds to a standard (non-placeable) WMF."""
    if not blob.startswith(b'\x01\x00\x09\x00'): return blob
    offset, x, y, width, height = 18, 0, 0, 1000, 1000
    while offset + 6 <= len(blob):
        words, kind = struct.unpack_from('<IH', blob, offset)
        if words < 3 or offset + words * 2 > len(blob): break
        if words >= 5 and kind == 0x020B: y, x = struct.unpack_from('<hh', blob, offset + 6)
        if words >= 5 and kind == 0x020C: height, width = struct.unpack_from('<hh', blob, offset + 6)
        offset += words * 2
    bounds = (x, y, x + abs(width), y + abs(height))
    if not all(-32768 <= v <= 32767 for v in bounds): raise ValueError('Metafile bounds are invalid')
    header = struct.pack('<IHhhhhHI', 0x9AC6CDD7, 0, *bounds, 1440, 0)
    checksum = 0
    for word in struct.unpack('<10H', header): checksum ^= word
    return header + struct.pack('<H', checksum) + blob


def normalize_image(blob, content_type):
    if blob.startswith(b'\x89PNG\r\n\x1a\n'): return blob, 'image/png'
    if blob.startswith(b'\xff\xd8\xff'): return blob, 'image/jpeg'
    if blob[:4] == b'RIFF' and blob[8:12] == b'WEBP': return blob, 'image/webp'
    try:
        from PIL import Image
        with Image.open(io.BytesIO(blob)) as source:
            source.load()
            out = io.BytesIO()
            source.convert('RGB').save(out, format='PNG')
            return out.getvalue(), 'image/png'
    except (OSError, ValueError): pass
    if os.name != 'nt' or not any(x in content_type.lower() for x in ['emf', 'wmf', 'metafile']):
        raise ValueError('Unsupported embedded image')
    # Windows' own Office-compatible renderer handles standard WMF files that
    # Pillow cannot identify, including WMF data incorrectly labelled as EMF.
    with tempfile.TemporaryDirectory(prefix='muj-media-') as folder:
        root = Path(folder)
        source = root / ('source.wmf' if blob.startswith(b'\x01\x00\x09\x00') else 'source.emf')
        source.write_bytes(placeable_wmf(blob))
        output = root / 'rendered.png'
        render_windows(source, output)
        return output.read_bytes(), 'image/png'


def render_windows(source, output):
    """Render metafiles through native GDI+, without executing scripts."""
    dll = ctypes.WinDLL('gdiplus')
    pointer = ctypes.c_void_p
    class Startup(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint), ('debug', pointer), ('background', ctypes.c_int), ('codecs', ctypes.c_int)]
    signatures = {
        'GdiplusStartup': [ctypes.POINTER(ctypes.c_size_t), ctypes.POINTER(Startup), pointer],
        'GdiplusShutdown': [ctypes.c_size_t],
        'GdipLoadImageFromFile': [ctypes.c_wchar_p, ctypes.POINTER(pointer)],
        'GdipGetImageWidth': [pointer, ctypes.POINTER(ctypes.c_uint)],
        'GdipGetImageHeight': [pointer, ctypes.POINTER(ctypes.c_uint)],
        'GdipCreateBitmapFromScan0': [ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, pointer, ctypes.POINTER(pointer)],
        'GdipGetImageGraphicsContext': [pointer, ctypes.POINTER(pointer)],
        'GdipGraphicsClear': [pointer, ctypes.c_uint],
        'GdipDrawImageRectI': [pointer, pointer, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int],
        'GdipSaveImageToFile': [pointer, ctypes.c_wchar_p, pointer, pointer],
        'GdipDeleteGraphics': [pointer], 'GdipDisposeImage': [pointer],
    }
    for name, args in signatures.items():
        getattr(dll, name).argtypes = args
        getattr(dll, name).restype = ctypes.c_int
    def checked(name, *args):
        if getattr(dll, name)(*args): raise ValueError('Windows could not render embedded image')
    token = ctypes.c_size_t()
    checked('GdiplusStartup', ctypes.byref(token), ctypes.byref(Startup(1, None, 0, 0)), None)
    image, bitmap, graphics = pointer(), pointer(), pointer()
    try:
        checked('GdipLoadImageFromFile', str(source), ctypes.byref(image))
        width, height = ctypes.c_uint(), ctypes.c_uint()
        checked('GdipGetImageWidth', image, ctypes.byref(width))
        checked('GdipGetImageHeight', image, ctypes.byref(height))
        scale = min(3, 4096 / max(1, width.value, height.value))
        w, h = max(1, int(width.value * scale)), max(1, int(height.value * scale))
        checked('GdipCreateBitmapFromScan0', w, h, 0, 0x26200A, None, ctypes.byref(bitmap))
        checked('GdipGetImageGraphicsContext', bitmap, ctypes.byref(graphics))
        checked('GdipGraphicsClear', graphics, 0xFFFFFFFF)
        checked('GdipDrawImageRectI', graphics, image, 0, 0, w, h)
        encoder = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID('557cf406-1a04-11d3-9a73-0000f81ef32e').bytes_le)
        checked('GdipSaveImageToFile', bitmap, str(output), encoder, None)
    finally:
        if graphics: dll.GdipDeleteGraphics(graphics)
        if bitmap: dll.GdipDisposeImage(bitmap)
        if image: dll.GdipDisposeImage(image)
        dll.GdiplusShutdown(token)
