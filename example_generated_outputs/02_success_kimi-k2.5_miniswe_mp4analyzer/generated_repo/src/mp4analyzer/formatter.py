"""Output formatter module for MP4 analyzer."""

import os
import json


LINE_WIDTH = 60
SUMMARY_WIDTH = 40


def _format_header(filename):
    """Format the centered header line."""
    title = f"MP4 Analysis: {filename}"
    return title.center(LINE_WIDTH)


def _format_box_line(box, prefix, is_last, detailed=False, expand=False):
    """Format a single box line and its properties."""
    lines = []

    # Tree connector
    connector = "\u2514\u2500\u2500" if is_last else "\u251c\u2500\u2500"

    # Box name if known
    box_name = box.properties.get('box_name', '')
    has_name = box_name and box_name != 'MP4Box'

    size_str = f"{box.size:,}"
    if has_name:
        line = f"{prefix}{connector} {box.box_type} (size={size_str}, offset={box.offset}) [{box_name}]"
    else:
        line = f"{prefix}{connector} {box.box_type} (size={size_str}, offset={box.offset})"

    lines.append(line)

    # Detailed properties
    if detailed and box_name and box_name != 'MP4Box':
        # Vertical bar prefix for properties
        if is_last:
            prop_prefix = prefix + "      "
        else:
            prop_prefix = prefix + "\u2502     "

        # Get properties to display (skip internal ones)
        skip_keys = {'size', 'box_name', 'start'}
        props = box.properties

        if box.box_type == 'ftyp':
            if 'major_brand' in props:
                lines.append(f"{prop_prefix}major_brand: {props['major_brand']}")
            if 'minor_version' in props:
                lines.append(f"{prop_prefix}minor_version: {props['minor_version']}")
            if 'compatible_brands' in props:
                brands = props['compatible_brands']
                brands_str = '[' + ', '.join(brands) + ']'
                lines.append(f"{prop_prefix}compatible_brands: {brands_str}")

    return lines


def _format_boxes_tree(boxes, prefix="", detailed=False, expand=False):
    """Recursively format box tree."""
    lines = []
    for i, box in enumerate(boxes):
        is_last = (i == len(boxes) - 1)
        box_lines = _format_box_line(box, prefix, is_last, detailed=detailed, expand=expand)
        lines.extend(box_lines)

        # Handle children
        if box.children:
            if is_last:
                child_prefix = prefix + "    "
            else:
                child_prefix = prefix + "\u2502   "
            child_lines = _format_boxes_tree(
                box.children, child_prefix, detailed=detailed, expand=expand
            )
            lines.extend(child_lines)

    return lines


def format_analysis(mp4_info, filename, detailed=False, expand=False):
    """Format the full analysis output."""
    lines = []

    # Header
    lines.append(_format_header(filename))
    lines.append("=" * LINE_WIDTH)

    # Movie info
    lines.append(mp4_info.get_movie_info_str())

    # Box structure
    lines.append("")
    lines.append("Box Structure:")
    lines.append("-" * 30)

    # Box tree
    box_lines = _format_boxes_tree(mp4_info.boxes, detailed=detailed, expand=expand)
    lines.extend(box_lines)

    return '\n'.join(lines) + '\n'


def format_summary(mp4_info, filename):
    """Format the summary output."""
    lines = []

    # Header
    lines.append(f"MP4 Summary: {filename}")
    lines.append("=" * SUMMARY_WIDTH)

    # Compute total sizes
    def sum_sizes(boxes):
        total = 0
        for box in boxes:
            total += box.size
        return total

    def count_all(boxes):
        total = len(boxes)
        for box in boxes:
            total += count_all(box.children)
        return total

    def collect_types(boxes, counter=None):
        if counter is None:
            counter = {}
        for box in boxes:
            counter[box.box_type] = counter.get(box.box_type, 0) + 1
            collect_types(box.children, counter)
        return counter

    total_size = sum_sizes(mp4_info.boxes)
    top_level_count = len(mp4_info.boxes)
    total_count = count_all(mp4_info.boxes)
    type_counts = collect_types(mp4_info.boxes)

    lines.append(f"Total file size: {total_size:,} bytes")
    lines.append(f"Top-level boxes: {top_level_count}")
    lines.append(f"Total box count: {total_count}")
    lines.append("")
    lines.append("Box type counts:")

    for box_type, count in type_counts.items():
        lines.append(f"  {box_type}: {count}")

    return '\n'.join(lines) + '\n'


def build_json_data(mp4_info):
    """Build JSON data structure for output."""
    data = {
        'file_path': mp4_info.file_path,
        'movie_info': mp4_info.get_movie_info_str(),
        'boxes': [box.to_dict() for box in mp4_info.boxes],
    }
    return data


def save_json_output(mp4_info, output_path):
    """Save JSON output to file."""
    data = build_json_data(mp4_info)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
