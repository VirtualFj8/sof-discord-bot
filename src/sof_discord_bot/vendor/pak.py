# Fully vendored copy of pak.py to avoid relying on repo root imports
import sys
import struct
import os
from pathlib import Path
import fnmatch


def _iter_pak_directory(pak_data):
    try:
        dir_off = struct.unpack_from('<I', pak_data, 4)[0]
        dir_len = struct.unpack_from('<I', pak_data, 8)[0]
    except struct.error:
        print("Error: Invalid or corrupt .pak header.", file=sys.stderr)
        return

    index = 0
    while index < dir_len:
        entry_offset = dir_off + index
        rel_path_bytes = struct.unpack_from('56s', pak_data, entry_offset)[0]
        file_info = {
            'path': rel_path_bytes.split(b'\x00')[0].decode('utf-8', errors='ignore').lower(),
            'pos': struct.unpack_from('<I', pak_data, entry_offset + 56)[0],
            'size': struct.unpack_from('<I', pak_data, entry_offset + 60)[0]
        }
        yield file_info
        index += 64


essential_pack_header = b'PACK'

def unpack_one_to_memory(pak_pathname, filename_glob):
    pak_path = Path(pak_pathname)
    if not pak_path.is_file():
        print(f"Error: Pak file not found at '{pak_path}'", file=sys.stderr)
        return None
    with open(pak_path, 'rb') as f:
        the_pak = f.read()
    if struct.unpack_from('4s', the_pak, 0)[0] != essential_pack_header:
        print(f"Error: '{pak_path}' is not a valid PACK file.", file=sys.stderr)
        return None
    for file_info in _iter_pak_directory(the_pak):
        if fnmatch.fnmatch(file_info['path'], filename_glob.lower()):
            pos = file_info['pos']
            size = file_info['size']
            return the_pak[pos:pos + size]
    print(f"Error: File matching '{filename_glob}' not found in archive.", file=sys.stderr)
    return None
