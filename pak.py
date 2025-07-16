#i 	int
#c 	char

import sys
import struct
import os
from pathlib import Path
import fnmatch

"""
.pak File Header Structure:
id	    4 byte string	Should be "PACK" (not null-terminated).
offset	Integer (4 bytes)	Index to the beginning of the file table.
size	Integer (4 bytes)	Size of the file table.

The number of files stored in the .pak file can be determined by dividing the "size"
value in the header by 64 (the size of each file entry struct).
"""

def _iter_pak_directory(pak_data):
    """A generator that yields file information from the PAK directory."""
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


def unpack_one_to_memory(pak_pathname, filename_glob):
    """
    Finds a single file in a .pak archive and returns its content as a bytes object.
    
    This is the core function for in-memory extraction.
    """
    pak_path = Path(pak_pathname)
    if not pak_path.is_file():
        print(f"Error: Pak file not found at '{pak_path}'", file=sys.stderr)
        return None

    with open(pak_path, 'rb') as f:
        the_pak = f.read()

    # Verify the "PACK" identifier
    if struct.unpack_from('4s', the_pak, 0)[0] != b'PACK':
        print(f"Error: '{pak_path}' is not a valid PACK file.", file=sys.stderr)
        return None

    for file_info in _iter_pak_directory(the_pak):
        if fnmatch.fnmatch(file_info['path'], filename_glob.lower()):
            print(f"Found file in archive: {file_info['path']}", file=sys.stderr)
            pos = file_info['pos']
            size = file_info['size']
            return the_pak[pos:pos + size]
    
    print(f"Error: File matching '{filename_glob}' not found in archive.", file=sys.stderr)
    return None


def create_pak(data_in_dir, pak_out):
    """Packs a directory of files into a .pak archive."""
    data_in_path = Path(data_in_dir)
    file_address_book = []
    tsize = 0
    fpos = 12  # Header size

    for root, _, files in os.walk(data_in_path):
        for f in files:
            full_path = Path(root) / f
            fpath_rel = full_path.relative_to(data_in_path).as_posix()
            fsize = full_path.stat().st_size
            file_address_book.append({
                "path_rel": fpath_rel.lower(),
                "path_abs": full_path, "size": fsize, "pos": fpos
            })
            fpos += fsize
            tsize += fsize

    print(f"Total files = {len(file_address_book)}", file=sys.stderr)
    print(f"Total filesize = {tsize}", file=sys.stderr)

    header_size = 12
    dir_offset = tsize + header_size
    dir_len = len(file_address_book) * 64
    mypakfile = bytearray(header_size + tsize + dir_len)

    struct.pack_into('4s', mypakfile, 0, b'PACK')
    struct.pack_into('<I', mypakfile, 4, dir_offset)
    struct.pack_into('<I', mypakfile, 8, dir_len)

    for entry in file_address_book:
        with open(entry["path_abs"], 'rb') as f:
            mypakfile[entry["pos"]:entry["pos"] + entry["size"]] = f.read()

    for i, entry in enumerate(file_address_book):
        entry_offset = dir_offset + (i * 64)
        struct.pack_into('56s', mypakfile, entry_offset, entry["path_rel"].encode('utf-8'))
        struct.pack_into('<I', mypakfile, entry_offset + 56, entry["pos"])
        struct.pack_into('<I', mypakfile, entry_offset + 60, entry["size"])

    with open(pak_out, 'wb') as f:
        print(f"Writing out {pak_out}", file=sys.stderr)
        f.write(mypakfile)


def unpack_pak(pak_file, unpack_loc, files_to_unpack=None):
    """
    Unpacks files from a .pak archive. If files_to_unpack is provided,
    only those files (matching glob patterns) will be extracted.
    """
    pak_path = Path(pak_file).resolve()
    unpack_location = Path(unpack_loc)

    with open(pak_path, 'rb') as f:
        the_pak = f.read()

    for file_info in _iter_pak_directory(the_pak):
        if files_to_unpack and not any(fnmatch.fnmatch(file_info['path'], p.lower()) for p in files_to_unpack):
            continue

        full_path = unpack_location / file_info['path']
        full_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"Unpacking: {full_path}", file=sys.stderr)
        try:
            with open(full_path, 'wb') as f:
                pos, size = file_info['pos'], file_info['size']
                f.write(the_pak[pos:pos + size])
        except IOError as e:
            print(f"Error writing file {full_path}: {e}", file=sys.stderr)
            sys.exit(1)


def main():
    """Main command-line interface handler."""
    args = sys.argv
    if len(args) < 3:
        print("PakTool - A utility for packing and unpacking .pak files.", file=sys.stderr)
        print("\nUsage:", file=sys.stderr)
        print("  To pack a directory:", file=sys.stderr)
        print(f"    python {args[0]} pack <input_folder> <output_pak_file>", file=sys.stderr)
        print("\n  To unpack all files from an archive:", file=sys.stderr)
        print(f"    python {args[0]} unpack <input_pak_file> <output_folder>", file=sys.stderr)
        print("\n  To unpack specific files matching patterns:", file=sys.stderr)
        print(f"    python {args[0]} unpack_one <input_pak_file> <output_folder> [file_pattern1] [pattern2] ...", file=sys.stderr)
        print("\n  To show a single file's content in the console (unpack to memory):", file=sys.stderr)
        print(f"    python {args[0]} show <input_pak_file> <filename_in_pak>", file=sys.stderr)
        sys.exit(1)

    command = args[1]
    
    if command == "pack" and len(args) == 4:
        create_pak(args[2], args[3])
    elif command == "unpack" and len(args) == 4:
        unpack_pak(args[2], args[3])
    elif command == "unpack_one" and len(args) >= 5:
        unpack_pak(args[2], args[3], files_to_unpack=args[4:])
    elif command == "show" and len(args) == 4:
        file_content = unpack_one_to_memory(args[2], args[3])
        if file_content:
            # Write binary data directly to standard output
            sys.stdout.buffer.write(file_content)
    else:
        print(f"Error: Invalid command or arguments for '{command}'.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()