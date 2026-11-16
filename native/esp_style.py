"""Shared player drawing commands for the GDI overlay and Qt design preview."""
from dataclasses import dataclass
import math

DEFAULT_STYLE = {
    'visible_color': '#55dc8c', 'hidden_color': '#ffad50', 'team_color': '#66b9ff',
    'health_color': '#55dc8c', 'armor_color': '#66b9ff',
    'line_width': 1, 'box': False, 'box_style': 'full', 'names': True, 'distance': True,
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
        if style['box_style'] == 'corner':
            # Each corner covers a quarter of each adjoining edge.
            dx,dy = (right-left)/4,(bottom-top)/4
            for x,y,sx,sy in ((left,top,1,1),(right,top,-1,1),
                              (right,bottom,-1,-1),(left,bottom,1,-1)):
                commands.append(Line((x,y),(x+sx*dx,y),color,width))
                commands.append(Line((x,y),(x,y+sy*dy),color,width))
        else:
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


def aim_fov_commands(frame, config, width, height):
    """Project an angular FOV ring. Invalid or unavailable projections draw nothing."""
    if config.aim == 'off' or not config.aim_draw_fov or width <= 0 or height <= 0:
        return []
    from .core import project
    try:
        pitch, yaw = frame.angles
        if not all(math.isfinite(value) for value in (*frame.eye, pitch, yaw, config.aim_fov)):
            return []
        if not 0 < config.aim_fov <= 30:
            return []
        def point(pitch_degrees):
            p,y = math.radians(pitch_degrees),math.radians(yaw)
            return (frame.eye[0]+1000*math.cos(p)*math.cos(y),
                    frame.eye[1]+1000*math.cos(p)*math.sin(y),
                    frame.eye[2]-1000*math.sin(p))
        center = project(point(pitch),frame.matrix,width,height)
        edge = project(point(pitch-config.aim_fov),frame.matrix,width,height)
        if center is None or edge is None:
            return []
        radius = math.hypot(edge[0]-center[0],edge[1]-center[1])
        if not math.isfinite(radius) or not .5 <= radius <= max(width,height)*2:
            return []
        cx,cy = width/2,height/2
        points = [(cx+radius*math.cos(2*math.pi*i/48),
                   cy+radius*math.sin(2*math.pi*i/48)) for i in range(48)]
        return [Line(points[i],points[(i+1)%48],'#ded9f0') for i in range(48)]
    except (TypeError, ValueError, IndexError, OverflowError):
        return []
