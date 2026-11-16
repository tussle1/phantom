"""Standalone native Phantom entry point. Does not start the legacy browser server."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import struct
import sys
import time

from native.config import config_path, load_config, save_config, Config, write_json
from native.core import AimController, Decoder, JumpController, ReadError, TriggerController
from native.schema import build_profile, download_profile, load_profile

DATA = Path(os.environ.get('LOCALAPPDATA', Path.home()/'.config'))/'PhantomNative'


def run(profile,config,path):
    from native import windows as win

    if struct.calcsize('P') != 8:
        raise OSError('Use 64-bit Python for the 64-bit game process.')
    process,decoder,game = None,None,None
    overlay = win.Overlay()
    aim,trigger,jump = AimController(),TriggerController(),JumpController()
    previous_keys = {}
    previous_mode = config.aim if config.aim != 'off' else 'smooth'
    retry_at,last_tick = 0.0,time.perf_counter()
    last_status = None

    def status(message):
        nonlocal last_status
        if message != last_status:
            print(message,flush=True)
            last_status = message

    print('Native external runtime. Borderless/windowed CS2 is required for the overlay.')
    print('F6 ESP | F7 aim | F8 trigger | F5 radar | F9 reload | F10 save | End exit')
    print('Input is foreground-gated. Aim and trigger are disabled in new configs.')
    try:
        while overlay.pump():
            now = time.perf_counter()
            dt,last_tick = now-last_tick,now
            keys = {name:win.held(vk) for name,vk in config.keys.items()}
            edges = {name:down and not previous_keys.get(name,False) for name,down in keys.items()}
            previous_keys = keys
            if edges['exit']:
                break
            if process and not process.alive():
                process.close()
                process,decoder,game = None,None,None
                overlay.hide()
            if process is None:
                aim.reset();trigger.reset();jump = JumpController()
                if now < retry_at:
                    time.sleep(.02)
                    continue
                retry_at = now+1
                pid = win.find_game()
                if not pid:
                    status('Waiting for cs2.exe…')
                    continue
                candidate = None
                try:
                    candidate = win.Process(pid)
                    base,size = win.client_module(pid)
                    for key,value in profile.modules.items():
                        if key != 'dwSensitivity_sensitivity' and value+64 > size:
                            raise ReadError('Profile contains an offset outside client.dll; update the profile.')
                    process = candidate
                    decoder = Decoder(process,base,profile)
                    status(f'Attached read-only to PID {pid}; profile {profile.source[:12]}.')
                except (OSError,ReadError) as error:
                    if candidate:
                        candidate.close()
                    status(f'Waiting for readable client.dll: {error}')
                    continue
            if game is None or not win.is_visible(game):
                game = win.game_window(process.pid)
            if not win.focused(game,process.pid):
                overlay.hide();aim.reset();trigger.reset();jump = JumpController()
                time.sleep(.025)
                continue
            if edges['reload']:
                try:
                    config = load_config(path)
                    previous_mode = config.aim if config.aim != 'off' else 'smooth'
                    previous_keys = {name:win.held(vk) for name,vk in config.keys.items()}
                    aim.reset();trigger.reset();jump = JumpController()
                    status(f'Reloaded {path.name}.')
                except (OSError,ValueError) as error:
                    status(f'Config reload rejected; previous config retained: {error}')
                # Do not act on bindings sampled before the configuration changed.
                overlay.hide()
                continue
            if edges['esp_toggle']:
                config.esp = not config.esp
            if edges['radar_toggle']:
                config.radar = not config.radar
            if edges['aim_toggle']:
                if config.aim != 'off':
                    previous_mode,config.aim = config.aim,'off'
                else:
                    config.aim = previous_mode
                aim.reset()
            if edges['trigger_toggle']:
                config.trigger = not config.trigger
                trigger.reset()
            if edges['save']:
                try:
                    save_config(path,config)
                    status(f'Saved {path.name}.')
                except (OSError,ValueError) as error:
                    status(f'Config save failed: {error}')
            try:
                frame = decoder.capture(config)
            except ReadError as error:
                overlay.hide();aim.reset();trigger.reset();jump = JumpController()
                status(f'No usable frame: {error}')
                time.sleep(.05)
                continue
            if not win.focused(game,process.pid):
                overlay.hide();aim.reset();trigger.reset();jump = JumpController()
                continue
            overlay.present(game,frame,config)
            status(f'Live reads: {len(frame.actors)} other players. Spotted-mask colors are not map visibility.')
            events = []
            dx,dy = aim.step(frame,config,keys['aim_hold'],dt)
            if dx or dy:
                events.append(win.mouse(1,dx,dy))
            if trigger.step(frame,config,keys['trigger_hold'],now):
                events.extend((win.mouse(2),win.mouse(4)))
            if jump.step(frame,config,keys['jump_hold']):
                events.extend((win.keyboard(0x20),win.keyboard(0x20,True)))
            win.emit(events,game,process.pid)
            time.sleep(max(0,1/60-(time.perf_counter()-now)))
    finally:
        # This is single-threaded: stop input, destroy GDI resources, then close RPM.
        aim.reset();trigger.reset()
        overlay.close()
        if process:
            process.close()


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument('--profile',type=Path,default=DATA/'offset-profile.json')
    result.add_argument('--config-dir',type=Path,default=DATA/'configs')
    result.add_argument('--config',default='default',help='Named native config, without .json')
    result.add_argument('--init-config',action='store_true',help='Create a config without attaching to a game.')
    result.add_argument('--list-configs',action='store_true')
    result.add_argument('--update-offsets',action='store_true',help='Explicitly fetch a pinned profile from a2x/cs2-dumper.')
    result.add_argument('--ref',default='main',help='main or exact a2x/cs2-dumper commit SHA')
    result.add_argument('--import-dumps',type=Path,help='Directory containing offsets.json and client_dll.json; requires --ref SHA.')
    result.add_argument('--check-profile',action='store_true',help='Validate profile structure only; not a live compatibility check.')
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        path = config_path(args.config_dir,args.config)
        if args.list_configs:
            if args.config_dir.exists():
                for file in sorted(args.config_dir.glob('*.json')):
                    try:
                        config_path(args.config_dir,file.stem)
                        print(file.stem)
                    except ValueError:
                        continue
            return 0
        if args.update_offsets or args.import_dumps:
            if args.update_offsets and args.import_dumps:
                raise ValueError('Choose --update-offsets or --import-dumps, not both.')
            if args.import_dumps:
                from native.schema import MAX_DOWNLOAD
                documents = []
                for filename in ('offsets.json','client_dll.json'):
                    source = args.import_dumps/filename
                    if source.stat().st_size > MAX_DOWNLOAD:
                        raise ValueError('Dump exceeds the size limit.')
                    documents.append(json.loads(source.read_text(encoding='utf-8')))
                document = build_profile(*documents,args.ref)
            else:
                document = download_profile(args.ref)
            write_json(args.profile,document)
            print(f'Wrote pinned profile {document["source"]} to {args.profile}')
            print('Structural validation passed. Live game compatibility has NOT been verified.')
            return 0
        if args.init_config:
            if path.exists():
                raise ValueError('Config already exists; it has not been overwritten.')
            save_config(path,Config())
            print(path)
            return 0
        if args.check_profile:
            profile = load_profile(args.profile)
            print(f'Valid profile structure: a2x/cs2-dumper@{profile.source}')
            print('This does not test live game offsets, entity layout, bone mapping, or Windows APIs.')
            return 0
        if sys.platform != 'win32':
            raise OSError('The native runtime requires 64-bit Windows. Config/profile tools and tests are cross-platform.')
        profile = load_profile(args.profile)
        if not path.exists():
            save_config(path,Config())
        config = load_config(path)
        print(f'Native config: {path}')
        run(profile,config,path)
        return 0
    except KeyboardInterrupt:
        return 0
    except (OSError,ValueError,KeyError,TypeError) as error:
        print(f'Phantom: {error}',file=sys.stderr)
        print('Setup: py -3 phantom.py --update-offsets, then py -3 phantom.py --init-config',file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
