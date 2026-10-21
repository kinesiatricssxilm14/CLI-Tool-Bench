"""CLI entry point for mp4analyzer."""

import sys
import os
import argparse

from .parser import parse_file
from .formatter import format_analysis, format_summary, save_json_output


def main():
    parser = argparse.ArgumentParser(
        prog='mp4analyzer',
        description='Analyze MP4 files',
    )

    parser.add_argument(
        'file',
        help='Path to the MP4 file to analyze',
    )
    parser.add_argument(
        '-d', '--detailed',
        action='store_true',
        default=False,
        help='Show detailed properties for each box',
    )
    parser.add_argument(
        '-s', '--summary',
        action='store_true',
        default=False,
        help='Show concise summary instead of full analysis',
    )
    parser.add_argument(
        '-e', '--expand',
        action='store_true',
        default=False,
        help='Expand arrays and large data structures',
    )
    parser.add_argument(
        '-o', '--output',
        metavar='FORMAT',
        help='Output format (e.g., json)',
    )
    parser.add_argument(
        '-j', '--json-path',
        metavar='PATH',
        help='Save JSON output to specified file path',
    )
    parser.add_argument(
        '--no-color',
        action='store_true',
        default=False,
        help='Disable colored output',
    )

    args = parser.parse_args()

    # Validate file exists
    if not os.path.exists(args.file):
        print(f"mp4analyzer: error: file not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(args.file):
        print(f"mp4analyzer: error: not a file: {args.file}", file=sys.stderr)
        sys.exit(1)

    # Parse the MP4 file
    try:
        mp4_info = parse_file(args.file)
    except Exception as e:
        print(f"mp4analyzer: error: failed to parse file: {e}", file=sys.stderr)
        sys.exit(1)

    filename = os.path.basename(args.file)
    stem = os.path.splitext(filename)[0]

    # Handle output format
    if args.output and args.output.lower() == 'json':
        # Save JSON to derived filename in CWD
        output_filename = stem + '.mp4analyzer.json'
        output_path = os.path.join(os.getcwd(), output_filename)
        try:
            save_json_output(mp4_info, output_path)
        except Exception as e:
            print(f"mp4analyzer: error: failed to write JSON: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"JSON output saved to: {output_filename}")
        sys.exit(0)

    # Handle summary mode
    if args.summary:
        output = format_summary(mp4_info, filename)
        sys.stdout.write(output)
        sys.exit(0)

    # Standard analysis output
    output = format_analysis(
        mp4_info,
        filename,
        detailed=args.detailed,
        expand=args.expand,
    )
    sys.stdout.write(output)

    # Handle json-path flag
    if args.json_path:
        try:
            save_json_output(mp4_info, args.json_path)
        except Exception as e:
            print(f"mp4analyzer: error: failed to write JSON: {e}", file=sys.stderr)
            sys.exit(1)
        print(f"JSON output saved to: {args.json_path}")

    sys.exit(0)


if __name__ == '__main__':
    main()
