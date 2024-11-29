import sys
from cx_Freeze import setup, Executable

# Les dépendances sont automatiquement détectées, mais il peut être nécessaire de les ajuster.
build_exe_options = {
    "excludes": ["tkinter", "unittest"],
    "zip_include_packages": ["encodings", "PySide6"],
}

# base="Win32GUI" devrait être utilisé uniquement avec l’app Windows GUI 
base = "Win32GUI" if sys.platform == "win32" else None

setup(
    name="capture_screenshotsReuni",
    version="0.1",
    description="Capture ecran",
    options={"build_exe": build_exe_options},
    executables=[Executable("capture_screenshotsReuni.py", base=base)],
)