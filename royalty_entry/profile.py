"""Window-relative regions observed during the user's demonstration.

Coordinates describe the canonical reference image. Runtime toolbar matching
maps that image to the current Remote Desktop scale and position.
"""
import json
from pathlib import Path

DEFAULT = {
    'version': 1, 'window_title': 'byumg-remote.byu.edu - Remote Desktop Connection',
    'window_size': [1907, 1032], 'settle_seconds': 1.2,
    'regions': {
        'manager_title': [450, 128, 620, 150],
        'search_value': [554, 232, 820, 252],
        'search_count': [550, 340, 1100, 362],
        'result_licenses': [470, 382, 625, 936],
        'result_publishers': [1005, 382, 1257, 936],
        'result_publisher_numbers': [1261, 382, 1338, 936],
        'properties_title': [678, 222, 1225, 245],
        'general_publisher': [817, 347, 1182, 367],
        'general_license': [795, 373, 1182, 392],
        'details_label': [696, 309, 796, 333],
        'details_balance': [806, 311, 913, 332],
        'financials_title': [496, 221, 1220, 244],
        'financials_types': [689, 279, 926, 824],
        'financials_amounts': [1179, 279, 1239, 824],
        'financials_balance': [896, 850, 952, 871],
        'entry_title': [788, 408, 1005, 430],
        'entry_type': [895, 512, 1100, 531],
        'entry_amount': [875, 560, 983, 579],
        'entry_reference': [875, 584, 1120, 603],
        'chooser_title': [699, 244, 1000, 266],
        'chooser_names': [694, 318, 919, 401],
    },
    'points': {
        'search_input': [652, 242], 'search_button': [899, 241],
        'result_focus': [521, 391], 'details_tab': [752, 262],
        'financials_button': [973, 297], 'properties_ok': [1123, 861],
        'financials_focus': [802, 288], 'financials_add': [1394, 270],
        'financials_ok': [1325, 900], 'type_button': [1111, 522],
        'chooser_ok': [1126, 875], 'entry_amount': [924, 570],
        'entry_reference': [984, 594], 'entry_ok': [933, 715],
    },
}


def load_profile(path: Path):
    profile = json.loads(path.read_text(encoding='utf-8')) if path.exists() else json.loads(json.dumps(DEFAULT))
    if profile.get('version') != 1:
        raise ValueError('Unsupported calibration profile')
    profile.setdefault('regions', {}).setdefault('result_publisher_numbers',
        list(DEFAULT['regions']['result_publisher_numbers']))
    for section in ('regions', 'points'):
        if set(DEFAULT[section]) - set(profile.get(section, {})):
            raise ValueError('Calibration profile is incomplete')
        for value in profile[section].values():
            expected = 4 if section == 'regions' else 2
            if len(value) != expected or not all(isinstance(x, int) for x in value):
                raise ValueError('Calibration coordinates must be integers')
            w, h = profile['window_size']
            if not all(0 <= x <= (w if i % 2 == 0 else h) for i, x in enumerate(value)):
                raise ValueError('Calibration coordinates lie outside the Remote Desktop window')
            if expected == 4 and (value[2] <= value[0] or value[3] <= value[1]):
                raise ValueError('Calibration rectangle has no area')
    return profile
