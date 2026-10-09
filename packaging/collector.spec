# Build from the repository root via build.sh.
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

root = Path(SPECPATH).parent
oci_data, oci_binaries, oci_imports = collect_all('oci_cli')
sdk_data, sdk_binaries, sdk_imports = collect_all('oci')
service_data, service_binaries, service_imports = collect_all('services')
a = Analysis([str(root / 'src' / 'binary_entrypoint.py')],
    pathex=[str(root)],
    binaries=oci_binaries + sdk_binaries + service_binaries,
    datas=oci_data + sdk_data + service_data + [(str(root / 'build' / 'suite'), 'suite')],
    hiddenimports=oci_imports + sdk_imports + service_imports,
    excludes=['IPython', 'jupyter', 'notebook', 'matplotlib', 'seaborn', 'sklearn'],
    noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [],
    name='oci-finops-helper', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, console=True)
