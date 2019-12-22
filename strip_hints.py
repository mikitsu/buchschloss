"""Strip type hints to make them compatible with earlier Pythons"""
import os
import strip_hints

for dirpath, __, filenames in os.walk('buchschloss'):
    for filename in filenames:
        full_path = os.path.join(dirpath, filename)
        new_text = strip_hints.strip_file_to_string(full_path)
        with open(full_path, 'w', encoding='UTF-8') as f:
            f.write(new_text)
