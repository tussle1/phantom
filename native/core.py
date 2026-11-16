"""Bounded memory decoding and deterministic input math; no Windows imports."""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct
from typing import Protocol

from .config import Config
from .catalyst_aim import CatalystMovement
from .schema import Profile

Vec3 = tuple[float, float, float]
BONE_LINKS = (('head','neck'), ('neck','chest'), ('chest','pelvis'),
              ('neck','left_shoulder'), ('left_shoulder','left_elbow'), ('left_elbow','left_hand'),
              ('neck','right_shoulder'), ('right_shoulder','right_elbow'), ('right_elbow','right_hand'),
              ('pelvis','left_knee'), ('left_knee','left_foot'),
              ('pelvis','right_knee'), ('right_knee','right_foot'))


class ReadError(Exception):
    """An unavailable read is never represented by zero-valued game state."""


class Memory(Protocol):
    def read(self, address: int, size: int) -> bytes: ...


def unpack(memory, address, fmt):
    raw = memory.read(address, struct.calcsize(fmt))
    if len(raw) != struct.calcsize(fmt):
        raise ReadError('Short memory read.')
    return struct.unpack(fmt, raw)


def scalar(memory, address, fmt):
    return unpack(memory, address, '<' + fmt)[0]


def valid_pointer(value):
    return type(value) is int and 0x10000 <= value < 0x00007FFFFFFF0000 and value % 8 == 0


def pointer(memory, address, nullable=False):
    value = scalar(memory, address, 'Q')
    if value == 0 and nullable:
        return 0
    if not valid_pointer(value):
        raise ReadError('Invalid/null pointer; game may be loading.')
    return value


def vector(memory, address):
    result = unpack(memory, address, '<3f')
    if not all(math.isfinite(v) and abs(v) < 1_000_000 for v in result):
        raise ReadError('Invalid vector.')
    return result


def distance(a, b):
    return math.sqrt(sum((a[i]-b[i])**2 for i in range(3)))


def add(a, b):
    return tuple(a[i]+b[i] for i in range(3))


def project(point, matrix, width, height):
    if len(matrix) != 16 or width <= 0 or height <= 0 or not all(math.isfinite(x) for x in (*point, *matrix)):
        return None
    w = sum(matrix[12+i]*point[i] for i in range(3)) + matrix[15]
    if w < 0.01:
        return None
    x = (sum(matrix[i]*point[i] for i in range(3))+matrix[3])/w
    y = (sum(matrix[4+i]*point[i] for i in range(3))+matrix[7])/w
    if abs(x) > 4 or abs(y) > 4:
        return None
    return (width*(1+x)/2, height*(1-y)/2)


def angle_to(eye, target):
    x, y, z = (target[i]-eye[i] for i in range(3))
    flat = math.hypot(x, y)
    if flat < 0.001:
        return None
    return (-math.degrees(math.atan2(z, flat)), math.degrees(math.atan2(y, x)))


def angle_delta(target, current):
    return ((target[0]-current[0]+180)%360-180, (target[1]-current[1]+180)%360-180)


def smooth_damp(current, target, velocity, smooth_time, max_speed, dt):
    """Critically damped scalar step with overshoot prevention and bounded dt."""
    if not all(math.isfinite(v) for v in (current,target,velocity,smooth_time,max_speed,dt)) or dt <= 0:
        return current, 0.0
    dt = min(dt, .05)
    omega = 2/max(.001, smooth_time)
    x = omega*dt
    decay = 1/(1+x+.48*x*x+.235*x*x*x)
    change = max(-max_speed*smooth_time, min(max_speed*smooth_time, current-target))
    adjusted = current-change
    temp = (velocity+omega*change)*dt
    next_velocity = (velocity-omega*temp)*decay
    output = adjusted+(change+temp)*decay
    if (target-current > 0) == (output > target):
        return target, 0.0
    return output, next_velocity


@dataclass(frozen=True)
class Actor:
    slot: int
    pawn: int
    name: str
    team: int
    health: int
    armor: int
    position: Vec3
    velocity: Vec3
    bones: dict[str, Vec3] = field(default_factory=dict)
    spotted: bool | None = None


@dataclass(frozen=True)
class Frame:
    local: Actor
    eye: Vec3
    angles: tuple[float, float]
    matrix: tuple[float, ...]
    sensitivity: float
    flags: int
    actors: tuple[Actor, ...]
    crosshair_pawn: int | None = None
    spectators: tuple[str, ...] = ()


class Decoder:
    def __init__(self, memory: Memory, base: int, profile: Profile):
        self.memory, self.base, self.profile = memory, base, profile
        self.stride = None

    def entity(self, root, index, stride=None):
        layout, memory = self.profile.layout, self.memory
        if type(index) is not int or not 0 <= index <= layout['handle_mask']:
            raise ReadError('Entity index is out of range.')
        stride = stride or self.stride
        if stride is None:
            raise ReadError('Entity stride has not been calibrated.')
        chunk = pointer(memory, root + layout['chunk_offset'] + 8*(index//layout['chunk_size']))
        return pointer(memory, chunk + stride*(index % layout['chunk_size']), nullable=True)

    def handle(self, root, handle, stride=None):
        if handle in (0, 0xFFFFFFFF):
            return 0
        return self.entity(root, handle & self.profile.layout['handle_mask'], stride)

    def calibrate(self, root, local_controller, local_pawn):
        handle = scalar(self.memory, local_controller + self.profile.fields['pawn_handle'], 'I')
        matches = []
        for stride in self.profile.layout['entry_strides']:
            try:
                if self.handle(root, handle, stride) == local_pawn:
                    matches.append(stride)
            except ReadError:
                pass
        if len(matches) != 1:
            self.stride = None
            raise ReadError('Cannot uniquely calibrate entity stride against the local pawn.')
        self.stride = matches[0]

    def bones(self, scene, position, config):
        f, layout, memory = self.profile.fields, self.profile.layout, self.memory
        try:
            array = pointer(memory, scene+f['model_state']+layout['bone_array'])
            count = max(config.bones.values())+1
            data = memory.read(array, count*layout['bone_stride'])
            if len(data) != count*layout['bone_stride']:
                return {}
            result = {}
            for name, index in config.bones.items():
                bone = struct.unpack_from('<3f', data, index*layout['bone_stride'])
                if not all(math.isfinite(x) for x in bone) or not .01 < distance(bone, position) < 150:
                    return {}
                result[name] = bone
            head = result['head']
            if not 25 < head[2]-position[2] < 100:
                return {}
            return result
        except (ReadError, struct.error):
            return {}

    def actor(self, pawn, slot, name, local_slot, config, with_bones=True):
        f, memory = self.profile.fields, self.memory
        health = scalar(memory, pawn+f['health'], 'i')
        armor = scalar(memory, pawn+f['armor'], 'i')
        team = scalar(memory, pawn+f['team'], 'B')
        if not 0 <= health <= 100 or not 0 <= armor <= 100 or team not in (2, 3):
            raise ReadError('Player values do not match this profile.')
        scene = pointer(memory, pawn+f['scene'])
        if scalar(memory, scene+f['dormant'], '?'):
            raise ReadError('Dormant actor.')
        position = vector(memory, scene+f['origin'])
        velocity = vector(memory, pawn+f['velocity'])
        if any(abs(v) > 10000 for v in velocity):
            raise ReadError('Implausible velocity.')
        spotted = None
        if local_slot is not None:
            try:
                mask = scalar(memory, pawn+f['spotted_state']+f['spotted_mask'], 'Q')
                spotted = bool(mask & (1 << (local_slot-1)))
            except ReadError:
                pass
        return Actor(slot,pawn,name,team,health,armor,position,velocity,
                     self.bones(scene,position,config) if with_bones else {},spotted)

    def capture(self, config):
        f, modules, memory = self.profile.fields, self.profile.modules, self.memory
        root = pointer(memory, self.base+modules['dwEntityList'])
        local_pawn = pointer(memory, self.base+modules['dwLocalPlayerPawn'])
        local_controller = pointer(memory, self.base+modules['dwLocalPlayerController'])
        self.calibrate(root,local_controller,local_pawn)
        controllers, local_slot = [], None
        for slot in range(1,self.profile.layout['controller_limit']+1):
            try:
                controller = self.entity(root,slot)
                if not controller:
                    continue
                if controller == local_controller:
                    local_slot = slot
                controllers.append((slot,controller))
            except ReadError:
                continue
        if local_slot is None:
            raise ReadError('Local controller is absent from the entity list.')
        local = self.actor(local_pawn,local_slot,'local',local_slot,config,False)
        view = vector(memory, local_pawn+f['view_offset'])
        if not 0 <= view[2] <= 100 or abs(view[0]) > 10 or abs(view[1]) > 10:
            raise ReadError('Invalid eye offset.')
        matrix = unpack(memory, self.base+modules['dwViewMatrix'], '<16f')
        if not all(math.isfinite(v) and abs(v) < 1e8 for v in matrix) or not any(abs(v) > .001 for v in matrix):
            raise ReadError('Invalid view matrix.')
        angles3 = vector(memory,self.base+modules['dwViewAngles'])
        if not -90 <= angles3[0] <= 90 or abs(angles3[1]) > 360:
            raise ReadError('Invalid view angles.')
        sensitivity_address = pointer(memory,self.base+modules['dwSensitivity'])
        sensitivity = scalar(memory,sensitivity_address+modules['dwSensitivity_sensitivity'],'f')
        if not math.isfinite(sensitivity) or not .01 <= sensitivity <= 100:
            raise ReadError('Invalid sensitivity.')
        flags = scalar(memory,local_pawn+f['flags'],'I')
        actors, spectators = [], []
        for slot, controller in controllers:
            if controller == local_controller:
                continue
            try:
                raw_name = memory.read(controller+f['name'],128).split(b'\0',1)[0]
                name = ''.join(c for c in raw_name.decode('utf-8','replace') if c.isprintable())[:40] or f'player {slot}'
                pawn = self.handle(root,scalar(memory,controller+f['pawn_handle'],'I'))
                if pawn and scalar(memory,pawn+f['health'],'i') > 0:
                    actor = self.actor(pawn,slot,name,local_slot,config)
                    actors.append(actor)
                    continue
                observer = self.handle(root,scalar(memory,controller+f['observer_pawn'],'I'))
                if observer:
                    services = pointer(memory,observer+f['observer_services'])
                    target = self.handle(root,scalar(memory,services+f['observer_target'],'I'))
                    if target == local_pawn:
                        spectators.append(name)
            except ReadError:
                continue
        crosshair = None
        try:
            index = scalar(memory,local_pawn+f['crosshair'],'i')
            if 0 < index <= self.profile.layout['handle_mask']:
                crosshair = self.entity(root,index)
        except ReadError:
            pass
        # A map transition or respawn invalidates the whole sample, not just the input.
        if pointer(memory,self.base+modules['dwLocalPlayerPawn']) != local_pawn:
            raise ReadError('Local pawn changed during capture.')
        return Frame(local,add(local.position,view),angles3[:2],matrix,sensitivity,flags,
                     tuple(actors),crosshair,tuple(spectators))


def choose_target(frame, config):
    if frame.local.health <= 0:
        return None
    best, best_score = None, config.aim_fov
    for actor in frame.actors:
        if actor.team == frame.local.team or actor.health <= 0 or actor.spotted is not True:
            continue
        if distance(actor.position,frame.local.position)*.0254 > config.max_distance_m:
            continue
        bone = actor.bones.get(config.priority_bone)
        if bone is None:
            continue
        predicted = tuple(bone[i]+actor.velocity[i]*config.prediction_ms/1000 for i in range(3))
        angle = angle_to(frame.eye,predicted)
        if angle is None:
            continue
        delta = angle_delta(angle,frame.angles)
        score = math.hypot(*delta)
        if score < best_score:
            best_score = score
            best = (actor.pawn,delta)
    return best


class AimController:
    def __init__(self, rng=None):
        self.catalyst = CatalystMovement(rng)
        self.reset()

    def reset(self):
        self.catalyst.reset()
        self.target = None
        self.velocity = [0.0,0.0]
        self.remainder = [0.0,0.0]

    def step(self, frame, config, held, dt):
        target = choose_target(frame,config) if held and config.aim != 'off' else None
        if target is None or not 0 < dt <= .1:
            self.reset()
            return (0,0)
        pawn, delta = target
        if pawn != self.target:
            self.reset()
            self.target = pawn
        if config.aim == 'catalyst':
            return self.catalyst.step(delta,frame.sensitivity,config.mouse_yaw,
                                      config.mouse_pitch,config.catalyst_smoothing)
        if config.aim == 'smooth':
            movement = []
            for i in range(2):
                value,self.velocity[i] = smooth_damp(0,delta[i],self.velocity[i],
                    config.smooth_time,config.max_aim_speed,dt)
                movement.append(value)
        else:
            # Hardlock removes damping; the per-frame speed cap still prevents huge jumps.
            cap = config.max_aim_speed*dt
            movement = [max(-cap,min(cap,value)) for value in delta]
        counts = [-movement[1]/(frame.sensitivity*config.mouse_yaw),
                  movement[0]/(frame.sensitivity*config.mouse_pitch)]
        result = []
        for i,value in enumerate(counts):
            value = max(-250,min(250,value+self.remainder[i]))
            count = math.trunc(value)
            self.remainder[i] = value-count
            result.append(count)
        return tuple(result)


class TriggerController:
    def __init__(self):
        self.reset()

    def reset(self):
        self.target = None
        self.since = None

    def step(self, frame, config, held, now):
        target = next((a for a in frame.actors if a.pawn == frame.crosshair_pawn and
                       a.health > 0 and a.team != frame.local.team and a.spotted is True),None)
        if not config.trigger or not held or frame.local.health <= 0 or target is None:
            self.reset()
            return False
        if target.pawn != self.target:
            self.target,self.since = target.pawn,now
        if now-self.since >= config.trigger_delay_ms/1000:
            self.since = now
            return True
        return False


class JumpController:
    def __init__(self):
        self.grounded = False

    def step(self, frame, config, held):
        ground = bool(frame.flags & 1)
        fire = config.bunny_hop and held and frame.local.health > 0 and ground and not self.grounded
        self.grounded = ground if held else False
        return fire
