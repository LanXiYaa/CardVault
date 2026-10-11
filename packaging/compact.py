"""Remove optional Qt features unused by the raster QWidget application."""
from pathlib import Path
import pefile
OPTIONAL = {'opengl32sw.dll', 'qt6opengl.dll', 'qt6pdf.dll', 'qt6quick.dll', 'qt6qml.dll', 'qt6qmlmeta.dll', 'qt6qmlmodels.dll', 'qt6qmlworkerscript.dll', 'qt6virtualkeyboard.dll', 'qtvirtualkeyboardplugin.dll', 'qpdf.dll', 'qdirect2d.dll'}
def compact_package(package):
    package = Path(package).resolve(strict=True)
    removed = {p for p in (package / '_internal/PySide6').rglob('*.dll') if p.name.lower() in OPTIONAL}
    names = {p.name.lower() for p in removed}
    for file in package.rglob('*'):
        if file in removed or file.suffix.lower() not in {'.dll', '.pyd', '.exe'}: continue
        with pefile.PE(str(file), fast_load=True) as pe:
            pe.parse_data_directories(directories=[1, 13])
            for entry in getattr(pe, 'DIRECTORY_ENTRY_IMPORT', []) + getattr(pe, 'DIRECTORY_ENTRY_DELAY_IMPORT', []):
                if entry.dll.decode('ascii').lower() in names:
                    raise RuntimeError(f'{file.name} depends on removed {entry.dll}')
    size = sum(p.stat().st_size for p in removed)
    for file in removed: file.unlink()
    return {'removed_bytes': size, 'removed': sorted(str(p.relative_to(package)) for p in removed)}
