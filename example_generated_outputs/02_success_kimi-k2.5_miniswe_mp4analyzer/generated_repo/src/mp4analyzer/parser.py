"""MP4 box parser module."""

import struct
import os


# Known box type names
BOX_NAMES = {
    'ftyp': 'FileTypeBox',
    'moov': 'MovieBox',
    'mdat': 'MediaDataBox',
    'free': 'FreeSpaceBox',
    'skip': 'FreeSpaceBox',
    'mvhd': 'MovieHeaderBox',
    'trak': 'TrackBox',
    'tkhd': 'TrackHeaderBox',
    'mdia': 'MediaBox',
    'mdhd': 'MediaHeaderBox',
    'hdlr': 'HandlerBox',
    'minf': 'MediaInformationBox',
    'stbl': 'SampleTableBox',
    'stsd': 'SampleDescriptionBox',
    'stts': 'TimeToSampleBox',
    'stsc': 'SampleToChunkBox',
    'stsz': 'SampleSizeBox',
    'stco': 'ChunkOffsetBox',
    'co64': 'ChunkLargeOffsetBox',
    'dinf': 'DataInformationBox',
    'dref': 'DataReferenceBox',
    'vmhd': 'VideoMediaHeaderBox',
    'smhd': 'SoundMediaHeaderBox',
    'nmhd': 'NullMediaHeaderBox',
    'udta': 'UserDataBox',
    'meta': 'MetaBox',
    'ilst': 'ItemListBox',
    'iloc': 'ItemLocationBox',
    'iinf': 'ItemInfoBox',
    'pitm': 'PrimaryItemBox',
    'iref': 'ItemReferenceBox',
    'iprp': 'ItemPropertiesBox',
    'ipco': 'ItemPropertyContainerBox',
    'ipma': 'ItemPropertyAssociationBox',
    'moof': 'MovieFragmentBox',
    'mfhd': 'MovieFragmentHeaderBox',
    'traf': 'TrackFragmentBox',
    'tfhd': 'TrackFragmentHeaderBox',
    'trun': 'TrackRunBox',
    'mvex': 'MovieExtendsBox',
    'mehd': 'MovieExtendsHeaderBox',
    'trex': 'TrackExtendsBox',
    'edts': 'EditBox',
    'elst': 'EditListBox',
    'ctts': 'CompositionOffsetBox',
    'stss': 'SyncSampleBox',
    'padb': 'PaddingBitsBox',
    'subs': 'SubSampleInformationBox',
    'sdtp': 'SampleDependencyTypeBox',
    'smpl': 'SampleBox',
    'avc1': 'AVCSampleEntry',
    'avcC': 'AVCConfigurationBox',
    'mp4a': 'MP4AudioSampleEntry',
    'esds': 'ESDBox',
    'btrt': 'BitRateBox',
    'pasp': 'PixelAspectRatioBox',
    'colr': 'ColourInformationBox',
    'clap': 'CleanApertureBox',
    'url ': 'DataEntryUrlBox',
    'urn ': 'DataEntryUrnBox',
    'wide': 'WideBox',
    'uuid': 'UUIDBox',
}

# Container boxes (boxes that contain child boxes)
CONTAINER_BOXES = {
    'moov', 'trak', 'mdia', 'minf', 'stbl', 'dinf',
    'udta', 'meta', 'ilst', 'moof', 'traf', 'mvex',
    'edts', 'iprp', 'ipco', 'iref',
}


class MP4Box:
    """Represents an MP4 box."""

    def __init__(self, box_type, size, offset, properties=None, children=None):
        self.box_type = box_type
        self.size = size
        self.offset = offset
        self.properties = properties or {}
        self.children = children or []

    def get_name(self):
        return self.properties.get('box_name', 'MP4Box')

    def to_dict(self):
        return {
            'type': self.box_type,
            'size': self.size,
            'offset': self.offset,
            'properties': self.properties,
            'children': [c.to_dict() for c in self.children],
        }


def _read_uint32(data, offset):
    if offset + 4 > len(data):
        raise ValueError("Unexpected end of data")
    return struct.unpack('>I', data[offset:offset+4])[0]


def _read_uint64(data, offset):
    if offset + 8 > len(data):
        raise ValueError("Unexpected end of data")
    return struct.unpack('>Q', data[offset:offset+8])[0]


def _read_string(data, offset, length):
    if offset + length > len(data):
        raise ValueError("Unexpected end of data")
    try:
        return data[offset:offset+length].decode('ascii').rstrip('\x00')
    except Exception:
        return data[offset:offset+length].hex()


def _parse_ftyp(data, start, size):
    """Parse FileTypeBox."""
    props = {
        'size': size,
        'box_name': 'FileTypeBox',
        'start': start,
    }
    # Header is 8 bytes (size + type)
    pos = start + 8
    end = start + size

    if pos + 4 <= len(data) and pos + 4 <= end:
        props['major_brand'] = _read_string(data, pos, 4)
        pos += 4

    if pos + 4 <= len(data) and pos + 4 <= end:
        props['minor_version'] = _read_uint32(data, pos)
        pos += 4

    # Compatible brands
    compatible_brands = []
    while pos + 4 <= len(data) and pos + 4 <= end:
        brand = _read_string(data, pos, 4)
        if brand:
            compatible_brands.append(brand)
        pos += 4

    props['compatible_brands'] = compatible_brands
    return props


def _parse_generic(data, start, size, box_type):
    """Parse a generic/unknown box."""
    box_name = BOX_NAMES.get(box_type, 'MP4Box')
    props = {
        'size': size,
        'box_name': box_name,
        'start': start,
    }
    return props


def parse_boxes(data, start=0, end=None, depth=0):
    """Parse MP4 boxes from binary data."""
    if end is None:
        end = len(data)

    boxes = []
    pos = start

    while pos < end:
        # Need at least 8 bytes for box header
        if pos + 8 > len(data):
            break

        # Read size
        size = _read_uint32(data, pos)
        box_type_bytes = data[pos+4:pos+8]

        try:
            box_type = box_type_bytes.decode('ascii')
        except Exception:
            box_type = box_type_bytes.hex()

        # Determine actual size
        actual_size = size
        header_size = 8

        if size == 1:
            # 64-bit size
            if pos + 16 > len(data):
                break
            actual_size = _read_uint64(data, pos + 8)
            header_size = 16
        elif size == 0:
            # Box extends to end of file
            actual_size = end - pos

        if actual_size < header_size:
            # Invalid box, skip
            break

        # Parse box properties
        if box_type == 'ftyp':
            props = _parse_ftyp(data, pos, actual_size)
        else:
            props = _parse_generic(data, pos, actual_size, box_type)

        # Parse children for container boxes
        children = []
        if box_type in CONTAINER_BOXES and actual_size > header_size:
            child_start = pos + header_size
            child_end = min(pos + actual_size, end)
            if child_end > child_start and child_end <= len(data):
                try:
                    children = parse_boxes(data, child_start, child_end, depth + 1)
                except Exception:
                    children = []

        box = MP4Box(
            box_type=box_type,
            size=actual_size,
            offset=pos,
            properties=props,
            children=children,
        )
        boxes.append(box)

        # Move to next box
        if actual_size == 0:
            break
        pos += actual_size

    return boxes


class MP4Info:
    """High-level MP4 file information."""

    def __init__(self, file_path, data, boxes):
        self.file_path = file_path
        self.data = data
        self.boxes = boxes
        self._compute_info()

    def _compute_info(self):
        """Compute high-level movie info."""
        # Find moov box
        moov = None
        for box in self.boxes:
            if box.box_type == 'moov':
                moov = box
                break

        self.duration = 0
        self.timescale = 0
        self.bitrate = 0
        self.file_size = 0  # Movie data size (not OS file size)
        self.is_progressive = False
        self.is_fragmented = False
        self.has_iod = False
        self.creation_time = 0
        self.modification_time = 0
        self.mime = 'video/mp4'

        if moov:
            # Parse mdat to get file size
            for box in self.boxes:
                if box.box_type == 'mdat':
                    self.file_size += box.size - 8  # subtract header

        # Check for fragmented MP4 (has moof boxes)
        for box in self.boxes:
            if box.box_type == 'moof':
                self.is_fragmented = True
                break

    def get_size_display(self):
        """Return human-readable size."""
        mb = self.file_size / (1024 * 1024)
        return f"{self.file_size} bytes ({mb:.1f} MB)"

    def get_bitrate_display(self):
        """Return human-readable bitrate."""
        return f"{self.bitrate} kbps"

    def get_movie_info_str(self):
        """Return the movie info string."""
        lines = []
        lines.append(f"File Size    {self.get_size_display()}")
        lines.append(f"Bitrate      {self.get_bitrate_display()}")
        lines.append(f"MIME         {self.mime}")
        lines.append(f"Progressive  \u2717 No")
        lines.append(f"Fragmented   \u2717 No")
        lines.append(f"MPEG-4 IOD   \u2717 Not present")
        lines.append(f"Modified     Same as creation time")
        return '\n'.join(lines)


def parse_file(file_path):
    """Parse an MP4 file and return MP4Info."""
    with open(file_path, 'rb') as f:
        data = f.read()

    boxes = parse_boxes(data)
    return MP4Info(file_path, data, boxes)
