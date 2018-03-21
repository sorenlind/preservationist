# coding: utf8
"""Functions for finding albums with messy artwork."""
import csv
import io
import logging
import os
from enum import Enum
from pathlib import Path

import mutagen
from mutagen.mp4 import AtomDataType
from PIL import Image
from tqdm import tqdm

IMAGE_SIZES = [(600, 600), (1400, 1400)]

logger = logging.getLogger(__name__)


class Album(object):
    """Simple album data class."""

    def __init__(self, artist_name, album_name):
        self.artist_name = artist_name
        self.album_name = album_name
        self.songs = []
        self._purchased_by = None

    def __str__(self):
        return "{artist_name:35}| {album_name:50}| {purchased_by:20}| {message:25}| {size:1}".format(
            artist_name=self.artist_name,
            album_name=self.album_name,
            purchased_by=", ".join(self.purchased_by),
            message=self.status_message,
            size=self.size_message)

    def add_song(self, song):
        self.songs.append(song)

    @property
    def purchased_by(self):
        if self._purchased_by is None:
            self._purchased_by = set(song.purchased_by for song in self.songs if song.purchased_by is not None)
        return self._purchased_by

    @property
    def status_message(self):
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

        if any((song.covers[0].width, song.covers[0].height) not in IMAGE_SIZES for song in self.songs):
            return "Bad artwork size"

        return ""

    @property
    def size_message(self):
        sizes = set(f"{song.covers[0].width}x{song.covers[0].height}" for song in self.songs if len(song.covers))
        if not sizes:
            return ""

        if len(sizes) == 1:
            return list(sizes)[0]

        return "Mixed"


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


class Artwork(object):
    def __init__(self, image_format, contents, width, height):
        self.image_format = image_format
        self.contents = contents
        self.width = width
        self.height = height


class ImageFormat(Enum):
    UNKNOWN = 0
    PNG = 1
    JPEG = 2


def diagnose(input_folder, output_file, verbose):
    """Find albums with messy artwork."""

    if output_file:
        with open(output_file, 'w') as csvfile:
            csvwriter = csv.writer(csvfile, delimiter=',', quoting=csv.QUOTE_MINIMAL)
            csvwriter.writerow(['artist', 'album', 'purchased_by', 'status_message', 'size'])
            for album in _parse_folder(input_folder):
                row = _album_to_row(album)
                csvwriter.writerow(row)
    else:
        for album in list(_parse_folder(input_folder)):
            if not album.status_message and not verbose:
                continue
            print(album)


def _album_to_row(album):
    return [
        album.artist_name, album.album_name, ", ".join(album.purchased_by), album.status_message, album.size_message
    ]


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
            logger.debug("unknown filetype: %s", file)
            continue

        song = _parse_song(subdir, file)
        album.add_song(song)

    return album


def _parse_song(subdir, file):
    path = os.path.join(subdir, file)

    try:
        audio = mutagen.File(path)
    except mutagen.mp3.HeaderNotFoundError as exception:
        logger.warning("Could not read '%s': %s", file, exception)
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
        image = Image.open(io.BytesIO(cover))
        cover = Artwork(image_format, cover.hex(), image.width, image.height)
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
    image = Image.open(io.BytesIO(cover.data))
    cover = Artwork(image_format, cover.data.hex(), image.width, image.height)
    return [cover]


def _parse_mime_type(mime_type):
    mime_type = mime_type.lower()
    if "jpeg" in mime_type:
        return ImageFormat.JPEG
    elif "png" in mime_type:
        return ImageFormat.PNG
    return ImageFormat.UNKNOWN
