"""Version-pinned CS2 schema extraction. No offsets are downloaded at runtime."""
from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
import re
import urllib.request

MAX_DOWNLOAD = 8 * 1024 * 1024
MODULES = ('dwEntityList', 'dwLocalPlayerPawn', 'dwLocalPlayerController',
           'dwViewMatrix', 'dwViewAngles', 'dwSensitivity', 'dwSensitivity_sensitivity')
FIELDS = {
    'health': ('C_BaseEntity', 'm_iHealth'),
    'team': ('C_BaseEntity', 'm_iTeamNum'),
    'scene': ('C_BaseEntity', 'm_pGameSceneNode'),
    'flags': ('C_BaseEntity', 'm_fFlags'),
    'velocity': ('C_BaseEntity', 'm_vecAbsVelocity'),
    'origin': ('CGameSceneNode', 'm_vecAbsOrigin'),
    'dormant': ('CGameSceneNode', 'm_bDormant'),
    'view_offset': ('C_BaseModelEntity', 'm_vecViewOffset'),
    'model_state': ('CSkeletonInstance', 'm_modelState'),
    'pawn_handle': ('CCSPlayerController', 'm_hPlayerPawn'),
    'name': ('CBasePlayerController', 'm_iszPlayerName'),
    'armor': ('C_CSPlayerPawn', 'm_ArmorValue'),
    'spotted_state': ('C_CSPlayerPawn', 'm_entitySpottedState'),
    'spotted_mask': ('EntitySpottedState_t', 'm_bSpottedByMask'),
    'crosshair': ('C_CSPlayerPawn', 'm_iIDEntIndex'),
    'observer_pawn': ('CCSPlayerController', 'm_hObserverPawn'),
    'observer_services': ('C_BasePlayerPawn', 'm_pObserverServices'),
    'observer_target': ('CPlayer_ObserverServices', 'm_hObserverTarget'),
}
# These are engine layout assumptions, not schema offsets. Entity stride is calibrated
# against the local pawn. Skeletons are omitted if positions fail spatial checks.
LAYOUT = {'chunk_offset': 0x10, 'chunk_size': 512, 'entry_strides': [0x70, 0x78],
          'handle_mask': 0x7FFF, 'bone_array': 0x80, 'bone_stride': 32,
          'controller_limit': 64}


@dataclass(frozen=True)
class Profile:
    modules: dict
    fields: dict
    layout: dict
    source: str


def bounded_int(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError('Invalid offset/profile layout value.')
    return value


def validate_profile(document):
    if not isinstance(document, dict) or type(document.get('version')) is not int or document.get('version') != 1:
        raise ValueError('Unsupported native offset profile.')
    modules, fields, layout = (document.get(key) for key in ('modules', 'fields', 'layout'))
    if not all(isinstance(x, dict) for x in (modules, fields, layout)):
        raise ValueError('Incomplete native offset profile.')
    modules = {key: bounded_int(modules.get(key), 1, 0x40000000) for key in MODULES}
    fields = {key: bounded_int(fields.get(key), 0, 0x100000) for key in FIELDS}
    if set(layout) != set(LAYOUT):
        raise ValueError('Incomplete engine layout.')
    # The reader currently supports this chunk/handle organization only.
    for key in ('chunk_offset', 'chunk_size', 'handle_mask', 'controller_limit'):
        if type(layout[key]) is not int or layout[key] != LAYOUT[key]:
            raise ValueError(f'Unsupported {key}.')
    strides = layout['entry_strides']
    if not isinstance(strides, list) or not 1 <= len(strides) <= 4:
        raise ValueError('Invalid entity strides.')
    strides = [bounded_int(s, 8, 1024) for s in strides]
    if len(set(strides)) != len(strides) or any(s % 8 for s in strides):
        raise ValueError('Entity strides must be unique and aligned.')
    layout = {**layout, 'entry_strides': strides,
              'bone_array': bounded_int(layout['bone_array'], 0, 4096),
              'bone_stride': bounded_int(layout['bone_stride'], 12, 256)}
    source = document.get('source')
    if not isinstance(source, str) or not re.fullmatch(r'[a-f0-9]{40}', source):
        raise ValueError('Profile must identify its cs2-dumper commit.')
    return Profile(modules, fields, layout, source)


def build_profile(offsets, schema, source):
    classes = schema['client.dll']['classes']
    fields = {key: classes[cls]['fields'][name] for key, (cls, name) in FIELDS.items()}
    document = {'version': 1, 'source': source, 'modules': {k: offsets['client.dll'][k] for k in MODULES},
                'fields': fields, 'layout': dict(LAYOUT)}
    validate_profile(document)
    return document


def load_profile(path):
    path = Path(path)
    if path.stat().st_size > MAX_DOWNLOAD:
        raise ValueError('Offset profile is too large.')
    return validate_profile(json.loads(path.read_text(encoding='utf-8')))


def github_json(path):
    request = urllib.request.Request('https://api.github.com/repos/a2x/cs2-dumper/' + path,
                                    headers={'User-Agent': 'Phantom-native-offset-tool',
                                             'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(MAX_DOWNLOAD + 1)
    if len(raw) > MAX_DOWNLOAD:
        raise ValueError('GitHub response exceeds size limit.')
    return json.loads(raw)


def download_profile(ref='main'):
    if ref != 'main' and not re.fullmatch(r'[a-f0-9]{40}', ref):
        raise ValueError('Use main or an exact commit SHA for --ref.')
    commit = github_json('commits/' + ref)['sha']
    if not re.fullmatch(r'[a-f0-9]{40}', commit):
        raise ValueError('GitHub returned an invalid commit.')
    documents = []
    for filename in ('offsets.json', 'client_dll.json'):
        result = github_json(f'contents/output/{filename}?ref={commit}')
        if result.get('encoding') != 'base64' or result.get('size', MAX_DOWNLOAD + 1) > MAX_DOWNLOAD:
            raise ValueError('Unexpected GitHub content response.')
        documents.append(json.loads(base64.b64decode(result['content'])))
    return build_profile(*documents, commit)
