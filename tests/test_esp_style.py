from dataclasses import asdict
import unittest
import math
from types import SimpleNamespace

from native.config import Config, validate_config
from native.esp_style import DEFAULT_STYLE, POSE, Line, Text, player_commands, aim_fov_commands
from native.presets import PRESETS, preset_document


class EspStyleTests(unittest.TestCase):
    def test_old_configs_upgrade_without_mutation_or_unknown_keys(self):
        settings = asdict(Config());settings.pop('esp_style');settings['keys'].pop('menu_toggle')
        upgraded = validate_config({'version':1,'settings':settings})
        self.assertEqual(upgraded.esp_style, DEFAULT_STYLE)
        self.assertNotIn('esp_style', settings)
        self.assertEqual(upgraded.keys['menu_toggle'],0xA1)
        settings['unknown'] = True
        with self.assertRaises(ValueError):
            validate_config({'version':1,'settings':settings})

    def test_style_validation_and_copying(self):
        for key,value in [('box_style','unknown'),('box_style',True),('line_width',True),('line_width',5),('box',1),('visible_color','red'),('hidden_color','#000000')]:
            settings = asdict(Config());settings['esp_style'][key] = value
            with self.assertRaises(ValueError):
                validate_config({'version':1,'settings':settings})
        settings = asdict(Config())
        config = validate_config({'version':1,'settings':settings})
        settings['esp_style']['box'] = True
        self.assertFalse(config.esp_style['box'])
        for name in PRESETS:
            self.assertEqual(preset_document(name)['settings']['esp_style'],DEFAULT_STYLE)

    def test_existing_style_upgrades_without_mutation(self):
        settings = asdict(Config())
        settings['esp_style'].pop('box_style')
        upgraded = validate_config({'version': 1, 'settings': settings})
        self.assertEqual(upgraded.esp_style['box_style'], 'full')
        self.assertNotIn('box_style', settings['esp_style'])

    def test_corner_box_geometry(self):
        config = Config(skeleton=False, health=False, armor=False)
        config.esp_style.update(box=True, box_style='corner', names=False, distance=False)
        lines = player_commands({'head': (10, 20), 'pelvis': (30, 60)}, '', 0, 0, 0, True, False, config)
        self.assertEqual(len(lines), 8)
        self.assertEqual(lines[0].start, (4, 15))
        self.assertEqual(lines[0].end, (12, 15))
        self.assertEqual(lines[1].end, (4, 27.5))
        self.assertTrue(all(line.color == config.esp_style['visible_color'] for line in lines))

    def test_aim_fov_ring_projection_and_failure_cases(self):
        # Perspective fixture: forward is +X, screen axes are -Y/+Z.
        matrix = (0.,-1.,0.,0., 0.,0.,1.,0., 0.,0.,0.,0., 1.,0.,0.,0.)
        frame = SimpleNamespace(eye=(0.,0.,0.), angles=(0.,0.), matrix=matrix)
        config = Config(aim='smooth', aim_draw_fov=True, aim_fov=5)
        commands = aim_fov_commands(frame,config,1920,1080)
        self.assertEqual(len(commands),48)
        self.assertAlmostEqual(commands[0].start[0]-960,540*math.tan(math.radians(5)))
        self.assertEqual(commands[-1].end,commands[0].start)
        self.assertTrue(all(isinstance(c, Line) for c in commands))
        self.assertEqual(aim_fov_commands(frame,Config(aim='off',aim_draw_fov=True),1920,1080),[])
        self.assertEqual(aim_fov_commands(frame,Config(aim='smooth'),1920,1080),[])
        self.assertEqual(aim_fov_commands(frame,config,0,1080),[])
        frame.matrix = (0.,)*16
        self.assertEqual(aim_fov_commands(frame,config,1920,1080),[])
        frame.matrix = matrix
        frame.angles = (float('nan'),0.)
        self.assertEqual(aim_fov_commands(frame,config,1920,1080),[])

    def test_legacy_settings_upgrade_new_aim_flag(self):
        settings = asdict(Config())
        settings.pop('aim_draw_fov')
        settings['esp_style'].pop('box_style')
        restored = validate_config({'version':1,'settings':settings})
        self.assertFalse(restored.aim_draw_fov)
        self.assertEqual(restored.esp_style['box_style'],'full')
        self.assertNotIn('aim_draw_fov',settings)
        settings['aim_draw_fov'] = 1
        with self.assertRaises(ValueError):
            validate_config({'version':1,'settings':settings})

    def test_commands_reflect_style_and_actor_state(self):
        config = Config()
        config.esp_style.update(box=True,line_width=3,visible_color='#112233',health_color='#abcdef')
        bones = {name:(x*300,y*400) for name,(x,y) in POSE.items()}
        commands = player_commands(bones,'example',42,75,50,True,False,config)
        self.assertTrue(any(isinstance(c,Line) and c.color=='#112233' and c.width==3 for c in commands))
        self.assertTrue(any(isinstance(c,Line) and c.color=='#abcdef' for c in commands))
        self.assertTrue(any(isinstance(c,Text) and c.text=='example 42m' for c in commands))
        config.skeleton=False;config.health=False;config.armor=False
        config.esp_style.update(names=False,distance=False)
        self.assertEqual(len(player_commands(bones,'example',42,75,50,False,False,config)),4)
        self.assertTrue(all(c.color==config.esp_style['hidden_color'] for c in player_commands(bones,'x',1,0,0,False,False,config)))
        self.assertTrue(all(c.color==config.esp_style['team_color'] for c in player_commands(bones,'x',1,0,0,False,True,config)))
        config.esp=False
        self.assertEqual(player_commands(bones,'x',1,0,0,True,False,config),[])
        config.esp=True
        self.assertEqual(player_commands({},'x',1,0,0,True,False,config),[])


if __name__ == '__main__':
    unittest.main()
