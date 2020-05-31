import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

ISO_DATE_TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'


def _get_file_with_type(input, type_):
    for input_file in input:
        if input_file['type'] == type_:
            return input_file

    return None


def _date_from_long_unix_str(str_time):
    return datetime.utcfromtimestamp(str_time / 1000)


def _to_iso(str_time):
    dt = _date_from_long_unix_str(str_time)
    return time.strftime(ISO_DATE_TIME_FORMAT, dt.timetuple())


def _merge_tracks(tracks):
    result = {}
    for track in tracks:
        for row in track:
            if not row.get('start_time'):
                continue

            if row['start_time'] not in result:
                result[row['start_time']] = {}

            result[row['start_time']].update(row)

    return [result[key] for key in sorted(result.keys())]


EXERCISE_RE = re.compile('^((?:\w+-?)+)\.(.+)\.json$')
SUPPORTED_TYPES = {'live_data', 'location_data'}
MIN_RECORDS_COUNT = 100
MAX_FILES_PER_LOAD = 25

if len(sys.argv) < 2:
    print('Path argument missing')
    print('Usage: python3 samsung_json_to_gpx.py /path/to/unpacked/zip/')
    sys.exit(1)

base_path = sys.argv[1]
if not os.path.exists(base_path) or not os.path.isdir(base_path):
    print('Seems like directory "{}" does not exist'.format(base_path))
    sys.exit(2)

jsons_path = os.path.join(base_path, 'jsons/com.samsung.health.exercise/')
if not os.path.exists(jsons_path):
    print('Seems like directory is invalid. Missing directory with exercises at "{}"'.format(jsons_path))
    sys.exit(3)

files = sorted(os.scandir(path=jsons_path), key=lambda f: f.name)

exercises = defaultdict(lambda: [])
for f in files:
    match = EXERCISE_RE.match(f.name)
    if match and match.group(2) in SUPPORTED_TYPES:
        exercises[match.group(1)].append({
            'path': f.path,
            'type': match.group(2)
        })

converted_cnt = 0
small_cnt = 0
invalid_cnt = 0
for name, values in exercises.items():
    written = 0
    if not _get_file_with_type(values, 'location_data'):
        print('Skip track {}: missing location data'.format(name))
        invalid_cnt += 1
        continue

    if not os.path.exists('./output/'):
        os.mkdir('./output')

    sources = []
    for source in values:
        with open(source['path']) as src_file:
            sources.append(json.load(src_file))

    data = _merge_tracks(sources)
    if len(data) < MIN_RECORDS_COUNT:
        print('Empty or small track {}'.format(name))
        small_cnt += 1
        continue

    start_unix = data[0]['start_time']

    output_data = []
    output_data.extend([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx creator="DrA1exGPX" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v1 http://www.garmin.com/xmlschemas/TrackPointExtensionv1.xsd" version="1.1" xmlns="http://www.topografix.com/GPX/1/1" xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1" xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3">',
        '<metadata>',
        '<time>{}</time>'.format(_to_iso(start_unix)),
        '</metadata>',
        '<trk>',
        '<name>Ride at {}</name>'.format(time.strftime('%Y-%m-%d', _date_from_long_unix_str(start_unix).timetuple())),
        '<type>1</type>',
        '<trkseg>'
    ])

    for item in data:
        if not item.get('latitude') or not item.get('longitude'):
            continue

        output_data.extend([
            '<trkpt lat="{}" lon="{}">'.format(item['latitude'], item['longitude']),
            '<time>{}</time>`'.format(_to_iso(item['start_time']))
        ])

        if item.get('altitude'):
            output_data.append('<ele>{}</ele>'.format(item['altitude']))

        if item.get('heart_rate'):
            output_data.extend([
                '<extensions>',
                '<gpxtpx:TrackPointExtension>',
                '<gpxtpx:hr>{}</gpxtpx:hr>'.format(item['heart_rate']),
                '</gpxtpx:TrackPointExtension>',
                '</extensions>'
            ])

        output_data.append('</trkpt>')
        written += 1

    output_data.extend([
        '</trkseg>',
        '</trk>',
        '</gpx>'
    ])

    print('Save track {} with {} points'.format(name, written))
    out_dir = './output/{}'.format(converted_cnt // MAX_FILES_PER_LOAD)
    if not os.path.exists(out_dir):
        os.mkdir(out_dir)
    out_path = '{}/{}.gpx'.format(out_dir, name)
    with open(out_path, 'w+') as out:
        out.write('\n'.join(output_data))
    converted_cnt += 1

print('Done')
print('Converted: {}, Small: {}, Invalid: {}'.format(converted_cnt, small_cnt, invalid_cnt))
