from dataclasses import asdict
import unittest

from native.config import Config, validate_config
from native.esp_style import DEFAULT_STYLE, POSE, Line, Text, player_commands
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
        for key,value in [('line_width',True),('line_width',5),('box',1),('visible_color','red'),('hidden_color','#000000')]:
            settings = asdict(Config());settings['esp_style'][key] = value
            with self.assertRaises(ValueError):
                validate_config({'version':1,'settings':settings})
        settings = asdict(Config())
        config = validate_config({'version':1,'settings':settings})
        settings['esp_style']['box'] = True
        self.assertFalse(config.esp_style['box'])
        for name in PRESETS:
            self.assertEqual(preset_document(name)['settings']['esp_style'],DEFAULT_STYLE)

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
