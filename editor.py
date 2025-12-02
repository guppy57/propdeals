import os
import tempfile
import subprocess


def edit_multiline_text(current_text: str = None, field_name: str = "text") -> str:
    """
    Open user's system text editor for multi-line text editing.

    Args:
        current_text: The initial text to populate the editor with (None or empty string for blank)
        field_name: Name of the field being edited (for reference)

    Returns:
        The edited text content after user saves and quits
    """
    # Get user's preferred editor from environment variable, default to vim
    editor = os.environ.get('EDITOR', 'vim')

    # Create temporary file with current text
    with tempfile.NamedTemporaryFile(mode='w+', suffix='.txt', delete=False) as tf:
        # Handle None or empty text
        if current_text:
            tf.write(current_text)
        tf.flush()
        temp_path = tf.name

    try:
        # Open the editor and wait for user to save and quit
        subprocess.call([editor, temp_path])

        # Read back the edited content
        with open(temp_path, 'r') as f:
            edited_text = f.read()

        return edited_text
    finally:
        # Clean up the temporary file
        os.unlink(temp_path)
