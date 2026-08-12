import pathlib

# prepare.py
p = pathlib.Path('prepare.py')
text = p.read_text('utf-8')
text = text.replace('VAULT_DIR = "vault"', 'VAULT_DIR = "exam upload"')
text = text.replace('image_folder = SCRIPT_DIR / "vault"', 'image_folder = SCRIPT_DIR / "exam upload"')
text = text.replace('uploaded_folder = SCRIPT_DIR / "processed"', 'uploaded_folder = SCRIPT_DIR / "uploaded exam"')
text = text.replace('git_portable\\cmd\\git.exe rm "vault/', 'git_portable\\cmd\\git.exe rm "exam upload/')
text = text.replace('git rm vault/', 'git rm "exam upload"/')
text = text.replace('remove the file from vault/', 'remove the file from exam upload/')
p.write_text(text, 'utf-8')

# compress_and_sync.py
p = pathlib.Path('compress_and_sync.py')
text = p.read_text('utf-8')
text = text.replace('VAULT_DIR = SCRIPT_DIR / "vault"', 'VAULT_DIR = SCRIPT_DIR / "exam upload"')
text = text.replace('PROCESSED_DIR = SCRIPT_DIR / "processed"', 'PROCESSED_DIR = SCRIPT_DIR / "uploaded exam"')
p.write_text(text, 'utf-8')
