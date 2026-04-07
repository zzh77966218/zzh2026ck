# -*- coding: utf-8 -*-
"""
远程控制客户端 - Android (RustDesk风格)
功能: 自动连接，扫码连接，远程控制
"""

import os
import sys
import socket
import struct
import threading
import time
import io
import json
import base64

# Kivy 相关
os.environ['KIVY_AUDIO'] = 'sdl2'
os.environ['KIVY_VIDEO'] = 'sdl2'

from kivy.config import Config
Config.set('graphics', 'orientation', 'portrait')
Config.set('kivy', 'exit_on_escape', '0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.widget import Widget
from kivy.properties import ObjectProperty, StringProperty, BooleanProperty, NumericProperty
from kivy.graphics import Color, Rectangle, Ellipse
from kivy.graphics.texture import Texture
from kivy.graphics.vertex_instructions import RoundedRectangle
from kivy.clock import Clock
from kivy.cache import Cache
from kivy.logger import Logger

from PIL import Image

# 二维码扫描相关
try:
    from pyzbar.pyzbar import decode as qr_decode
    from pyzbar.pyzbar import ZBarSymbol
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

# 尝试导入摄像头
try:
    from kivy.uix.camera import Camera
    HAS_KIVY_CAMERA = True
except ImportError:
    HAS_KIVY_CAMERA = False

# ============== 配置 ==============
DEFAULT_REGISTER_PORT = 21115
DEFAULT_RELAY_PORT = 21116
BUFFER_SIZE = 65536
HEARTBEAT_INTERVAL = 30

# ============== 协议定义 ==============
class Protocol:
    """通信协议"""
    MSG_REGISTER = 1
    MSG_LIST = 2
    MSG_CONNECT = 3
    MSG_DISCONNECT = 4
    MSG_SCREEN_INFO = 10
    MSG_SCREEN_DATA = 11
    MSG_MOUSE_MOVE = 20
    MSG_MOUSE_CLICK = 21
    MSG_MOUSE_SCROLL = 22
    MSG_KEY_PRESS = 23
    MSG_TEXT_INPUT = 24
    MSG_PING = 99
    
    @staticmethod
    def pack(msg_type, data):
        payload = json.dumps(data).encode('utf-8')
        header = struct.pack("!BI", msg_type, len(payload))
        return header + payload
    
    @staticmethod
    def unpack_header(sock):
        header = b''
        while len(header) < 5:
            packet = sock.recv(5 - len(header))
            if not packet:
                return None, None
            header += packet
        msg_type, payload_len = struct.unpack("!BI", header)
        return msg_type, payload_len
    
    @staticmethod
    def recv_payload(sock, payload_len):
        payload = b''
        while len(payload) < payload_len:
            packet = sock.recv(min(payload_len - len(payload), BUFFER_SIZE))
            if not packet:
                return None
            payload += packet
        return json.loads(payload.decode('utf-8'))

# ============== 连接管理 ==============
class ConnectionManager:
    """连接管理器"""
    
    def __init__(self):
        self.register_sock = None
        self.relay_sock = None
        self.connected = False
        self.my_id = None
        self.host_id = None
        self.viewer_id = None
        self.client_name = "Android"
        self.lock = threading.RLock()
        
    def connect_register(self, host, port, timeout=10):
        """连接注册服务器"""
        try:
            self.register_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.register_sock.settimeout(timeout)
            self.register_sock.connect((host, port))
            
            # 发送注册请求
            reg_data = {"name": self.client_name, "type": "mobile"}
            self.register_sock.sendall(Protocol.pack(Protocol.MSG_REGISTER, reg_data))
            
            # 接收响应
            msg_type, payload_len = Protocol.unpack_header(self.register_sock)
            if payload_len is None:
                return False, "无响应"
            
            response = Protocol.recv_payload(self.register_sock, payload_len)
            if response is None:
                return False, "无法解析响应"
            
            if response.get("status") == "ok":
                self.my_id = response.get("client_id")
                self.connected = True
                Logger.info(f"ConnectionManager: 注册成功，ID={self.my_id}")
                return True, "注册成功"
            else:
                return False, response.get("message", "注册被拒绝")
            
        except socket.timeout:
            return False, "连接超时"
        except Exception as e:
            return False, f"连接错误: {str(e)}"
    
    def get_online_clients(self):
        """获取在线客户端"""
        try:
            if not self.register_sock:
                return []
            
            self.register_sock.sendall(Protocol.pack(Protocol.MSG_LIST, {}))
            msg_type, payload_len = Protocol.unpack_header(self.register_sock)
            if payload_len is None:
                return []
            
            response = Protocol.recv_payload(self.register_sock, payload_len)
            if response:
                return response.get("clients", [])
            return []
        except Exception as e:
            Logger.error(f"ConnectionManager: 获取设备列表失败: {e}")
            return []
    
    def request_connect(self, target_id, password=""):
        """请求连接"""
        try:
            if not self.register_sock:
                return {"status": "error", "message": "未连接到注册服务器"}
            
            request = {"target_id": target_id, "password": password}
            self.register_sock.sendall(Protocol.pack(Protocol.MSG_CONNECT, request))
            
            msg_type, payload_len = Protocol.unpack_header(self.register_sock)
            if payload_len is None:
                return {"status": "error", "message": "无响应"}
            
            response = Protocol.recv_payload(self.register_sock, payload_len)
            if response:
                return response
            
            return {"status": "error", "message": "无响应"}
        except Exception as e:
            return {"status": "error", "message": f"请求失败: {str(e)}"}
    
    def connect_relay(self, host, port, role="viewer", timeout=30):
        """连接中继服务器"""
        try:
            self.relay_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.relay_sock.settimeout(timeout)
            self.relay_sock.connect((host, port))
            
            info = {
                "role": role,
                "host_id": self.host_id,
                "viewer_id": self.viewer_id or self.my_id
            }
            self.relay_sock.sendall(Protocol.pack(Protocol.MSG_REGISTER, info))
            
            # 等待连接确认
            msg_type, payload_len = Protocol.unpack_header(self.relay_sock)
            if payload_len is None:
                return False
            
            response = Protocol.recv_payload(self.relay_sock, payload_len)
            if response and response.get("status") == "ok":
                Logger.info(f"ConnectionManager: 中继连接成功，role={role}")
                return True
            
            return False
        except Exception as e:
            Logger.error(f"ConnectionManager: 中继连接异常: {e}")
            return False
    
    def recv_screen_data(self):
        """接收屏幕数据"""
        try:
            if not self.relay_sock:
                return None
            
            self.relay_sock.settimeout(5)
            header = self.relay_sock.recv(4)
            if not header or len(header) < 4:
                return None
            
            data_len = struct.unpack("!I", header)[0]
            if data_len == 0:
                return None
            
            data = b''
            while len(data) < data_len:
                packet = self.relay_sock.recv(min(data_len - len(data), BUFFER_SIZE))
                if not packet:
                    return None
                data += packet
            return data
        except socket.timeout:
            return None
        except Exception as e:
            Logger.error(f"ConnectionManager: 接收屏幕数据异常: {e}")
            return None
    
    def send_control(self, msg_type, data):
        """发送控制指令"""
        try:
            if self.relay_sock:
                self.relay_sock.sendall(Protocol.pack(msg_type, data))
                return True
        except Exception as e:
            Logger.error(f"ConnectionManager: 发送控制指令异常: {e}")
        return False
    
    def send_screen_request(self):
        """请求屏幕数据"""
        self.send_control(Protocol.MSG_SCREEN_DATA, {})
    
    def send_mouse_move(self, x, y):
        self.send_control(Protocol.MSG_MOUSE_MOVE, {"x": int(x), "y": int(y)})
    
    def send_mouse_click(self, button="left"):
        self.send_control(Protocol.MSG_MOUSE_CLICK, {"button": button})
    
    def send_scroll(self, clicks):
        self.send_control(Protocol.MSG_MOUSE_SCROLL, {"clicks": int(clicks)})
    
    def send_key_press(self, key):
        self.send_control(Protocol.MSG_KEY_PRESS, {"key": key})
    
    def send_text(self, text):
        self.send_control(Protocol.MSG_TEXT_INPUT, {"text": text})
    
    def heartbeat(self):
        """心跳"""
        try:
            if self.register_sock:
                self.register_sock.sendall(Protocol.pack(Protocol.MSG_PING, {}))
                return True
        except Exception as e:
            Logger.error(f"ConnectionManager: 心跳失败: {e}")
        return False
    
    def disconnect(self):
        """断开连接"""
        self.connected = False
        try:
            if self.relay_sock:
                self.relay_sock.close()
                self.relay_sock = None
        except:
            pass
        try:
            if self.register_sock:
                self.register_sock.close()
                self.register_sock = None
        except:
            pass
        Logger.info("ConnectionManager: 已断开连接")

# ============== 自定义控件 ==============
class RemoteScreenView(Widget):
    """远程屏幕显示"""
    
    texture = None
    remote_width = NumericProperty(1920)
    remote_height = NumericProperty(1080)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.touch_callback = None
        self.last_touch_pos = None
        self.last_touch_id = None
        
        with self.canvas:
            Color(0.15, 0.15, 0.2, 1)
            self.bg = Rectangle(pos=self.pos, size=self.size)
        
        self.bind(pos=self._update, size=self._update)
    
    def _update(self, *args):
        self.bg.pos = self.pos
        self.bg.size = self.size
    
    def update_texture(self, image_data):
        """更新显示图像"""
        try:
            if not image_data or len(image_data) == 0:
                return
                
            img = Image.open(io.BytesIO(image_data))
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 计算缩放比例，保持宽高比
            max_width = self.width - 20
            max_height = self.height - 20
            if max_width <= 0 or max_height <= 0:
                return
            
            scale_w = max_width / img.width
            scale_h = max_height / img.height
            scale = min(scale_w, scale_h, 1.0)  # 不放大
            
            new_width = int(img.width * scale)
            new_height = int(img.height * scale)
            
            img = img.resize((new_width, new_height), Image.LANCZOS)
            
            # 创建纹理
            buf = img.tobytes('raw', 'RGB')
            texture = Texture.create(size=img.size, colorfmt='rgb')
            texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
            texture.flip_vertical()
            
            self.texture = texture
            self.remote_width = img.width
            self.remote_height = img.height
            
            # 重新绘制
            self.canvas.clear()
            with self.canvas:
                Color(1, 1, 1, 1)
                pos = self.calc_pos((new_width, new_height))
                Rectangle(texture=texture, pos=pos, size=(new_width, new_height))
                
        except Exception as e:
            Logger.error(f"RemoteScreenView: 纹理更新失败: {e}")
    
    def calc_pos(self, img_size):
        """计算居中位置"""
        x = (self.width - img_size[0]) / 2
        y = (self.height - img_size[1]) / 2
        return x, y
    
    def get_remote_coords(self, touch_x, touch_y):
        """触摸坐标转换为远程坐标"""
        if not self.texture or self.remote_width <= 0 or self.remote_height <= 0:
            return 0, 0
        
        # 屏幕显示位置
        img_pos = self.calc_pos((self.remote_width, self.remote_height))
        
        # 相对于图像的位置
        img_x = touch_x - (self.pos[0] + img_pos[0])
        img_y = touch_y - (self.pos[1] + img_pos[1])
        
        # 确保在图像范围内
        if img_x < 0 or img_y < 0 or img_x >= self.remote_width or img_y >= self.remote_height:
            return None, None
        
        return int(img_x), int(img_y)
    
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.touch_callback:
            x, y = self.get_remote_coords(touch.x, touch.y)
            if x is not None and y is not None:
                self.last_touch_pos = (x, y)
                self.last_touch_id = touch.uid
                self.touch_callback('down', x, y)
                return True
        return False
    
    def on_touch_move(self, touch):
        if touch.uid == self.last_touch_id and self.collide_point(*touch.pos) and self.touch_callback:
            x, y = self.get_remote_coords(touch.x, touch.y)
            if x is not None and y is not None:
                self.touch_callback('move', x, y)
                return True
        return False
    
    def on_touch_up(self, touch):
        if touch.uid == self.last_touch_id and self.touch_callback:
            self.touch_callback('up', 0, 0)
            self.last_touch_id = None
            return True
        return False

# ============== 二维码扫描界面 ==============
class QRScanScreen(Screen):
    """二维码扫描界面"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app = App.get_running_app()
        self.scan_camera = None
        self.scan_running = False
        self.scan_event = None
        
        # 创建并添加布局
        layout = self.create_scan_layout()
        self.add_widget(layout)
        
    def on_enter(self):
        """进入界面时启动摄像头"""
        self.start_camera()
        
    def on_leave(self):
        """离开界面时停止摄像头"""
        self.stop_camera()
        
    def create_scan_layout(self):
        """创建扫描界面布局"""
        layout = BoxLayout(orientation='vertical', padding=0, spacing=0)
        layout.bind(size=self._update_bg)
        
        # 背景
        with layout.canvas.before:
            Color(0, 0, 0, 1)
            layout.bg_rect = Rectangle(pos=layout.pos, size=layout.size)
        
        # 顶部栏
        top_bar = BoxLayout(size_hint_y=0.1, padding=10)
        back_btn = Button(text='< 返回',
                          background_color=[0.3, 0.3, 0.4, 1],
                          size_hint_x=0.25,
                          on_press=lambda x: self.go_back())
        
        title_label = Label(text='扫码连接',
                            font_size='18sp',
                            color=[1, 1, 1, 1])
        
        top_bar.add_widget(back_btn)
        top_bar.add_widget(title_label)
        layout.add_widget(top_bar)
        
        # 摄像头区域
        self.camera_container = BoxLayout(size_hint_y=0.7)
        self.camera_placeholder = Label(text='[b]正在启动摄像头...[/b]',
                                        markup=True,
                                        font_size='16sp',
                                        color=[1, 1, 1, 1])
        self.camera_container.add_widget(self.camera_placeholder)
        layout.add_widget(self.camera_container)
        
        # 提示信息
        hint_label = Label(text='将二维码对准摄像头\n自动识别连接',
                          font_size='14sp',
                          color=[0.7, 0.7, 0.7, 1],
                          size_hint_y=0.1)
        layout.add_widget(hint_label)
        
        # 手动输入按钮
        manual_btn = Button(text='手动输入ID',
                           background_color=[0.2, 0.5, 0.8, 1],
                           font_size='14sp',
                           size_hint_y=0.1,
                           on_press=self.on_manual_input)
        layout.add_widget(manual_btn)
        
        return layout
    
    def _update_bg(self, instance, value):
        instance.bg_rect.size = instance.size
    
    def start_camera(self):
        """启动摄像头扫描"""
        self.scan_running = True
        
        # 移除占位符
        self.camera_container.clear_widgets()
        
        if HAS_KIVY_CAMERA and HAS_PYZBAR:
            try:
                # 尝试创建摄像头
                self.scan_camera = Camera(resolution=(640, 480), play=True)
                self.scan_camera_container = FloatLayout()
                self.scan_camera.size_hint = (1, 1)
                self.scan_camera.pos_hint = {'center_x': 0.5, 'center_y': 0.5}
                
                # 添加扫描框提示
                with self.scan_camera_container.canvas:
                    Color(0, 1, 0, 0.3)
                    # 扫描框边框
                    border_size = 250
                    self.scan_frame = Rectangle(
                        pos=(320 - border_size/2, 240 - border_size/2),
                        size=(border_size, border_size)
                    )
                
                self.scan_camera_container.add_widget(self.scan_camera)
                self.camera_container.add_widget(self.scan_camera_container)
                
                # 开始扫描
                self.scan_event = Clock.schedule_interval(self.check_qrcode, 0.5)
            except Exception as e:
                Logger.error(f"Camera error: {e}")
                self.show_fallback()
        else:
            self.show_fallback()
    
    def show_fallback(self):
        """显示备用输入界面"""
        self.camera_container.clear_widgets()
        
        if not HAS_PYZBAR:
            msg = '[b]无法扫描: 未安装pyzbar库[/b]\n\n请手动输入服务器ID'
        else:
            msg = '[b]无法启动摄像头[/b]\n\n请手动输入服务器ID'
        
        msg_label = Label(text=msg,
                         markup=True,
                         font_size='14sp',
                         color=[1, 1, 1, 1],
                         halign='center')
        self.camera_container.add_widget(msg_label)
    
    def stop_camera(self):
        """停止摄像头扫描"""
        self.scan_running = False
        if self.scan_event:
            self.scan_event.cancel()
            self.scan_event = None
        if self.scan_camera:
            self.scan_camera.play = False
            self.scan_camera = None
    
    def check_qrcode(self, dt):
        """检查二维码"""
        if not self.scan_running or not self.scan_camera:
            return
            
        try:
            # 从摄像头获取图像
            texture = self.scan_camera.texture
            if texture is None:
                return
                
            # 将纹理转换为PIL图像
            size = texture.size
            colorfmt = texture.colorfmt
            buf = texture.pixels
            
            # 创建PIL图像
            img = Image.frombytes(colorfmt='RGB', size=size, data=buf)
            
            # 尝试解码二维码
            decoded = qr_decode(img, symbols=[ZBarSymbol.QR_CODE])
            
            if decoded:
                qr_data = decoded[0].data.decode('utf-8')
                self.on_qr_scanned(qr_data)
                
        except Exception as e:
            Logger.error(f"QR scan error: {e}")
    
    def on_qr_scanned(self, qr_data):
        """二维码扫描成功"""
        self.stop_camera()
        
        try:
            # 解析二维码数据
            # 格式: {"id": "123456", "ip": "192.168.1.1", "port": 21115}
            data = json.loads(qr_data)
            target_id = data.get('id')
            
            if target_id:
                Clock.schedule_once(lambda dt: self.go_back_and_connect(target_id))
                return
        except:
            pass
        
        # 如果解析失败，显示错误
        Clock.schedule_once(lambda dt: self.show_error('无效的二维码'))
    
    def go_back_and_connect(self, target_id):
        """返回并连接"""
        self.app.target_id_input.text = target_id
        self.app.on_connect_pressed(None)
        self.app.screen_manager.current = 'home'
    
    def show_error(self, msg):
        """显示错误"""
        popup = Popup(title='错误',
                     content=Label(text=msg, font_size='14sp'),
                     size_hint=(0.8, 0.3))
        popup.open()
        Clock.schedule_once(lambda dt: self.start_camera(), 2)
    
    def on_manual_input(self, instance):
        """手动输入"""
        self.go_back()
    
    def go_back(self, *args):
        """返回主页"""
        self.app.screen_manager.current = 'home'

# ============== 界面定义 ==============
class HomeScreen(Screen):
    """主界面"""
    
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app

# ============== 主应用 ==============
class RemoteLinkApp(App):
    """远程控制应用"""
    
    connection = ObjectProperty(None)
    screen_manager = None
    
    # 屏幕
    home_screen = None
    control_screen = None
    
    # 状态
    connected_to_host = BooleanProperty(False)
    
    def build(self):
        """构建应用"""
        self.connection = ConnectionManager()
        
        # 主题颜色
        self.primary_color = [0, 0.85, 1, 1]  # 青色
        self.bg_color = [0.1, 0.1, 0.18, 1]
        self.card_color = [0.15, 0.15, 0.25, 1]
        
        # 创建屏幕管理器
        self.screen_manager = ScreenManager()
        
        # 主页面
        self.home_screen = HomeScreen(app=self, name='home')
        home_layout = self.create_home_layout()
        self.home_screen.add_widget(home_layout)
        self.screen_manager.add_widget(self.home_screen)
        
        # 控制页面
        self.control_screen = Screen(name='control')
        ctrl_layout = self.create_control_layout()
        self.control_screen.add_widget(ctrl_layout)
        self.screen_manager.add_widget(self.control_screen)
        
        # 扫描页面
        self.scan_screen = QRScanScreen(name='scan')
        self.screen_manager.add_widget(self.scan_screen)
        
        return self.screen_manager
    
    def create_home_layout(self):
        """创建主界面布局"""
        layout = BoxLayout(orientation='vertical', padding=20, spacing=15)
        layout.bind(size=self._update_bg)
        
        # 背景
        with layout.canvas.before:
            Color(*self.bg_color)
            layout.bg_rect = Rectangle(pos=layout.pos, size=layout.size)
        
        # Logo区域
        logo_frame = BoxLayout(orientation='vertical', size_hint_y=0.25)
        logo_title = Label(text='[b]RemoteLink[/b]',
                          markup=True, font_size='32sp',
                          color=self.primary_color, halign='center')
        logo_subtitle = Label(text='远程控制',
                             font_size='14sp', color=[0.6, 0.6, 0.6, 1])
        logo_frame.add_widget(logo_title)
        logo_frame.add_widget(logo_subtitle)
        layout.add_widget(logo_frame)
        
        # ID显示卡片
        id_card = BoxLayout(orientation='vertical',
                            size_hint_y=0.25,
                            padding=20)
        with id_card.canvas.before:
            Color(*self.card_color)
            id_card.rect = RoundedRectangle(pos=id_card.pos, size=id_card.size, radius=[15])
        
        id_label = Label(text='本机ID', font_size='12sp', color=[0.5, 0.5, 0.5, 1])
        self.my_id_label = Label(text='未连接', font_size='28sp', color=[1, 1, 1, 1])
        
        # ID输入区
        id_input_frame = BoxLayout(size_hint_y=0.25, padding=10)
        self.target_id_input = TextInput(hint_text='输入对方ID',
                                          multiline=False,
                                          font_size='20sp',
                                          halign='center',
                                          size_hint_x=0.7)
        connect_btn = Button(text='连接',
                             background_color=self.primary_color,
                             size_hint_x=0.3,
                             on_press=self.on_connect_pressed)
        
        id_input_frame.add_widget(self.target_id_input)
        id_input_frame.add_widget(connect_btn)
        
        id_card.add_widget(id_label)
        id_card.add_widget(self.my_id_label)
        id_card.add_widget(id_input_frame)
        layout.add_widget(id_card)
        
        # 扫码按钮
        scan_btn = Button(text='[b]📷 扫码连接[/b]',
                         markup=True,
                         font_size='16sp',
                         background_color=[0.2, 0.2, 0.3, 1],
                         size_hint_y=0.12,
                         on_press=self.on_scan_pressed)
        layout.add_widget(scan_btn)
        
        # 在线设备列表
        list_label = Label(text='在线设备', size_hint_y=0.08,
                          font_size='14sp', color=[0.6, 0.6, 0.6, 1],
                          halign='left')
        layout.add_widget(list_label)
        
        self.device_list = ScrollView(size_hint_y=0.25)
        self.device_list_content = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        self.device_list_content.bind(minimum_height=self.device_list_content.setter('height'))
        self.device_list.add_widget(self.device_list_content)
        layout.add_widget(self.device_list)
        
        # 状态
        self.status_label = Label(text='未连接',
                                   font_size='12sp',
                                   color=[1, 0.3, 0.3, 1],
                                   size_hint_y=0.05)
        layout.add_widget(self.status_label)
        
        return layout
    
    def _update_bg(self, instance, value):
        instance.bg_rect.size = instance.size
    
    def create_control_layout(self):
        """创建控制界面"""
        layout = BoxLayout(orientation='vertical', padding=10, spacing=10)
        
        # 顶部栏
        top_bar = BoxLayout(size_hint_y=0.08, padding=10)
        back_btn = Button(text='< 返回',
                          background_color=[0.3, 0.3, 0.4, 1],
                          size_hint_x=0.25,
                          on_press=lambda x: self.go_home())
        
        self.remote_id_label = Label(text='连接中...',
                                      font_size='14sp',
                                      color=[1, 1, 1, 1])
        
        top_bar.add_widget(back_btn)
        top_bar.add_widget(self.remote_id_label)
        layout.add_widget(top_bar)
        
        # 远程屏幕
        screen_frame = BoxLayout(size_hint_y=0.65)
        self.remote_screen = RemoteScreenView()
        self.remote_screen.touch_callback = self.on_touch_event
        screen_frame.add_widget(self.remote_screen)
        layout.add_widget(screen_frame)
        
        # 控制按钮
        ctrl_bar = BoxLayout(size_hint_y=0.12, spacing=10, padding=5)
        
        btn_style = {'font_size': '14sp', 'background_color': [0.2, 0.5, 0.8, 1]}
        
        left_btn = Button(text='左键', **btn_style)
        left_btn.bind(on_press=lambda x: self.on_control_button('left'))
        
        right_btn = Button(text='右键', **btn_style)
        right_btn.bind(on_press=lambda x: self.on_control_button('right'))
        
        dbl_btn = Button(text='双击', **btn_style)
        dbl_btn.bind(on_press=lambda x: self.on_control_button('double'))
        
        ctrl_bar.add_widget(left_btn)
        ctrl_bar.add_widget(right_btn)
        ctrl_bar.add_widget(dbl_btn)
        layout.add_widget(ctrl_bar)
        
        # 状态栏
        self.ctrl_status = Label(text='等待画面...',
                                  font_size='11sp',
                                  color=[0.5, 0.5, 0.5, 1],
                                  size_hint_y=0.05)
        layout.add_widget(self.ctrl_status)
        
        return layout
    
    def _update_card_rect(self, instance, value):
        instance.rect.pos = instance.pos
        instance.rect.size = instance.size
    
    def on_start(self):
        """应用启动"""
        # 自动连接本地服务器
        threading.Thread(target=self.auto_connect, daemon=True).start()
    
    def auto_connect(self):
        """自动连接"""
        # 尝试连接本地服务器
        local_ips = ['127.0.0.1', 'localhost']
        
        # 获取本机IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            local_ips.insert(0, local_ip)
        except:
            pass
        
        for ip in local_ips:
            Clock.schedule_once(lambda dt, h=ip: self.try_connect(h))
            time.sleep(1)
    
    def try_connect(self, host):
        """尝试连接"""
        success, msg = self.connection.connect_register(host, DEFAULT_REGISTER_PORT)
        
        Clock.schedule_once(lambda dt: self.update_connection_status(success, msg))
    
    def update_connection_status(self, success, msg):
        """更新连接状态"""
        if success:
            self.my_id_label.text = self.connection.my_id or '未知'
            self.my_id_label.color = [0, 1, 0.5, 1]
            self.status_label.text = f'已连接服务器'
            self.status_label.color = [0, 1, 0.5, 1]
            
            # 刷新设备列表
            self.refresh_device_list()
        else:
            self.my_id_label.text = '连接失败'
            self.my_id_label.color = [1, 0.3, 0.3, 1]
            self.status_label.text = f'请启动服务端或检查网络'
            self.status_label.color = [1, 0.3, 0.3, 1]
    
    def refresh_device_list(self):
        """刷新设备列表"""
        self.device_list_content.clear_widgets()
        
        devices = self.connection.get_online_clients()
        for device in devices:
            if device.get('id') != self.connection.my_id:
                btn = Button(text=f"{device.get('name', '设备')} ({device.get('id')})",
                            size_hint_y=None, height=50,
                            background_color=[0.2, 0.3, 0.4, 1],
                            on_press=lambda x, d=device: self.connect_to_device(d))
                self.device_list_content.add_widget(btn)
    
    def connect_to_device(self, device):
        """连接到设备"""
        device_id = device.get('id')
        if device_id:
            self.target_id_input.text = device_id
            self.on_connect_pressed(None)
    
    def on_connect_pressed(self, instance):
        """连接按钮"""
        target_id = self.target_id_input.text.strip()
        
        if not target_id:
            self.status_label.text = '请输入对方ID'
            return
        
        if not target_id.isdigit() or len(target_id) != 6:
            self.status_label.text = 'ID格式错误'
            return
        
        self.status_label.text = '正在连接...'
        self.status_label.color = [1, 1, 0, 1]
        
        threading.Thread(target=self._do_connect,
                        args=(target_id,), daemon=True).start()
    
    def _do_connect(self, target_id):
        """执行连接"""
        # 请求连接
        result = self.connection.request_connect(target_id)
        
        if result.get('status') == 'ok':
            # 连接中继服务器
            host = self.connection.register_sock.getpeername()[0]
            success = self.connection.connect_relay(host, DEFAULT_RELAY_PORT, "viewer")
            
            if success:
                self.connection.host_id = target_id
                Clock.schedule_once(lambda dt: self.start_control_mode(target_id))
            else:
                Clock.schedule_once(lambda dt: self.on_connect_failed("中继连接失败"))
        else:
            Clock.schedule_once(lambda dt: self.on_connect_failed(result.get('message', '连接失败')))
    
    def on_connect_failed(self, msg):
        """连接失败"""
        self.status_label.text = f'连接失败: {msg}'
        self.status_label.color = [1, 0.3, 0.3, 1]
    
    def start_control_mode(self, host_id):
        """开始控制模式"""
        self.connected_to_host = True
        self.remote_id_label.text = f'控制: {host_id}'
        self.ctrl_status.text = '已连接'
        
        # 切换界面
        self.screen_manager.current = 'control'
        
        # 开始接收屏幕
        threading.Thread(target=self.screen_receive_loop, daemon=True).start()
    
    def screen_receive_loop(self):
        """屏幕接收循环"""
        last_request_time = 0
        request_interval = 0.1  # 100ms请求一次
        
        while self.connected_to_host and self.connection.relay_sock:
            try:
                current_time = time.time()
                # 定期请求屏幕数据
                if current_time - last_request_time >= request_interval:
                    self.connection.send_screen_request()
                    last_request_time = current_time
                
                # 接收屏幕数据
                screen_data = self.connection.recv_screen_data()
                if screen_data:
                    Clock.schedule_once(lambda dt, d=screen_data: 
                                       self.remote_screen.update_texture(d))
                    self.ctrl_status.text = '已连接'
                    self.ctrl_status.color = [0, 1, 0.5, 1]
                else:
                    # 短暂延迟避免busy loop
                    time.sleep(0.05)
                    
            except Exception as e:
                Logger.error(f"RemoteLinkApp: 屏幕接收异常: {e}")
                break
        
        Clock.schedule_once(lambda dt: self.on_connection_lost())
    
    def on_touch_event(self, event_type, x, y):
        """触摸事件"""
        if not self.connected_to_host or not self.connection.relay_sock:
            return
        
        if event_type == 'move':
            self.connection.send_mouse_move(x, y)
        elif event_type == 'down':
            # 发送移动然后点击
            self.connection.send_mouse_move(x, y)
            time.sleep(0.05)
            self.connection.send_mouse_click('left')
        elif event_type == 'up':
            pass
    
    def on_control_button(self, action):
        """控制按钮"""
        if not self.connected_to_host or not self.connection.relay_sock:
            return
        
        if action == 'left':
            self.connection.send_mouse_click('left')
        elif action == 'right':
            self.connection.send_mouse_click('right')
        elif action == 'double':
            self.connection.send_mouse_click('left')
            time.sleep(0.1)
            self.connection.send_mouse_click('left')
    
    def on_connection_lost(self):
        """连接丢失"""
        self.connected_to_host = False
        
        self.ctrl_status.text = '连接已断开'
        self.ctrl_status.color = [1, 0.3, 0.3, 1]
        
        self.remote_id_label.text = '已断开'
        
        # 清理资源
        self.connection.disconnect()
        
        # 2秒后返回主界面
        time.sleep(2)
        Clock.schedule_once(lambda dt: self.go_home())
    
    def on_scan_pressed(self, instance):
        """扫码按钮"""
        # 跳转到扫描界面
        self.screen_manager.current = 'scan'
    
    def go_home(self):
        """返回主页"""
        self.connected_to_host = False
        
        try:
            self.connection.disconnect()
        except:
            pass
        
        self.screen_manager.current = 'home'
        self.status_label.text = '已断开'
        self.status_label.color = [1, 0.3, 0.3, 1]
        self.target_id_input.text = ''

# ============== 入口 ==============
if __name__ == '__main__':
    RemoteLinkApp().run()
