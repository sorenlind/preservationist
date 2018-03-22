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

MIXED = "[Mixed]"


class Album(object):
    """Simple album data class."""

    def __init__(self, artist_folder, album_folder):
        self.artist_folder = artist_folder
        self.album_folder = album_folder
        self.songs = []
        self.erroneous = []
        self._purchased_by = None

    def __str__(self):
        return "{artist_folder:35}| {album_folder:50}| {purchased_by:20}| {artwork_message:25}| {size:9}| {sort_album:1}".format(
            artist_folder=self.artist_folder,
            album_folder=self.album_folder,
            purchased_by=", ".join(self.purchased_by),
            artwork_message=self.artwork_message,
            size=self.artwork_size,
            sort_album=self.sort_album)

    def __len__(self):
        return len(self.songs)

    def add(self, song):
        if song.error:
            self.erroneous.append(song)
        else:
            self.songs.append(song)

    @property
    def purchased_by(self):
        if self._purchased_by is None:
            self._purchased_by = set(song.purchased_by for song in self.songs if song.purchased_by is not None)
        return self._purchased_by

    @property
    def file_message(self):
        if not self.songs and all(_is_video(song.file_type) for song in self.erroneous):
            return ""

        if self.erroneous:
            return ", ".join(sorted(set(song.error for song in self.erroneous)))

        if not self.songs:
            return "Empty album"

        if self.file_type == MIXED:
            return "Mixed file type: " + _unique_values(self.songs, lambda x: x.file_type)

        return ""

    @property
    def artwork_message(self):
        if not self.songs:
            return ""

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
    def artwork_size(self):
        sizes = set(f"{song.covers[0].width}x{song.covers[0].height}" for song in self.songs if len(song.covers))
        if not sizes:
            return ""

        if len(sizes) == 1:
            return list(sizes)[0]

        return MIXED

    @property
    def naming_message(self):
        if not self.songs:
            return ""

        if self.compilation == MIXED:
            return "Some set as compilation"

        if self.compilation == "True" and self.album_artist != "Various Artists":
            return "Unexpected album artist for compilation: " + _unique_values(self.songs, lambda x: x.album_artist)

        if self.compilation == "True" and len(self) > 1 and self.artist != MIXED:
            return "Expected multiple artists for compilation"

        if self.compilation == "False" and self.album_artist == "Various Artists":
            return "Unexpected album artist for non-compilation"

        album_artist_lower = _unique_value_or_mixed(
            [song.album_artist.lower() if song.album_artist else None for song in self.songs])
        if self.album_artist == MIXED and album_artist_lower != MIXED:
            return "Artist differs by case only: " + _unique_values(self.songs, lambda x: x.album_artist)

        artist_lower = _unique_value_or_mixed([song.artist.lower() if song.artist else None for song in self.songs])
        if self.artist == MIXED and artist_lower != MIXED:
            return "Album artist differs by case only: " + _unique_values(self.songs, lambda x: x.artist)

        # It's okay to have mixed artists if it's fx "Placebo feat. David Bowie" for a Placebo album.
        # Mixed artists are also okay if each artist is part of the album artist as in "Mark Lanegan & Karen Dalton"
        # But other wise different artists we will make a warning.
        if self.compilation == "False" and self.artist == MIXED:
            album_artist = self.album_artist
            if all(song.artist.startswith(album_artist) for song in self.songs):
                pass
                # return "this is ok (startswith): " + _unique_values(self.songs, lambda x: x.artist)
            elif all(song.artist in album_artist for song in self.songs):
                pass
                # return "this is ok (in album_artist): " + _unique_values(self.songs, lambda x: x.artist)
            else:
                return "Expected single artist for non-compilation: " + _unique_values(self.songs, lambda x: x.artist)

        if self.name == MIXED:
            return "Mixed album: " + _unique_values(self.songs, lambda x: x.album)

        if self.sort_album == MIXED:
            return "Mixed sort album: " + _unique_values(self.songs, lambda x: x.sort_album)

        if self.album_artist == MIXED:
            return "Mixed album artist: " + _unique_values(self.songs, lambda x: x.album_artist)

        if self.sort_album_artist == MIXED:
            return "Mixed sort album artist: " + _unique_values(self.songs, lambda x: x.sort_album_artist)

        if not self.album_artist:
            return "No album artist"

        return ""

    @property
    def album_artist(self):
        return _unique_value_or_mixed([song.album_artist for song in self.songs])

    @property
    def artist(self):
        return _unique_value_or_mixed([song.artist for song in self.songs])

    @property
    def name(self):
        return _unique_value_or_mixed([song.album for song in self.songs])

    @property
    def sort_album_artist(self):
        return _unique_value_or_mixed([song.sort_album_artist for song in self.songs])

    @property
    def sort_artist(self):
        return _unique_value_or_mixed([song.sort_artist for song in self.songs])

    @property
    def sort_album(self):
        return _unique_value_or_mixed([song.sort_album for song in self.songs])

    @property
    def compilation(self):
        temp = _unique_value_or_mixed([str(song.compilation) for song in self.songs])
        if temp == "":
            return "False"
        return temp

    @property
    def file_type(self):
        return _unique_value_or_mixed([song.file_type for song in self.songs + self.erroneous])


def _is_video(file_type):
    return file_type in ['.mov', '.m4v', '.mpeg', '.mpg', '.mp4']


def _unique_values(songs, getter, max_length=100):
    return ", ".join(sorted(set(getter(song) or "[None]" for song in songs)))[:max_length]


def _unique_value_or_mixed(values):
    temp = list(set(values))
    if not temp:
        return ""

    if len(temp) == 1:
        return temp[0] or ""

    return MIXED


class Song(object):
    """Simple song data class."""

    def __init__(self, file_name):
        self.file_name = file_name
        self._file_type = None
        self.purchased_by = None
        self.album_artist = None
        self.artist = None
        self.album = None
        self.sort_album_artist = None
        self.sort_artist = None
        self.sort_album = None
        self.compilation = False
        self.covers = []
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
            csvwriter.writerow([
                'artist_folder',
                'album_folder',
                'compilation',
                'album_artist',
                'artist',
                'album',
                'sort_album_artist',
                'sort_artist',
                'sort_album',
                'purchased_by',
                'file_type',
                'artwork_size',
                'status',
                'file_message',
                'artwork_message',
                'naming_message',
            ])
            for album in _parse_folder(input_folder):
                row = _album_to_row(album)
                csvwriter.writerow(row)
    else:
        for album in list(_parse_folder(input_folder)):
            if not album.artwork_message and album.sort_album != MIXED and not verbose:
                continue
            print(album)


def _album_to_row(album):
    return [
        album.artist_folder, album.album_folder, album.compilation, album.album_artist,
        album.artist, album.name, album.sort_album_artist, album.sort_artist, album.sort_album, ", ".join(
            album.purchased_by), album.file_type, album.artwork_size, "OK"
        if not (album.file_message or album.artwork_message or album.naming_message) else "", album.file_message,
        album.artwork_message, album.naming_message
    ]


def _parse_folder(input_folder):
    relevant_subdirs = _find_subfolders(input_folder)
    for subdir, files in tqdm(relevant_subdirs):
        album = _parse_album(subdir, files)
        yield album


def _find_subfolders(input_folder):
    relevant_subdirs = []
    for subdir, dirs, files in sorted(os.walk(input_folder)):
        if ".itlp" in subdir:
            continue  # ignore iTunes LP

        if [dir_ for dir_ in dirs if ".itlp" not in dir_]:
            # We ignore folders with subdirs except if the subdir is an iTunes LP
            continue

        relevant_subdirs.append((subdir, files))
    return relevant_subdirs


def _parse_album(subdir, files):
    artist_name, album_name = Path(subdir).absolute().parts[-2:]
    album = Album(artist_name, album_name)

    for file in sorted(files):
        if file.startswith("."):
            continue  # ignore hidden files

        suffix = Path(file).suffix.lower()
        if suffix in [".pdf"]:
            # PDF files appear in folders because they come with some iTunes downloads. We simply skip them.
            continue
        if suffix not in [".m4a", ".m4p", ".mp3"]:
            # Unsupported format. We do not try and read the file but we do add a 'song' representing the file. This
            # is to make sure we are made aware of unused files lying around
            song = Song(os.path.join(subdir, file))
            song.error = f"Unsupported file type: {song.file_type}"
            album.add(song)
            continue

        # File is in a supported format. We read the file and try to extract meta data.
        song = _parse_song(subdir, file)
        album.add(song)
        continue

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
    if "aART" in audio.tags:
        song.album_artist = audio.tags["aART"][0]
    if "\xa9ART" in audio.tags:
        song.artist = audio.tags["\xa9ART"][0]
    if "\xa9alb" in audio.tags:
        song.album = audio.tags["\xa9alb"][0]
    if "soaa" in audio.tags:
        song.sort_album_artist = audio.tags["soaa"][0]
    if "soar" in audio.tags:
        song.sort_artist = audio.tags["soar"][0]
    if "soal" in audio.tags:
        song.sort_album = audio.tags["soal"][0]
    if "cpil" in audio.tags:
        song.compilation = audio.tags["cpil"]

    if not song.album_artist and 'TPE2' in audio.tags:
        song.album_artist = str(audio.tags['TPE2'])
    if not song.artist and 'TOPE' in audio.tags:
        song.artist = str(audio.tags['TOPE'])
    if not song.artist and 'TPE1' in audio.tags:
        song.artist = str(audio.tags['TPE1'])
    if not song.album and 'TALB' in audio.tags:
        song.album = str(audio.tags['TALB'])

    if not song.sort_album_artist and 'TSO2' in audio.tags:
        song.sort_album_artist = str(audio.tags['TSO2'])
    if not song.sort_artist and 'TSOP' in audio.tags:
        song.sort_artist = str(audio.tags['TSOP'])
    if not song.sort_album and 'TSOA' in audio.tags:
        song.sort_album = str(audio.tags['TSOA'])

    if "TCMP" in audio.tags:
        song.compilation = bool(int(str(audio.tags['TCMP'])))

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
