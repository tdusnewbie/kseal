import pytest
import os
from unittest.mock import patch

from kseal.editor import open_editor

@patch("kseal.editor.subprocess.call")
@patch.dict(os.environ, {"EDITOR": "my-editor"})
def test_open_editor_env(mock_call):
    open_editor("path/to/file")
    mock_call.assert_called_once_with(["my-editor", "path/to/file"])

@patch("kseal.editor.subprocess.call")
@patch.dict(os.environ, clear=True)
@patch("shutil.which")
def test_open_editor_fallback(mock_which, mock_call):
    # 'vi' not found, 'nano' found
    mock_which.side_effect = lambda x: x if x == "nano" else None
    
    open_editor("path/to/file")
    mock_call.assert_called_once_with(["nano", "path/to/file"])

@patch.dict(os.environ, clear=True)
@patch("shutil.which", return_value=None)
def test_open_editor_no_fallback(mock_which):
    with pytest.raises(RuntimeError, match="No editor found"):
        open_editor("path/to/file")
