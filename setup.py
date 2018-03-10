"""Setup script for package."""
import re
from setuptools import setup, find_packages

VERSION = re.search(r'^VERSION\s*=\s*"(.*)"', open("preservationist/version.py").read(), re.M).group(1)
with open("README.md", "rb") as f:
    LONG_DESCRIPTION = f.read().decode("utf-8")

setup(
    name="preservationist",
    version=VERSION,
    description="Package used for finding audio files with messy artwork.",
    long_description=LONG_DESCRIPTION,
    author="Soren Lind Kristiansen",
    author_email="soren@gutsandglory.dk",
    url="https://github.com/sorenlind/preservationist/",
    keywords="audio itunes artwork",
    packages=find_packages(),
    install_requires=['mutagen', 'tqdm'],
    extras_require={
        'notebooks': ['jupyter'],
        'dev': ['jupyter', 'pylint', 'pycodestyle', 'pydocstyle', 'yapf', 'pytest', 'tox', 'rope'],
        'test': ['pytest', 'tox'],

    },
    setup_requires=['pytest-runner'],
    tests_require=['pytest'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3.6',
    ],
    entry_points={
        "console_scripts": [
            "preserve = preservationist.entry_points.preserve:main",
        ],
    })
