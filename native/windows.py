"""Typed, read-only Win32 process access, foreground-gated input and GDI overlay."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import math
import os
import sys

if sys.platform != 'win32':
    raise OSError('The native runtime requires Windows.')

from .core import BONE_LINKS, ReadError, distance, project, valid_pointer

kernel = C.WinDLL('kernel32', use_last_error=True)
user = C.WinDLL('user32', use_last_error=True)
gdi = C.WinDLL('gdi32', use_last_error=True)
LRESULT = C.c_ssize_t
WNDPROC = C.WINFUNCTYPE(LRESULT, W.HWND, W.UINT, W.WPARAM, W.LPARAM)
ENUMPROC = C.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)


def bind(dll, name, result, *arguments):
    fn = getattr(dll,name)
    fn.restype,fn.argtypes = result,list(arguments)
    return fn


snapshot = bind(kernel,'CreateToolhelp32Snapshot',W.HANDLE,W.DWORD,W.DWORD)
close_handle = bind(kernel,'CloseHandle',W.BOOL,W.HANDLE)
open_process = bind(kernel,'OpenProcess',W.HANDLE,W.DWORD,W.BOOL,W.DWORD)
read_process = bind(kernel,'ReadProcessMemory',W.BOOL,W.HANDLE,C.c_void_p,C.c_void_p,C.c_size_t,C.POINTER(C.c_size_t))
get_exit_code = bind(kernel,'GetExitCodeProcess',W.BOOL,W.HANDLE,C.POINTER(W.DWORD))
get_module_handle = bind(kernel,'GetModuleHandleW',W.HMODULE,W.LPCWSTR)
foreground = bind(user,'GetForegroundWindow',W.HWND)
window_pid = bind(user,'GetWindowThreadProcessId',W.DWORD,W.HWND,C.POINTER(W.DWORD))
is_visible = bind(user,'IsWindowVisible',W.BOOL,W.HWND)
is_iconic = bind(user,'IsIconic',W.BOOL,W.HWND)
get_window = bind(user,'GetWindow',W.HWND,W.HWND,W.UINT)
get_client_rect = bind(user,'GetClientRect',W.BOOL,W.HWND,C.POINTER(W.RECT))
client_to_screen = bind(user,'ClientToScreen',W.BOOL,W.HWND,C.POINTER(W.POINT))
enum_windows = bind(user,'EnumWindows',W.BOOL,ENUMPROC,W.LPARAM)
key_state = bind(user,'GetAsyncKeyState',C.c_short,C.c_int)


class PROCESSENTRY(C.Structure):
    _fields_ = [('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',C.c_size_t),
                ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),
                ('priority',W.LONG),('flags',W.DWORD),('exe',W.WCHAR*260)]


class MODULEENTRY(C.Structure):
    _fields_ = [('size',W.DWORD),('module_id',W.DWORD),('pid',W.DWORD),
                ('global_usage',W.DWORD),('process_usage',W.DWORD),('base',C.POINTER(W.BYTE)),
                ('image_size',W.DWORD),('module',W.HMODULE),('name',W.WCHAR*256),('path',W.WCHAR*260)]


process_first = bind(kernel,'Process32FirstW',W.BOOL,W.HANDLE,C.POINTER(PROCESSENTRY))
process_next = bind(kernel,'Process32NextW',W.BOOL,W.HANDLE,C.POINTER(PROCESSENTRY))
module_first = bind(kernel,'Module32FirstW',W.BOOL,W.HANDLE,C.POINTER(MODULEENTRY))
module_next = bind(kernel,'Module32NextW',W.BOOL,W.HANDLE,C.POINTER(MODULEENTRY))


def enumerate_snapshot(flags,pid,structure,first,next_fn):
    handle = snapshot(flags,pid)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        entry = structure()
        entry.size = C.sizeof(entry)
        ok = first(handle,C.byref(entry))
        while ok:
            yield structure.from_buffer_copy(entry)
            ok = next_fn(handle,C.byref(entry))
        if C.get_last_error() != 18:  # ERROR_NO_MORE_FILES
            raise C.WinError(C.get_last_error())
    finally:
        close_handle(handle)


def find_game():
    entries = enumerate_snapshot(2,0,PROCESSENTRY,process_first,process_next)
    try:
        for entry in entries:
            if entry.exe.casefold() == 'cs2.exe':
                return entry.pid
        return None
    finally:
        entries.close()


def client_module(pid):
    entries = enumerate_snapshot(0x18,pid,MODULEENTRY,module_first,module_next)
    try:
        for entry in entries:
            if entry.name.casefold() == 'client.dll':
                return C.cast(entry.base,C.c_void_p).value,entry.image_size
        raise ReadError('client.dll is not loaded.')
    finally:
        entries.close()


class Process:
    def __init__(self,pid):
        # No write, thread-creation, or injection access is requested.
        self.handle = open_process(0x1000 | 0x10,False,pid)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        self.pid = pid

    def close(self):
        if self.handle:
            close_handle(self.handle)
            self.handle = None

    def alive(self):
        code = W.DWORD()
        return bool(self.handle and get_exit_code(self.handle,C.byref(code)) and code.value == 259)

    def read(self,address,size):
        if not self.handle or not 0 < size <= 65536 or not valid_pointer(address & ~7) or address+size >= 0x00007FFFFFFF0000:
            raise ReadError('Invalid memory range.')
        buffer = C.create_string_buffer(size)
        actual = C.c_size_t()
        if not read_process(self.handle,C.c_void_p(address),buffer,size,C.byref(actual)) or actual.value != size:
            raise ReadError('ReadProcessMemory failed or returned partial data.')
        return buffer.raw


def game_window(pid):
    found = []
    @ENUMPROC
    def visit(hwnd,_):
        owner = W.DWORD()
        window_pid(hwnd,C.byref(owner))
        if owner.value == pid and is_visible(hwnd) and not get_window(hwnd,4):
            rect = W.RECT()
            if get_client_rect(hwnd,C.byref(rect)) and rect.right > 100 and rect.bottom > 100:
                found.append((rect.right*rect.bottom,hwnd))
        return True
    enum_windows(visit,0)
    return max(found,key=lambda item:item[0])[1] if found else None


def focused(hwnd,pid):
    actual = W.DWORD()
    if not hwnd or foreground() != hwnd or is_iconic(hwnd):
        return False
    window_pid(hwnd,C.byref(actual))
    return actual.value == pid


def held(vk):
    return bool(key_state(vk) & 0x8000)


class MOUSEINPUT(C.Structure):
    _fields_ = [('dx',W.LONG),('dy',W.LONG),('data',W.DWORD),('flags',W.DWORD),
                ('time',W.DWORD),('extra',C.c_size_t)]


class KEYBDINPUT(C.Structure):
    _fields_ = [('vk',W.WORD),('scan',W.WORD),('flags',W.DWORD),('time',W.DWORD),('extra',C.c_size_t)]


class HARDWAREINPUT(C.Structure):
    _fields_ = [('message',W.DWORD),('low',W.WORD),('high',W.WORD)]


class INPUT_UNION(C.Union):
    _fields_ = [('mouse',MOUSEINPUT),('key',KEYBDINPUT),('hardware',HARDWAREINPUT)]


class INPUT(C.Structure):
    _fields_ = [('type',W.DWORD),('value',INPUT_UNION)]


send_input = bind(user,'SendInput',W.UINT,W.UINT,C.POINTER(INPUT),C.c_int)


def mouse(flags,dx=0,dy=0):
    event = INPUT()
    event.type = 0
    event.value.mouse = MOUSEINPUT(dx,dy,0,flags,0,0)
    return event


def keyboard(vk,up=False):
    event = INPUT()
    event.type = 1
    event.value.key = KEYBDINPUT(vk,0,2 if up else 0,0,0)
    return event


def emit(events,hwnd,pid):
    if not events or not focused(hwnd,pid):
        return
    if C.sizeof(INPUT) != 40:
        raise OSError('Expected the 64-bit Windows INPUT layout.')
    array = (INPUT*len(events))(*events)
    count = send_input(len(events),array,C.sizeof(INPUT))
    if count != len(events):
        # A partial batch can contain a button-down; always attempt releases.
        releases = (INPUT*2)(mouse(4),keyboard(0x20,True))
        send_input(2,releases,C.sizeof(INPUT))
        raise OSError('SendInput failed/was blocked. Input automation stopped.')


class WNDCLASS(C.Structure):
    _fields_ = [('style',W.UINT),('procedure',WNDPROC),('class_extra',C.c_int),
                ('window_extra',C.c_int),('instance',W.HINSTANCE),('icon',W.HICON),
                ('cursor',W.HANDLE),('background',W.HBRUSH),('menu',W.LPCWSTR),('name',W.LPCWSTR)]


class PAINTSTRUCT(C.Structure):
    _fields_ = [('dc',W.HDC),('erase',W.BOOL),('rect',W.RECT),('restore',W.BOOL),
                ('update',W.BOOL),('reserved',W.BYTE*32)]


register_class = bind(user,'RegisterClassW',W.ATOM,C.POINTER(WNDCLASS))
unregister_class = bind(user,'UnregisterClassW',W.BOOL,W.LPCWSTR,W.HINSTANCE)
create_window = bind(user,'CreateWindowExW',W.HWND,W.DWORD,W.LPCWSTR,W.LPCWSTR,W.DWORD,
                     C.c_int,C.c_int,C.c_int,C.c_int,W.HWND,W.HMENU,W.HINSTANCE,C.c_void_p)
def_window_proc = bind(user,'DefWindowProcW',LRESULT,W.HWND,W.UINT,W.WPARAM,W.LPARAM)
destroy_window = bind(user,'DestroyWindow',W.BOOL,W.HWND)
show_window = bind(user,'ShowWindow',W.BOOL,W.HWND,C.c_int)
set_position = bind(user,'SetWindowPos',W.BOOL,W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT)
set_layered = bind(user,'SetLayeredWindowAttributes',W.BOOL,W.HWND,W.DWORD,W.BYTE,W.DWORD)
peek_message = bind(user,'PeekMessageW',W.BOOL,C.POINTER(W.MSG),W.HWND,W.UINT,W.UINT,W.UINT)
translate_message = bind(user,'TranslateMessage',W.BOOL,C.POINTER(W.MSG))
dispatch_message = bind(user,'DispatchMessageW',LRESULT,C.POINTER(W.MSG))
invalidate = bind(user,'InvalidateRect',W.BOOL,W.HWND,C.POINTER(W.RECT),W.BOOL)
update_window = bind(user,'UpdateWindow',W.BOOL,W.HWND)
begin_paint = bind(user,'BeginPaint',W.HDC,W.HWND,C.POINTER(PAINTSTRUCT))
end_paint = bind(user,'EndPaint',W.BOOL,W.HWND,C.POINTER(PAINTSTRUCT))
fill_rect = bind(user,'FillRect',C.c_int,W.HDC,C.POINTER(W.RECT),W.HBRUSH)
compatible_dc = bind(gdi,'CreateCompatibleDC',W.HDC,W.HDC)
compatible_bitmap = bind(gdi,'CreateCompatibleBitmap',W.HBITMAP,W.HDC,C.c_int,C.c_int)
select_object = bind(gdi,'SelectObject',W.HGDIOBJ,W.HDC,W.HGDIOBJ)
delete_object = bind(gdi,'DeleteObject',W.BOOL,W.HGDIOBJ)
delete_dc = bind(gdi,'DeleteDC',W.BOOL,W.HDC)
stock_object = bind(gdi,'GetStockObject',W.HGDIOBJ,C.c_int)
create_pen = bind(gdi,'CreatePen',W.HPEN,C.c_int,C.c_int,W.DWORD)
move_to = bind(gdi,'MoveToEx',W.BOOL,W.HDC,C.c_int,C.c_int,C.POINTER(W.POINT))
line_to = bind(gdi,'LineTo',W.BOOL,W.HDC,C.c_int,C.c_int)
text_color = bind(gdi,'SetTextColor',W.DWORD,W.HDC,W.DWORD)
bg_mode = bind(gdi,'SetBkMode',C.c_int,W.HDC,C.c_int)
text_out = bind(gdi,'TextOutW',W.BOOL,W.HDC,C.c_int,C.c_int,W.LPCWSTR,C.c_int)
bit_blt = bind(gdi,'BitBlt',W.BOOL,W.HDC,C.c_int,C.c_int,C.c_int,C.c_int,W.HDC,C.c_int,C.c_int,W.DWORD)
ellipse = bind(gdi,'Ellipse',W.BOOL,W.HDC,C.c_int,C.c_int,C.c_int,C.c_int)


def rgb(r,g,b):
    return r | g<<8 | b<<16


PURPLE,GREEN,ORANGE,WHITE,BLUE = (rgb(*v) for v in ((185,160,255),(139,215,158),(225,163,111),(231,229,239),(135,180,230)))


class Overlay:
    def __init__(self):
        try:
            bind(user,'SetProcessDpiAwarenessContext',W.BOOL,C.c_void_p)(C.c_void_p(-4))
        except AttributeError:
            bind(user,'SetProcessDPIAware',W.BOOL)()
        self.frame,self.config,self.error = None,None,None
        self.width,self.height = 1,1
        self.instance = get_module_handle(None)
        self.class_name = 'PhantomNative_' + str(os.getpid())
        self.callback = WNDPROC(self.procedure)
        self.window_class = WNDCLASS()
        self.window_class.procedure = self.callback
        self.window_class.instance = self.instance
        self.window_class.name = self.class_name
        if not register_class(C.byref(self.window_class)):
            raise C.WinError(C.get_last_error())
        self.hwnd = create_window(0x080800A8,self.class_name,'Phantom native overlay',0x80000000,
                                  0,0,1,1,None,None,self.instance,None)
        if not self.hwnd:
            unregister_class(self.class_name,self.instance)
            raise C.WinError(C.get_last_error())
        if not set_layered(self.hwnd,0,255,1):
            self.close()
            raise C.WinError(C.get_last_error())

    def close(self):
        if self.hwnd:
            destroy_window(self.hwnd)
            self.hwnd = None
            unregister_class(self.class_name,self.instance)

    def procedure(self,hwnd,message,wparam,lparam):
        if message == 0x14:  # WM_ERASEBKGND: paint uses a back buffer.
            return 1
        if message == 0x84:  # HTTRANSPARENT
            return -1
        if message == 0xF:
            paint = PAINTSTRUCT()
            dc = begin_paint(hwnd,C.byref(paint))
            try:
                if dc:
                    self.paint(dc)
            except Exception as error:
                self.error = error
            finally:
                end_paint(hwnd,C.byref(paint))
            return 0
        return def_window_proc(hwnd,message,wparam,lparam)

    def pump(self):
        message = W.MSG()
        while peek_message(C.byref(message),None,0,0,1):
            if message.message == 0x12:
                return False
            translate_message(C.byref(message))
            dispatch_message(C.byref(message))
        if self.error:
            raise RuntimeError('Overlay rendering failed.') from self.error
        return True

    def hide(self):
        self.frame = None
        show_window(self.hwnd,0)

    def present(self,game,frame,config):
        rect,origin = W.RECT(),W.POINT(0,0)
        if not get_client_rect(game,C.byref(rect)) or not client_to_screen(game,C.byref(origin)):
            self.hide()
            return
        if rect.right <= 0 or rect.bottom <= 0:
            self.hide()
            return
        self.width,self.height = rect.right,rect.bottom
        self.frame,self.config = frame,config
        if not set_position(self.hwnd,W.HWND(-1),origin.x,origin.y,self.width,self.height,0x10 | 0x40):
            raise C.WinError(C.get_last_error())
        invalidate(self.hwnd,None,False)
        update_window(self.hwnd)

    def paint(self,screen):
        dc = compatible_dc(screen)
        if not dc:
            raise C.WinError(C.get_last_error())
        bitmap = compatible_bitmap(screen,self.width,self.height)
        if not bitmap:
            delete_dc(dc)
            raise C.WinError(C.get_last_error())
        previous = select_object(dc,bitmap)
        try:
            rect = W.RECT(0,0,self.width,self.height)
            fill_rect(dc,C.byref(rect),stock_object(4))  # BLACK_BRUSH, the color key.
            if self.frame and self.config:
                self.draw(dc)
            if not bit_blt(screen,0,0,self.width,self.height,dc,0,0,0x00CC0020):
                raise C.WinError(C.get_last_error())
        finally:
            select_object(dc,previous)
            delete_object(bitmap)
            delete_dc(dc)

    def line(self,dc,a,b,color,width=1):
        pen = create_pen(0,width,color)
        if not pen:
            raise C.WinError(C.get_last_error())
        old = select_object(dc,pen)
        try:
            move_to(dc,round(a[0]),round(a[1]),None)
            line_to(dc,round(b[0]),round(b[1]))
        finally:
            select_object(dc,old)
            delete_object(pen)

    def text(self,dc,x,y,message,color=WHITE):
        bg_mode(dc,1)
        text_color(dc,color)
        text_out(dc,round(x),round(y),message,len(message.encode('utf-16-le'))//2)

    def draw(self,dc):
        frame,config,w,h = self.frame,self.config,self.width,self.height
        self.text(dc,18,16,f'PHANTOM | ESP {"ON" if config.esp else "OFF"} | AIM {config.aim.upper()} | TRIGGER {"ON" if config.trigger else "OFF"}',PURPLE)
        self.text(dc,18,35,'F6 ESP / F7 aim / F8 trigger / F9 reload / F10 save / End exit')
        for actor in frame.actors:
            meters = distance(frame.local.position,actor.position)*.0254
            if meters > config.max_distance_m or (actor.team == frame.local.team and not config.teammates):
                continue
            color = BLUE if actor.team == frame.local.team else GREEN if actor.spotted is True else ORANGE if actor.spotted is False else WHITE
            if config.esp:
                bones = {key:project(value,frame.matrix,w,h) for key,value in actor.bones.items()}
                from .esp_style import player_commands, actor_color, Line
                commands = player_commands(bones,actor.name,meters,actor.health,actor.armor,
                                           actor.spotted,actor.team == frame.local.team,config)
                for command in commands:
                    value = command.color
                    native_color = rgb(*(int(value[i:i+2],16) for i in (1,3,5)))
                    if isinstance(command,Line):
                        self.line(dc,command.start,command.end,native_color,command.width)
                    else:
                        self.text(dc,*command.at,command.text,native_color)
                # Keep the existing read-failure boundary: no invented skeleton.
                if not commands and not any(point is not None for point in bones.values()):
                    origin = project(actor.position,frame.matrix,w,h)
                    if origin:
                        label = ' '.join(part for part in (
                            actor.name if config.esp_style['names'] else '',
                            f'{meters:.0f}m' if config.esp_style['distance'] else '',
                            f'HP {actor.health}' if config.health else '',
                            f'AR {actor.armor}' if config.armor else '') if part)
                        value = actor_color(config,actor.spotted,actor.team==frame.local.team)
                        if label:
                            self.text(dc,*origin,label,rgb(*(int(value[i:i+2],16) for i in (1,3,5))))
        if config.radar:
            self.draw_radar(dc)
        if config.spectators:
            self.text(dc,w-260,55,f'Spectating you: {len(frame.spectators)}',PURPLE)
            for i,name in enumerate(frame.spectators[:16]):
                self.text(dc,w-260,75+i*17,name)
        self.text(dc,18,h-30,'Color = spotted-mask proxy, NOT map ray visibility. Bones/layout are build-dependent.',ORANGE)

    def draw_radar(self,dc):
        frame,config = self.frame,self.config
        cx,cy,radius = 112,170,88
        pen = create_pen(0,1,PURPLE)
        if not pen:
            raise C.WinError(C.get_last_error())
        old_pen = select_object(dc,pen)
        old_brush = select_object(dc,stock_object(5))  # NULL_BRUSH
        try:
            ellipse(dc,cx-radius,cy-radius,cx+radius,cy+radius)
        finally:
            select_object(dc,old_pen)
            select_object(dc,old_brush)
            delete_object(pen)
        self.line(dc,(cx-radius,cy),(cx+radius,cy),PURPLE)
        self.line(dc,(cx,cy-radius),(cx,cy+radius),PURPLE)
        self.text(dc,cx-4,cy-8,'^',WHITE)
        yaw = math.radians(frame.angles[1])
        for actor in frame.actors:
            if actor.team == frame.local.team and not config.teammates:
                continue
            dx,dy = actor.position[0]-frame.local.position[0],actor.position[1]-frame.local.position[1]
            if math.hypot(dx,dy)*.0254 > config.max_distance_m:
                continue
            scale = (radius-9)*.0254/config.max_distance_m
            x = cx+(-math.sin(yaw)*dx+math.cos(yaw)*dy)*scale
            y = cy-(math.cos(yaw)*dx+math.sin(yaw)*dy)*scale
            color = BLUE if actor.team == frame.local.team else GREEN if actor.spotted is True else ORANGE
            self.line(dc,(x-2,y),(x+3,y),color,4)
