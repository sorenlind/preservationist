# coding: utf8
"""Functions for finding albums with messy artwork."""
from enum import Enum
import csv
import logging
import os
from pathlib import Path

import mutagen
from mutagen.mp4 import AtomDataType
from tqdm import tqdm


class Album(object):
    """Simple album data class."""

    def __init__(self, artist_name, album_name):
        self.artist_name = artist_name
        self.album_name = album_name
        self.songs = []
        self._artwork_ok = None
        self._purchased_by = None

    def __str__(self):
        return "{artist_name:35}| {album_name:50}| {artwork_ok:3}| {purchased_by:20}| {message:1}".format(
            artist_name=self.artist_name,
            album_name=self.album_name,
            artwork_ok="OK" if self.artwork_ok else "",
            purchased_by=", ".join(self.purchased_by),
            message=self.status_message)

    def add_song(self, song):
        self.songs.append(song)

    @property
    def artwork_ok(self):
        if self._artwork_ok is None:
            self._artwork_ok = all(song.artwork_ok for song in self.songs)
        return self._artwork_ok

    @property
    def purchased_by(self):
        if self._purchased_by is None:
            self._purchased_by = set(song.purchased_by for song in self.songs if song.purchased_by is not None)
        return self._purchased_by

    @property
    def status_message(self):
        #if self.artwork_ok:
        #    return ""

        if all(not song.has_cover for song in self.songs):
            return "No artwork"

        if not all(song.has_cover for song in self.songs):
            return "Some artwork missing"

        if not all(len(song.covers) == 1 for song in self.songs):
            return "Multiple covers per file"

        if len(set(song.covers[0].contents for song in self.songs)) > 1:
            return "Multiple covers"

        if len(set(song.covers[0].image_format for song in self.songs)) > 1:
            return "Multiple image formats"

        if any(song for song in self.songs if song.covers[0].image_format == ImageFormat.PNG):
            return "PNG artwork"

        if any(song for song in self.songs if song.covers[0].image_format == ImageFormat.UNKNOWN):
            return "Unknown artwork format"

        #artwork_types = [song. for song in self.songs]
        
        return ""


# NO_ARTWORK = "No artwork"
# ARTWORK_OK = "OK"
# SOME_MISSING = "Some artwork missing"
# ARTWORK_TYPE_PNG = "PNG image type"
# ARTWORK_TYPE_JPEG = "JPEG"
# ARTWORK_TYPE_UNKOWN = "Unknown image type"
# ARTWORK_TYPE_MULTIPLE = "Multiple image types"
# ARTWORK_COVER_MULTIPLE = "Multiple covers"
# MULTIPLE_ARTWORK_IN_FILE = "Multiple covers in single file"
# COVER_JPEG = "JPEG"
# COVER_PNG = "PNG"
# COVER_UNKOWN = "UNKNOWN"

# # ------
# if result == ARTWORK_OK and not verbose:
#     continue

# if not covers_found:
#     return NO_ARTWORK
# elif missing_covers:
#     return SOME_MISSING
# elif len(set(covers_found)) == 1:
#     artwork_type = cover_formats_found[0]
#     if artwork_type == COVER_JPEG:
#         return ARTWORK_OK
#     elif artwork_type == COVER_PNG:
#         return ARTWORK_TYPE_PNG
#     else:
#         return ARTWORK_TYPE_UNKOWN
# elif len(set(cover_formats_found)) == 1:
#     return ARTWORK_COVER_MULTIPLE
# else:
#     return ARTWORK_TYPE_MULTIPLE


class Song(object):
    """Simple song data class."""

    def __init__(self, file_name):
        self.file_name = file_name
        self._file_type = None
        self.purchased_by = None
        self.covers = []
        self.valid_audio_file = False
        self.error = None

    @property
    def file_type(self):
        """Return the file type, fx '.mp3'. or '.m4a'"""
        if not self._file_type:
            self._file_type = Path(self.file_name).suffix
        return self._file_type

    @property
    def purchased(self):
        """Return a value indicating whether the song was purchased in the iTunes store."""
        return bool(self.purchased_by)

    @property
    def has_cover(self):
        """Return a value indicating whether the song has a cover."""
        return bool(self.covers)

    @property
    def is_valid_audio(self):
        """Return a value indicating whether mutagen could load the file."""
        return self.error is None

    @property
    def artwork_ok(self):
        return self.is_valid_audio and len(self.covers) == 1 and self.covers[0].ok


class Artwork(object):
    def __init__(self, image_format, contents):
        self.image_format = image_format
        self.contents = contents

    def ok(self):
        # TODO: Also check image dimensions / resolution
        return self.image_format == ImageFormat.JPEG


class ImageFormat(Enum):
    UNKNOWN = 0
    PNG = 1
    JPEG = 2


def diagnose(input_folder, output_file, verbose):
    """Find albums with messy artwork."""

    if output_file:
        with open(output_file, 'w') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            csvwriter.writerow(['artist', 'album', 'result'])
            for album in _parse_folder(input_folder):
                row = _album_to_row(album)
                csvwriter.writerow(row)
    else:
        for album in list(_parse_folder(input_folder)):
            if album.artwork_ok and not verbose:
                continue
            print(album)


def _album_to_row(album):
    return [album.artist_name, album.album_name, album.ok]


def _parse_folder(input_folder):
    for subdir, dirs, files in tqdm(sorted(os.walk(input_folder))):
        if ".itlp" in subdir:
            continue  # ignore iTunes LP

        if [dir_ for dir_ in dirs if ".itlp" not in dir_]:
            # We ignore folders with subdirs except if the subdir is an iTunes LP
            continue

        album = _parse_album(subdir, files)
        yield album


def _parse_album(subdir, files):
    artist_name, album_name = Path(subdir).absolute().parts[-2:]
    album = Album(artist_name, album_name)

    for file in sorted(files):
        if file.startswith("."):
            continue  # ignore hidden files

        suffix = Path(file).suffix.lower()
        if suffix in [".mpg", ".mpeg", ".pdf", ".m4v", ".mov", ".mp4"]:
            continue

        if suffix not in [".m4a", ".m4p", ".mp3"]:
            logging.debug("unknown filetype: %s", file)
            continue

        song = _parse_song(subdir, file)
        album.add_song(song)

    return album


def _parse_song(subdir, file):
    path = os.path.join(subdir, file)

    try:
        audio = mutagen.File(path)
    except Exception as exception:
        logging.warning("Could not read '%s': %s", file, exception)
        song = Song(file)
        song.error = str(exception)
        return song

    assert audio is not None

    song = Song(file)
    if "covr" in audio.tags:
        song.covers = _parse_covr_tag(audio)
    elif 'APIC:' in audio.tags:
        song.covers = _parse_apic_tag(audio)

    if 'apID' in audio.tags:
        assert len(audio.tags['apID']) == 1
        song.purchased_by = audio.tags['apID'][0]
    return song


def _parse_covr_tag(audio):
    covers = []
    for cover in audio.tags["covr"]:
        image_format = _atom_to_enum(AtomDataType(cover.imageformat))
        cover = Artwork(image_format, cover.hex())
        covers.append(cover)
    return covers


def _atom_to_enum(atom_data_type):
    if atom_data_type == AtomDataType.JPEG:
        return ImageFormat.JPEG
    elif atom_data_type == AtomDataType.PNG:
        return ImageFormat.PNG
    return ImageFormat.UNKNOWN


def _parse_apic_tag(audio):
    cover = audio.tags['APIC:']
    image_format = _parse_mime_type(cover.mime)
    cover = Artwork(image_format, cover.data.hex())
    return [cover]


def _parse_mime_type(mime_type):
    mime_type = mime_type.lower()
    if "jpeg" in mime_type:
        return ImageFormat.JPEG
    elif "png" in mime_type:
        return ImageFormat.PNG
    return ImageFormat.UNKNOWN


# NO_ARTWORK = "No artwork"
# ARTWORK_OK = "OK"
# SOME_MISSING = "Some artwork missing"
# ARTWORK_TYPE_PNG = "PNG image type"
# ARTWORK_TYPE_JPEG = "JPEG"
# ARTWORK_TYPE_UNKOWN = "Unknown image type"
# ARTWORK_TYPE_MULTIPLE = "Multiple image types"
# ARTWORK_COVER_MULTIPLE = "Multiple covers"
# MULTIPLE_ARTWORK_IN_FILE = "Multiple covers in single file"
# COVER_JPEG = "JPEG"
# COVER_PNG = "PNG"
# COVER_UNKOWN = "UNKNOWN"

# # ------
# if result == ARTWORK_OK and not verbose:
#     continue

# if not covers_found:
#     return NO_ARTWORK
# elif missing_covers:
#     return SOME_MISSING
# elif len(set(covers_found)) == 1:
#     artwork_type = cover_formats_found[0]
#     if artwork_type == COVER_JPEG:
#         return ARTWORK_OK
#     elif artwork_type == COVER_PNG:
#         return ARTWORK_TYPE_PNG
#     else:
#         return ARTWORK_TYPE_UNKOWN
# elif len(set(cover_formats_found)) == 1:
#     return ARTWORK_COVER_MULTIPLE
# else:
#     return ARTWORK_TYPE_MULTIPLE
