import argparse
import os
import sys

from . import dontorrent


SITES = {
    "dontorrent": dontorrent.main,
}


def print_help():
    print("usage: python -m arr_indexers [--site SITE] [site options]\n")
    print("Supported sites:")
    for site in sorted(SITES):
        print(f"  {site}")
    print("\nUse a site-specific help command for available options, for example:")
    print("  python -m arr_indexers --site dontorrent --help")


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv in (["--help"], ["-h"]):
        print_help()
        return

    parser = argparse.ArgumentParser(
        description="Run a Torznab proxy service for a supported indexer.",
        add_help=False,
    )
    parser.add_argument("--site", default=os.getenv("ARR_INDEXERS_SITE", "dontorrent"), choices=sorted(SITES))
    args, remaining = parser.parse_known_args()

    SITES[args.site](remaining)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
