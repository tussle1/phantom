"""Native unit tests use fabricated memory, never a live process."""
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import phantom
from native.config import Config, config_path, load_config, save_config, validate_config
from native.core import (Actor, AimController, Decoder, Frame, JumpController, ReadError,
                         TriggerController, angle_delta, angle_to, choose_target, project,
                         smooth_damp, vector)
from native.schema import FIELDS, LAYOUT, MODULES, build_profile, validate_profile


IDENTITY = (1.,0.,0.,0., 0.,1.,0.,0., 0.,0.,1.,0., 0.,0.,0.,1.)


def document():
    fields = {'health':0x100,'armor':0x104,'team':0x108,'scene':0x110,
              'velocity':0x120,'flags':0x130,'view_offset':0x140,
              'pawn_handle':0x150,'name':0x200,'spotted_state':0x160,
              'spotted_mask':8,'crosshair':0x180,'observer_pawn':0x190,
              'observer_services':0x198,'observer_target':0x20,
              'origin':0x20,'dormant':0x40,'model_state':0x100}
    modules = {key:0x10000+i*0x100 for i,key in enumerate(MODULES)}
    modules['dwSensitivity_sensitivity'] = 0x58
    return {'version':1,'source':'a'*40,'fields':fields,'modules':modules,'layout':dict(LAYOUT)}


class FakeMemory:
    def __init__(self):
        self.data = {}

    def write(self,address,data):
        self.data.update({address+i:b for i,b in enumerate(data)})

    def put(self,address,fmt,*values):
        self.write(address,struct.pack('<'+fmt,*values))

    def read(self,address,size):
        try:
            return bytes(self.data[address+i] for i in range(size))
        except KeyError as error:
            raise ReadError('Unmapped fixture memory.') from error


def fixture():
    profile = validate_profile(document())
    memory = FakeMemory()
    base,root,chunk0,chunk1 = 0x10000000,0x20000000,0x21000000,0x22000000
    local_controller,enemy_controller = 0x30000000,0x31000000
    local_pawn,enemy_pawn = 0x40000000,0x41000000
    f,m = profile.fields,profile.modules
    memory.put(base+m['dwEntityList'],'Q',root)
    memory.put(base+m['dwLocalPlayerPawn'],'Q',local_pawn)
    memory.put(base+m['dwLocalPlayerController'],'Q',local_controller)
    memory.put(root+0x10,'Q',chunk0)
    memory.put(root+0x18,'Q',chunk1)
    stride = 0x70
    for index,address in [(1,local_controller),(2,enemy_controller),(1001,local_pawn),(1002,enemy_pawn)]:
        chunk = chunk0 if index < 512 else chunk1
        memory.put(chunk+(index%512)*stride,'Q',address)
    memory.put(local_controller+f['pawn_handle'],'I',1001)
    memory.put(enemy_controller+f['pawn_handle'],'I',1002)
    memory.write(enemy_controller+f['name'],b'fixture enemy\0'+b'\0'*114)
    for pawn,scene,origin,team in [(local_pawn,0x50000000,(0,0,0),2),(enemy_pawn,0x51000000,(100,0,0),3)]:
        memory.put(pawn+f['health'],'i',100)
        memory.put(pawn+f['armor'],'i',80)
        memory.put(pawn+f['team'],'B',team)
        memory.put(pawn+f['scene'],'Q',scene)
        memory.put(pawn+f['velocity'],'3f',0,0,0)
        memory.put(pawn+f['spotted_state']+f['spotted_mask'],'Q',1)
        memory.put(scene+f['origin'],'3f',*origin)
        memory.put(scene+f['dormant'],'?',False)
    array = 0x60000000
    memory.put(0x51000000+f['model_state']+0x80,'Q',array)
    memory.write(array,bytes(28*32))
    for name,index in Config().bones.items():
        z = 64 if name == 'head' else 35
        memory.put(array+index*32,'3f',100,0,z)
    memory.put(local_pawn+f['view_offset'],'3f',0,0,64)
    memory.put(local_pawn+f['flags'],'I',1)
    memory.put(local_pawn+f['crosshair'],'i',1002)
    memory.put(base+m['dwViewMatrix'],'16f',*IDENTITY)
    memory.put(base+m['dwViewAngles'],'3f',0,0,0)
    memory.put(base+m['dwSensitivity'],'Q',0x70000000)
    memory.put(0x70000000+m['dwSensitivity_sensitivity'],'f',2.)
    return memory,Decoder(memory,base,profile),local_pawn,enemy_pawn


def frame():
    local = Actor(1,0x40000000,'local',2,100,100,(0,0,0),(0,0,0))
    enemy = Actor(2,0x41000000,'enemy',3,100,100,(100,1,0),(0,0,0),{'head':(100,1,64)},True)
    return Frame(local,(0,0,64),(0,0),IDENTITY,2,1,(enemy,),enemy.pawn)


class NativeConfigTests(unittest.TestCase):
    def test_roundtrip_and_named_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            path = config_path(directory,'practice 01')
            save_config(path,Config())
            self.assertEqual(asdict(load_config(path)),asdict(Config()))
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])

    def test_reject_unsupported_features_and_invalid_values(self):
        for key,value in [('aim','silent'),('aim_fov',float('nan')),('smooth_time',0),
                           ('max_aim_speed',True),('mouse_yaw',0),('skeleton',1),
                           ('priority_bone','foot'),('bones',{}),('keys',{})]:
            document = {'version':1,'settings':{**asdict(Config()),key:value}}
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_config(document)
        with self.assertRaises(ValueError):
            validate_config({'version':1,'settings':{**asdict(Config()),'noSmoke':True}})

    def test_invalid_keys_and_bones(self):
        for group,key,value in [('keys','aim_hold',0),('keys','exit',300),('bones','head',256),('bones','head',True)]:
            settings = asdict(Config());settings[group][key] = value
            with self.assertRaises(ValueError):
                validate_config({'version':1,'settings':settings})
        settings = asdict(Config());settings['keys']['save'] = settings['keys']['exit']
        with self.assertRaises(ValueError):
            validate_config({'version':1,'settings':settings})

    def test_path_traversal_and_windows_device_names(self):
        for name in ['../x','a/b','a\\b','CON','com1','LPT9','name ', '', 'x'*41]:
            with self.subTest(name=name),self.assertRaises(ValueError):
                config_path('/tmp',name)

    def test_init_cli_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(phantom.main(['--config-dir',directory,'--init-config']),0)
            self.assertEqual(phantom.main(['--config-dir',directory,'--init-config']),1)


class ProfileTests(unittest.TestCase):
    def test_valid_profile(self):
        self.assertEqual(validate_profile(document()).source,'a'*40)

    def test_invalid_profile(self):
        for key,value in [('version',2),('source','main'),('modules',{}),('fields',{}),('layout',{})]:
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_profile({**document(),key:value})
        for strides in [[],[0x70,0x70],[0x71],[True]]:
            doc = document();doc['layout']['entry_strides'] = strides
            with self.assertRaises(ValueError):
                validate_profile(doc)

    def test_bundled_reference_module_values(self):
        from native.schema import load_profile
        profile = load_profile(Path(__file__).resolve().parents[1]/'native/profiles/reference-26598758.json')
        expected = {'dwEntityList':0x2709010,'dwLocalPlayerController':0x252B0C8,
                    'dwLocalPlayerPawn':0x2553D38,'dwViewAngles':0x256A4B8,'dwViewMatrix':0x2559640}
        for key,value in expected.items():
            self.assertEqual(profile.modules[key],value)

    def test_extract_only_needed_schema_fields(self):
        doc = document()
        classes = {}
        for key,(cls,name) in FIELDS.items():
            classes.setdefault(cls,{'fields':{}})['fields'][name] = doc['fields'][key]
        built = build_profile({'client.dll':doc['modules']},{'client.dll':{'classes':classes}},'b'*40)
        self.assertEqual(built['fields'],doc['fields'])
        self.assertEqual(built['source'],'b'*40)


class DecoderTests(unittest.TestCase):
    def test_real_decode_path_with_fixture_memory(self):
        memory,decoder,local,enemy = fixture()
        result = decoder.capture(Config())
        self.assertEqual(decoder.stride,0x70)
        self.assertEqual(result.local.pawn,local)
        self.assertEqual(len(result.actors),1)
        actor = result.actors[0]
        self.assertEqual(actor.pawn,enemy)
        self.assertEqual(actor.name,'fixture enemy')
        self.assertEqual(actor.health,100)
        self.assertTrue(actor.spotted)
        self.assertEqual(actor.bones['head'],(100.,0.,64.))
        self.assertEqual(result.crosshair_pawn,enemy)

    def test_map_transition_invalidates_frame(self):
        memory,decoder,local,_ = fixture()
        original = memory.read
        local_address = decoder.base+decoder.profile.modules['dwLocalPlayerPawn']
        reads = 0
        def changing_read(address,size):
            nonlocal reads
            if address == local_address:
                reads += 1
                if reads > 1:
                    return struct.pack('<Q',local+0x100000)
            return original(address,size)
        memory.read = changing_read
        with self.assertRaises(ReadError):
            decoder.capture(Config())

    def test_dead_observer_can_be_resolved_without_dead_skeleton(self):
        memory,decoder,local,enemy = fixture()
        fields = decoder.profile.fields
        memory.put(enemy+fields['health'],'i',0)
        # Observer pawn uses the same valid handle in this fixture; no live actor is emitted.
        memory.put(0x31000000+fields['observer_pawn'],'I',1002)
        services = 0x71000000
        memory.put(enemy+fields['observer_services'],'Q',services)
        memory.put(services+fields['observer_target'],'I',1001)
        sample = decoder.capture(Config())
        self.assertEqual(sample.actors,())
        self.assertEqual(sample.spectators,('fixture enemy',))

    def test_invalid_bones_are_omitted_not_fabricated(self):
        memory,decoder,_,_ = fixture()
        memory.put(0x60000000+6*32,'3f',math.nan,0,0)
        self.assertEqual(decoder.capture(Config()).actors[0].bones,{})

    def test_bad_actor_health_is_skipped(self):
        memory,decoder,_,enemy = fixture()
        memory.put(enemy+decoder.profile.fields['health'],'i',-100)
        self.assertEqual(decoder.capture(Config()).actors,())

    def test_bad_local_health_invalidates_frame(self):
        memory,decoder,local,_ = fixture()
        memory.put(local+decoder.profile.fields['health'],'i',100000)
        with self.assertRaises(ReadError):
            decoder.capture(Config())

    def test_bad_pointer_is_not_zero_health(self):
        memory,decoder,_,_ = fixture()
        memory.put(decoder.base+decoder.profile.modules['dwLocalPlayerPawn'],'Q',0)
        with self.assertRaises(ReadError):
            decoder.capture(Config())

    def test_ambiguous_stride_is_rejected(self):
        memory,decoder,local,_ = fixture()
        # Make both stride candidates resolve to local; calibration must fail closed.
        memory.put(0x22000000+(1001%512)*0x78,'Q',local)
        with self.assertRaises(ReadError):
            decoder.capture(Config())

    def test_short_read_and_nonfinite_vector(self):
        memory = FakeMemory()
        memory.put(0x10000,'3f',0,0,float('inf'))
        with self.assertRaises(ReadError):
            vector(memory,0x10000)
        with self.assertRaises(ReadError):
            vector(memory,0x20000)

    def test_entity_index_bounds(self):
        _,decoder,_,_ = fixture()
        for index in [-1,32768,True]:
            with self.assertRaises(ReadError):
                decoder.entity(0x20000000,index,0x70)

    def test_spotted_is_local_player_specific(self):
        memory,decoder,_,enemy = fixture()
        f = decoder.profile.fields
        memory.put(enemy+f['spotted_state']+f['spotted_mask'],'Q',2)
        self.assertFalse(decoder.capture(Config()).actors[0].spotted)


class GeometryTests(unittest.TestCase):
    def test_projection(self):
        self.assertEqual(project((0,0,0),IDENTITY,1920,1080),(960,540))
        self.assertEqual(project((1,1,0),IDENTITY,1920,1080),(1920,0))
        self.assertIsNone(project((0,0,0),IDENTITY[:12]+(0.,0.,0.,-1.),1920,1080))
        self.assertIsNone(project((math.nan,0,0),IDENTITY,1920,1080))
        self.assertIsNone(project((10000,0,0),IDENTITY,1920,1080))

    def test_wrapped_angles(self):
        self.assertEqual(angle_delta((0,-179),(0,179)),(0,2))
        self.assertEqual(angle_to((0,0,0),(10,0,0)),(0.,0.))
        self.assertIsNone(angle_to((0,0,0),(0,0,10)))

    def test_smooth_damp_converges_without_overshoot(self):
        position,velocity = 0.,0.
        for _ in range(300):
            next_position,velocity = smooth_damp(position,10.,velocity,.15,90,1/60)
            self.assertGreaterEqual(next_position,position)
            self.assertLessEqual(next_position,10.)
            position = next_position
        self.assertAlmostEqual(position,10.,places=4)
        self.assertEqual(smooth_damp(0,10,0,.1,90,0),(0,0.))


class InputMathTests(unittest.TestCase):
    def test_target_filters(self):
        sample,config = frame(),Config()
        self.assertIsNotNone(choose_target(sample,config))
        for actor in [replace(sample.actors[0],team=2),replace(sample.actors[0],health=0),
                      replace(sample.actors[0],spotted=False),replace(sample.actors[0],spotted=None),
                      replace(sample.actors[0],bones={})]:
            self.assertIsNone(choose_target(replace(sample,actors=(actor,)),config))
        self.assertIsNone(choose_target(replace(sample,local=replace(sample.local,health=0)),config))
        self.assertIsNone(choose_target(sample,replace(config,aim_fov=.1)))

    def test_aim_requires_activation_and_resets_on_loss(self):
        sample,config = frame(),Config(aim='smooth')
        controller = AimController()
        self.assertEqual(controller.step(sample,config,False,1/60),(0,0))
        moves = [controller.step(sample,config,True,1/60) for _ in range(10)]
        self.assertTrue(any(dx < 0 for dx,dy in moves))
        self.assertTrue(all(abs(dx)<=250 and abs(dy)<=250 for dx,dy in moves))
        self.assertEqual(controller.step(sample,config,True,1),(0,0))
        self.assertIsNone(controller.target)
        self.assertEqual(controller.step(sample,Config(),True,1/60),(0,0))

    def test_hardlock_is_speed_bounded(self):
        dx,dy = AimController().step(frame(),Config(aim='hardlock'),True,1/60)
        self.assertLess(dx,0)
        self.assertEqual(dy,0)
        self.assertLessEqual(abs(dx),250)

    def test_prediction_changes_target_angle(self):
        sample = frame()
        sample = replace(sample,actors=(replace(sample.actors[0],velocity=(0,10,0)),))
        a = choose_target(sample,Config(prediction_ms=0))[1]
        b = choose_target(sample,Config(prediction_ms=100))[1]
        self.assertGreater(b[1],a[1])

    def test_trigger_stability_delay_cooldown_and_release(self):
        sample,config,controller = frame(),Config(trigger=True),TriggerController()
        self.assertFalse(controller.step(sample,config,True,0))
        self.assertFalse(controller.step(sample,config,True,.14))
        self.assertTrue(controller.step(sample,config,True,.16))
        self.assertFalse(controller.step(sample,config,True,.17))
        self.assertFalse(controller.step(sample,config,False,.4))
        self.assertFalse(controller.step(sample,config,True,.5))
        self.assertFalse(controller.step(replace(sample,crosshair_pawn=None),config,True,.8))

    def test_trigger_never_targets_teammates(self):
        sample = frame()
        sample = replace(sample,actors=(replace(sample.actors[0],team=2),))
        controller = TriggerController()
        self.assertFalse(controller.step(sample,Config(trigger=True),True,0))
        self.assertFalse(controller.step(sample,Config(trigger=True),True,1))

    def test_jump_once_per_landing(self):
        sample,config,controller = frame(),Config(bunny_hop=True),JumpController()
        self.assertTrue(controller.step(sample,config,True))
        self.assertFalse(controller.step(sample,config,True))
        self.assertFalse(controller.step(replace(sample,flags=0),config,True))
        self.assertTrue(controller.step(sample,config,True))
        self.assertFalse(JumpController().step(sample,Config(),True))


if __name__ == '__main__':
    unittest.main()
