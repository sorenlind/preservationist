# -*- coding: utf-8 -*-
"""Preservationist."""

import argparse
import logging
from preservationist.version import VERSION
from preservationist.identification import diagnose

MAINPARSER_HELP = "print current version number"
SUBPARSERS_HELP = "%(prog)s must be called with a command:"

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.DEBUG)


def main():
    """Main function handling arguments."""
    _create_parser("Preservationist", VERSION, [_diagnose_parser])


def _create_parser(description, version, subparsers_funcs):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument(
        "-V", "--version", action="version", version="%(prog)s {}".format(version), help=MAINPARSER_HELP)

    subparsers = parser.add_subparsers(help=SUBPARSERS_HELP, dest='command')
    subparsers.required = True

    for subparsers_func in subparsers_funcs:
        subparsers_func(subparsers)

    args = parser.parse_args()
    args.func(parser, args)


def _diagnose_parser(subparsers):
    """Create parser for the 'diagnose' command."""
    parser = subparsers.add_parser("diagnose", help="find albums with messy artwork.")
    parser.add_argument('--input-folder', type=str, help='name of input folder', required=True)
    parser.add_argument('--output-file', type=str, help='name of output file', required=False)
    parser.add_argument(
        '--verbose', help='show status for all albums', default=False, action='store_true')
    parser.set_defaults(func=_diagnose)
    return parser


def _diagnose(_, args):
    """Find albums with messy artwork."""
    logging.info("finding albums with messy artwork.")
    diagnose(input_folder=args.input_folder, output_file=args.output_file, verbose=args.verbose)


if __name__ == "__main__":
    main()
