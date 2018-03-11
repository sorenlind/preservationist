# coding: utf8
"""Functions for finding albums with messy artwork."""
import csv
import logging
import os
from pathlib import Path

import mutagen
from mutagen.mp4 import AtomDataType
from tqdm import tqdm

NO_ARTWORK = "No artwork"
ARTWORK_OK = "OK"
SOME_MISSING = "Some artwork missing"
ARTWORK_TYPE_PNG = "PNG image type"
# ARTWORK_TYPE_JPEG = "JPEG"
ARTWORK_TYPE_UNKOWN = "Unknown image type"
ARTWORK_TYPE_MULTIPLE = "Multiple image types"
ARTWORK_COVER_MULTIPLE = "Multiple covers"


def diagnose(input_folder, output_file, verbose):
    """Find albums with messy artwork."""

    results = _process_folder(input_folder, verbose)
    if output_file:
        with open(output_file, 'w') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            csvwriter.writerow(['artist', 'album', 'result'])
            for result in results:
                csvwriter.writerow(result)
    else:
        for artist, album, result in list(results):
            print("%s - %s : %s" % (artist, album, result))


def _process_folder(input_folder, verbose):
    for subdir, dirs, files in tqdm(list(os.walk(input_folder))):
        if ".itlp" in subdir:
            continue  # ignore iTunes LP

        if [dir_ for dir_ in dirs if ".itlp" not in dir_]:
            # We ignore folders with subdirs except if the subdir is an iTunes LP
            continue

        result = _process_album(subdir, files)
        if result == ARTWORK_OK and not verbose:
            continue

        artist, album = Path(subdir).parts[-2:]

        yield [artist, album, result]


def _process_album(subdir, files):
    covers_found = []
    cover_formats_found = []
    missing_covers = 0
    errors = False
    for file in sorted(files):
        if file.startswith("."):
            continue  # ignore hidden files

        suffix = Path(file).suffix.lower()
        if suffix in [".mpg", ".mpeg", ".pdf", ".m4v", ".mov", ".m4p", ".mp4"]:
            continue

        if suffix not in [".m4a", ".mp3"]:
            logging.debug("unknown filetype: %s", file)
            continue

        path = os.path.join(subdir, file)
        try:
            audio = mutagen.File(path)
        except Exception as exception:
            logging.warning("Could not read '%s': %s", file, exception)
            errors = True
            continue

        if not audio:
            # print("COULD NOT READ", " - ".join(Path(path).parts[-3:]))
            logging.warning("No audio in file '%s'", file)
            errors = True
            continue

        path = os.path.join(subdir, file)
        audio = mutagen.File(path)
        has_cover = "covr" in audio.tags
        if has_cover:
            covers = audio.tags["covr"]
            cover_formats_found.append(covers[0].imageformat)
            covers_found.append(covers[0].hex())
        else:
            missing_covers = True

    if not covers_found:
        return NO_ARTWORK
    elif missing_covers:
        return SOME_MISSING
    elif len(set(covers_found)) == 1:
        artwork_type = AtomDataType(cover_formats_found[0])
        if artwork_type == AtomDataType.JPEG:
            return ARTWORK_OK
        elif artwork_type == AtomDataType.PNG:
            return ARTWORK_TYPE_PNG
        else:
            return ARTWORK_TYPE_UNKOWN
    elif len(set(cover_formats_found)) == 1:
        return ARTWORK_COVER_MULTIPLE
    else:
        return ARTWORK_TYPE_MULTIPLE
