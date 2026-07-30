import os
import subprocess

def open_editor(filepath: str):
    editor = os.environ.get('EDITOR')
    if not editor:
        for fallback in ['vi', 'nano', 'vim']:
            import shutil
            if shutil.which(fallback):
                editor = fallback
                break
    if not editor:
        raise RuntimeError("No editor found in $EDITOR or fallbacks (vi, nano, vim)")
    subprocess.call([editor, filepath])
