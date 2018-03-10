# coding: utf8
"""Functions for finding albums with messy artwork."""
import os
import logging
from pathlib import Path
import mutagen
from mutagen.mp4 import AtomDataType


def diagnose(input_folder, recursive):
    """Find albums for with messy artwork."""
    logging.warning("not really implemented")

    for subdir, dirs, files in os.walk(input_folder):
        if dirs:
            continue

        covers_found = set()
        cover_formats_found = set()
        for file in sorted(files):
            path = os.path.join(subdir, file)
            audio = mutagen.File(path)
            has_cover = "covr" in audio.tags
            cover_format = "None"
            cover_count = 0
            if has_cover:
                covers = audio.tags["covr"]
                cover_count = len(covers)
                #cover_format = AtomDataType(covers[0].imageformat)
                cover_formats_found.add(covers[0].imageformat)
                covers_found.add(covers[0].hex())

            #print("-", file, ":", cover_count, "(", cover_format, ")", )

        artist_album = " - ".join(Path(subdir).parts[-2:])
        if not covers_found:
            print(artist_album, ": NO COVERS!")
        elif len(covers_found) == 1:
            # print(artist_album, ": ALL SONGS HAVE SAME ARTWORK")
            pass
        elif len(cover_formats_found) == 1:
            print(artist_album, ": MULTIPLE ARTWORK!")
        else:
            print(artist_album, ": MULTIPLE FORMATS!")
            print(cover_formats_found)