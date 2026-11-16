"""Shared player drawing commands for the GDI overlay and Qt design preview."""
from dataclasses import dataclass

DEFAULT_STYLE = {
    'visible_color': '#55dc8c', 'hidden_color': '#ffad50', 'team_color': '#66b9ff',
    'health_color': '#55dc8c', 'armor_color': '#66b9ff',
    'line_width': 1, 'box': False, 'names': True, 'distance': True,
}
TARGETS = ('head', 'neck', 'chest', 'pelvis')
# Normalized sample pose: artwork only; never consumed by the memory reader.
POSE = {'head':(.5,.12), 'neck':(.5,.23), 'chest':(.5,.34), 'pelvis':(.5,.53),
        'left_shoulder':(.36,.25), 'left_elbow':(.27,.39), 'left_hand':(.23,.53),
        'right_shoulder':(.64,.25), 'right_elbow':(.73,.39), 'right_hand':(.77,.53),
        'left_knee':(.39,.70), 'left_foot':(.35,.88),
        'right_knee':(.61,.70), 'right_foot':(.65,.88)}


@dataclass(frozen=True)
class Line:
    start: tuple
    end: tuple
    color: str
    width: int = 1


@dataclass(frozen=True)
class Text:
    at: tuple
    text: str
    color: str


def actor_color(config, spotted, teammate):
    style = config.esp_style
    return style['team_color'] if teammate else style['visible_color'] if spotted is True else style['hidden_color'] if spotted is False else '#ffffff'


def player_commands(bones, name, meters, health, armor, spotted, teammate, config):
    # Import lazily: core imports Config, which imports this module for defaults.
    from .core import BONE_LINKS
    if not config.esp:
        return []
    visible = [point for point in bones.values() if point is not None]
    if not visible:
        return []
    style = config.esp_style
    color = actor_color(config,spotted,teammate)
    width = style['line_width']
    commands = []
    if config.skeleton:
        for a,b in BONE_LINKS:
            if bones.get(a) is not None and bones.get(b) is not None:
                commands.append(Line(bones[a],bones[b],color,width))
    left,right = min(p[0] for p in visible)-6,max(p[0] for p in visible)+6
    top,bottom = min(p[1] for p in visible)-5,max(p[1] for p in visible)+5
    if style['box']:
        corners = ((left,top),(right,top),(right,bottom),(left,bottom))
        commands.extend(Line(corners[i],corners[(i+1)%4],color,width) for i in range(4))
    label = ' '.join(part for part in (name if style['names'] else '', f'{meters:.0f}m' if style['distance'] else '') if part)
    if label:
        commands.append(Text((left,top-18),label,color))
    if config.health:
        fraction = max(0,min(100,health))/100
        commands.extend((Line((left-5,top),(left-5,bottom),'#282d28',3),
                         Line((left-5,bottom),(left-5,bottom-(bottom-top)*fraction),style['health_color'],3)))
    if config.armor:
        fraction = max(0,min(100,armor))/100
        commands.extend((Line((left,bottom+4),(right,bottom+4),'#282d32',2),
                         Line((left,bottom+4),(left+(right-left)*fraction,bottom+4),style['armor_color'],2)))
    return commands
