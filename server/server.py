# -*- coding: utf-8 -*-
"""
远程控制服务器端 - Windows 11 (RustDesk风格)
功能: ID注册中心，处理连接请求，中继转发
"""

import socket
import struct
import threading
import time
import io
import os
import sys
import platform
import hashlib
import json
import qrcode
import base64
from datetime import datetime
from uuid import uuid4

# 屏幕捕获和控制
try:
    import mss
    import numpy as np
    import pyautogui
    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0
except ImportError:
    pass

# 图形界面
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from PIL import Image, ImageTk, ImageDraw

# ============== 配置 ==============
DEFAULT_PORT = 21115  # 注册服务端口
RELAY_PORT = 21116    # 中继服务端口
BUFFER_SIZE = 65536
HEARTBEAT_INTERVAL = 30

# ============== 全局变量 ==============
register_server = None
relay_server = None
running = False
clients_registry = {}  # client_id -> {socket, info}
remote_desktop_sessions = {}  # viewer_id -> (host_id, relay_socket)
log_callback = None

# ============== 心跳检查函数 ==============
def heartbeat_checker(registered_clients, interval=30, timeout=90):
    """定期检查客户端心跳"""
    while running:
        time.sleep(interval)
        current_time = time.time()
        disconnected = []
        
        for client_id, data in registered_clients.items():
            last_heartbeat = data.get("last_heartbeat", 0)
            if current_time - last_heartbeat > timeout:
                disconnected.append(client_id)
        
        for client_id in disconnected:
            if client_id in registered_clients:
                try:
                    registered_clients[client_id]["socket"].close()
                except:
                    pass
                del registered_clients[client_id]
                log(f"心跳超时移除: {client_id}")

# ============== 日志系统 ==============
def log(message, level="INFO"):
    """日志输出"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_message = f"[{timestamp}] [{level}] {message}"
    print(log_message)
    if log_callback:
        log_callback(log_message)

# ============== ID生成器 ==============
class IDGenerator:
    """ID生成器 - 生成6位数字ID"""
    
    @staticmethod
    def generate():
        """生成唯一ID"""
        # 基于时间和随机数生成
        random_part = uuid4().fields[0] % 900000
        return str(100000 + random_part)
    
    @staticmethod
    def validate(client_id):
        """验证ID格式"""
        return client_id.isdigit() and len(client_id) == 6

# ============== 屏幕捕获 ==============
class ScreenCapture:
    """屏幕捕获类"""
    
    def __init__(self):
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        self.quality = 50
        
    def capture(self):
        """捕获屏幕"""
        try:
            screenshot = self.sct.grab(self.monitor)
            img = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
            output = io.BytesIO()
            img.save(output, format='JPEG', quality=self.quality)
            return output.getvalue()
        except Exception as e:
            log(f"屏幕捕获失败: {e}", "ERROR")
            return None
    
    def get_screen_size(self):
        """获取屏幕分辨率"""
        try:
            return self.monitor["width"], self.monitor["height"]
        except:
            return 1920, 1080
    
    def close(self):
        """关闭"""
        try:
            self.sct.close()
        except:
            pass

# ============== 输入控制 ==============
class InputController:
    """输入控制类"""
    
    @staticmethod
    def move_mouse(x, y):
        try:
            pyautogui.moveTo(int(x), int(y), duration=0)
            return True
        except:
            return False
    
    @staticmethod
    def click(button="left"):
        try:
            if button == "left":
                pyautogui.click()
            elif button == "right":
                pyautogui.click(button='right')
            elif button == "double":
                pyautogui.doubleClick()
            return True
        except:
            return False
    
    @staticmethod
    def scroll(clicks):
        try:
            pyautogui.scroll(int(clicks))
            return True
        except:
            return False
    
    @staticmethod
    def key_press(key):
        try:
            pyautogui.press(key)
            return True
        except:
            return False
    
    @staticmethod
    def type_text(text):
        try:
            pyautogui.write(text, interval=0.01)
            return True
        except:
            return False

# ============== 协议处理 ==============
class Protocol:
    """通信协议"""
    
    # 消息类型
    MSG_REGISTER = 1           # 注册
    MSG_LIST = 2               # 获取在线列表
    MSG_CONNECT = 3           # 请求连接
    MSG_DISCONNECT = 4         # 断开连接
    MSG_SCREEN_INFO = 10      # 屏幕信息
    MSG_SCREEN_DATA = 11       # 屏幕数据
    MSG_MOUSE_MOVE = 20        # 鼠标移动
    MSG_MOUSE_CLICK = 21      # 鼠标点击
    MSG_MOUSE_SCROLL = 22     # 鼠标滚动
    MSG_KEY_PRESS = 23         # 按键
    MSG_TEXT_INPUT = 24        # 文本输入
    MSG_PING = 99              # 心跳
    
    @staticmethod
    def pack(msg_type, data):
        """打包消息"""
        payload = json.dumps(data).encode('utf-8')
        header = struct.pack("!BI", msg_type, len(payload))
        return header + payload
    
    @staticmethod
    def unpack_header(sock):
        """接收消息头"""
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
        """接收消息体"""
        payload = b''
        while len(payload) < payload_len:
            packet = sock.recv(min(payload_len - len(payload), BUFFER_SIZE))
            if not packet:
                return None
            payload += packet
        return json.loads(payload.decode('utf-8'))

# ============== 注册服务器 ==============
class RegisterServer:
    """注册服务器 - 管理客户端ID注册"""
    
    def __init__(self, port=DEFAULT_PORT):
        self.port = port
        self.socket = None
        self.registered_clients = {}  # client_id -> {socket, info, last_heartbeat}
        self.client_passwords = {}     # client_id -> password
        
    def start(self):
        """启动注册服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(50)
            log(f"注册服务启动: 端口 {self.port}")
            
            while running:
                try:
                    self.socket.settimeout(1.0)
                    try:
                        client_sock, addr = self.socket.accept()
                        threading.Thread(target=self.handle_client, 
                                       args=(client_sock,), daemon=True).start()
                    except socket.timeout:
                        continue
                except Exception as e:
                    if running:
                        log(f"注册服务异常: {e}", "ERROR")
        except Exception as e:
            log(f"注册服务启动失败: {e}", "ERROR")
    
    def handle_client(self, sock):
        """处理客户端请求"""
        client_id = None
        try:
            msg_type, payload_len = Protocol.unpack_header(sock)
            if payload_len is None:
                return
                
            payload = Protocol.recv_payload(sock, payload_len)
            
            if msg_type == Protocol.MSG_REGISTER:
                # 注册请求
                client_id = self.register_client(sock, payload)
                if client_id:
                    sock.sendall(Protocol.pack(Protocol.MSG_REGISTER, {
                        "status": "ok",
                        "client_id": client_id
                    }))
                    log(f"客户端注册: {client_id} @ {sock.getpeername()}")
                    
                    # 保持连接，处理心跳
                    self.heartbeat_loop(sock, client_id)
                    
            elif msg_type == Protocol.MSG_LIST:
                # 获取在线列表
                online = self.get_online_clients()
                sock.sendall(Protocol.pack(Protocol.MSG_LIST, {
                    "clients": online
                }))
                
            elif msg_type == Protocol.MSG_CONNECT:
                # 连接请求
                target_id = payload.get("target_id")
                password = payload.get("password", "")
                result = self.request_connect(client_id, target_id, password)
                sock.sendall(Protocol.pack(Protocol.MSG_CONNECT, result))
                
        except Exception as e:
            log(f"处理客户端异常: {e}", "ERROR")
        finally:
            if client_id:
                self.unregister_client(client_id)
            try:
                sock.close()
            except:
                pass
    
    def register_client(self, sock, info):
        """注册客户端"""
        # 生成新ID
        while True:
            client_id = IDGenerator.generate()
            if client_id not in self.registered_clients:
                break
        
        self.registered_clients[client_id] = {
            "socket": sock,
            "info": info,
            "last_heartbeat": time.time()
        }
        
        password = info.get("password", "")
        if password:
            self.client_passwords[client_id] = password
        
        return client_id
    
    def unregister_client(self, client_id):
        """注销客户端"""
        if client_id in self.registered_clients:
            del self.registered_clients[client_id]
            log(f"客户端断开: {client_id}")
    
    def heartbeat_loop(self, sock, client_id):
        """心跳维护"""
        while running and client_id in self.registered_clients:
            try:
                sock.settimeout(HEARTBEAT_INTERVAL + 5)
                try:
                    msg_type, payload_len = Protocol.unpack_header(sock)
                    if payload_len is None:
                        break
                    payload = Protocol.recv_payload(sock, payload_len)
                    
                    if msg_type == Protocol.MSG_PING:
                        self.registered_clients[client_id]["last_heartbeat"] = time.time()
                        sock.sendall(Protocol.pack(Protocol.MSG_PING, {"status": "ok"}))
                except socket.timeout:
                    break
            except Exception as e:
                break
        
        self.unregister_client(client_id)
    
    def get_online_clients(self):
        """获取在线客户端"""
        online = []
        for cid, data in self.registered_clients.items():
            info = data.get("info", {})
            online.append({
                "id": cid,
                "name": info.get("name", f"设备-{cid}"),
                "online": True
            })
        return online
    
    def request_connect(self, viewer_id, target_id, password):
        """请求连接"""
        if target_id not in self.registered_clients:
            return {"status": "error", "message": "目标不在线"}
        
        # 验证密码
        if target_id in self.client_passwords:
            if self.client_passwords[target_id] != password:
                return {"status": "error", "message": "密码错误"}
        
        return {
            "status": "ok",
            "relay_port": RELAY_PORT,
            "message": "请连接中继端口"
        }
    
    def stop(self):
        """停止"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

# ============== 中继服务器 ==============
class RelayServer:
    """中继服务器 - 转发远程控制数据"""
    
    def __init__(self, port=RELAY_PORT):
        self.port = port
        self.socket = None
        self.sessions = {}  # (host_id, viewer_id) -> {host_sock, viewer_sock}
        
    def start(self):
        """启动中继服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind(('0.0.0.0', self.port))
            self.socket.listen(50)
            log(f"中继服务启动: 端口 {self.port}")
            
            while running:
                try:
                    self.socket.settimeout(1.0)
                    try:
                        client_sock, addr = self.socket.accept()
                        threading.Thread(target=self.handle_relay, 
                                       args=(client_sock,), daemon=True).start()
                    except socket.timeout:
                        continue
                except Exception as e:
                    if running:
                        log(f"中继服务异常: {e}", "ERROR")
        except Exception as e:
            log(f"中继服务启动失败: {e}", "ERROR")
    
    def handle_relay(self, sock):
        """处理中继连接"""
        try:
            # 接收连接信息
            msg_type, payload_len = Protocol.unpack_header(sock)
            if payload_len is None:
                sock.close()
                return
            
            info = Protocol.recv_payload(sock, payload_len)
            role = info.get("role")  # "host" or "viewer"
            host_id = info.get("host_id")
            viewer_id = info.get("viewer_id")
            
            if role == "host":
                # 主机等待连接
                log(f"主机 {host_id} 等待控制连接...")
                # 存储主机连接
                self.sessions[host_id] = {"host_sock": sock, "viewer_sock": None}
                
                # 等待 viewer 连接
                self.wait_for_viewer(host_id, viewer_id)
                
            elif role == "viewer":
                # viewer 连接
                self.connect_viewer(host_id, viewer_id, sock)
                
        except Exception as e:
            log(f"中继处理异常: {e}", "ERROR")
            sock.close()
    
    def wait_for_viewer(self, host_id, viewer_id):
        """等待viewer连接"""
        timeout = 60  # 60秒超时
        start = time.time()
        
        while running and time.time() - start < timeout:
            if host_id in self.sessions and self.sessions[host_id].get("viewer_sock"):
                log(f"viewer {viewer_id} 已连接 host {host_id}")
                self.relay_loop(host_id)
                break
            time.sleep(0.1)
        
        if host_id in self.sessions and not self.sessions[host_id].get("viewer_sock"):
            try:
                self.sessions[host_id]["host_sock"].close()
            except:
                pass
            del self.sessions[host_id]
    
    def connect_viewer(self, host_id, viewer_id, viewer_sock):
        """连接viewer到主机"""
        if host_id in self.sessions:
            self.sessions[host_id]["viewer_sock"] = viewer_sock
            # 通知主机
            try:
                host_sock = self.sessions[host_id]["host_sock"]
                host_sock.sendall(Protocol.pack(Protocol.MSG_CONNECT, {
                    "status": "ok",
                    "viewer_id": viewer_id
                }))
            except:
                pass
        else:
            viewer_sock.close()
    
    def relay_loop(self, host_id):
        """中继数据"""
        if host_id not in self.sessions:
            return
            
        session = self.sessions[host_id]
        host_sock = session["host_sock"]
        viewer_sock = session["viewer_sock"]
        
        if not host_sock or not viewer_sock:
            return
        
        # 双向转发
        def forward(src, dst, direction):
            try:
                while running:
                    data = src.recv(BUFFER_SIZE)
                    if not data:
                        break
                    dst.sendall(data)
            except:
                pass
        
        t1 = threading.Thread(target=forward, args=(host_sock, viewer_sock, "host->viewer"))
        t2 = threading.Thread(target=forward, args=(viewer_sock, host_sock, "viewer->host"))
        
        t1.daemon = True
        t2.daemon = True
        t1.start()
        t2.start()
        
        t1.join()
        t2.join()
        
        # 清理
        try:
            host_sock.close()
        except:
            pass
        try:
            viewer_sock.close()
        except:
            pass
        if host_id in self.sessions:
            del self.sessions[host_id]
        
        log(f"会话结束: host {host_id}")
    
    def stop(self):
        """停止"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass

# ============== 远程控制处理器 ==============
class RemoteControlHandler:
    """远程控制处理 - 替代原来的ClientHandler"""
    
    def __init__(self, sock, client_id):
        self.sock = sock
        self.client_id = client_id
        self.running = True
        self.screen_capture = None
        self.viewer_id = None
        
    def start(self):
        """开始处理"""
        try:
            # 等待连接请求
            msg_type, payload_len = Protocol.unpack_header(self.sock)
            if payload_len is None:
                return
                
            payload = Protocol.recv_payload(self.sock, payload_len)
            
            if payload.get("status") == "ok":
                self.viewer_id = payload.get("viewer_id")
                log(f"viewer {self.viewer_id} 已接管控制")
                self.init_screen_control()
                
        except Exception as e:
            log(f"远程控制异常: {e}", "ERROR")
        finally:
            self.running = False
            try:
                self.sock.close()
            except:
                pass
    
    def init_screen_control(self):
        """初始化屏幕控制"""
        self.screen_capture = ScreenCapture()
        
        while self.running:
            try:
                msg_type, payload_len = Protocol.unpack_header(self.sock)
                if payload_len is None:
                    break
                    
                payload = Protocol.recv_payload(self.sock, payload_len)
                self.handle_command(msg_type, payload)
                
            except Exception as e:
                log(f"控制处理异常: {e}", "ERROR")
                break
        
        if self.screen_capture:
            self.screen_capture.close()
    
    def handle_command(self, msg_type, payload):
        """处理控制命令"""
        if msg_type == Protocol.MSG_SCREEN_DATA:
            # 屏幕截图
            screen_data = self.screen_capture.capture()
            if screen_data:
                header = struct.pack("!I", len(screen_data))
                self.sock.sendall(header + screen_data)
            else:
                self.sock.sendall(struct.pack("!I", 0))
                
        elif msg_type == Protocol.MSG_SCREEN_INFO:
            # 屏幕信息
            w, h = self.screen_capture.get_screen_size()
            self.sock.sendall(Protocol.pack(Protocol.MSG_SCREEN_INFO, {
                "width": w,
                "height": h
            }))
            
        elif msg_type == Protocol.MSG_MOUSE_MOVE:
            InputController.move_mouse(payload.get("x", 0), payload.get("y", 0))
            
        elif msg_type == Protocol.MSG_MOUSE_CLICK:
            InputController.click(payload.get("button", "left"))
            
        elif msg_type == Protocol.MSG_MOUSE_SCROLL:
            InputController.scroll(payload.get("clicks", 0))
            
        elif msg_type == Protocol.MSG_KEY_PRESS:
            InputController.key_press(payload.get("key", ""))
            
        elif msg_type == Protocol.MSG_TEXT_INPUT:
            InputController.type_text(payload.get("text", ""))

# ============== 主服务器 ==============
class RemoteControlServer:
    """远程控制服务器"""
    
    def __init__(self, register_port=DEFAULT_PORT, relay_port=RELAY_PORT):
        self.register_port = register_port
        self.relay_port = relay_port
        self.register_server = RegisterServer(register_port)
        self.relay_server = RelayServer(relay_port)
        self.server_id = None
        self.server_password = ""
        
    def start(self):
        """启动服务器"""
        global running
        
        try:
            running = True
            
            # 生成服务器ID
            self.server_id = IDGenerator.generate()
            log(f"=== 服务器启动 ===")
            log(f"服务器ID: {self.server_id}")
            log(f"注册端口: {self.register_port}")
            log(f"中继端口: {self.relay_port}")
            log(f"本机IP: {self.get_local_ip()}")
            
            # 启动注册服务
            register_thread = threading.Thread(target=self.register_server.start, daemon=True)
            register_thread.start()
            
            # 启动心跳检查线程
            heartbeat_thread = threading.Thread(
                target=heartbeat_checker, 
                args=(self.register_server.registered_clients, HEARTBEAT_INTERVAL, HEARTBEAT_INTERVAL * 3),
                daemon=True
            )
            heartbeat_thread.start()
            
            # 启动中继服务
            relay_thread = threading.Thread(target=self.relay_server.start, daemon=True)
            relay_thread.start()
            
            # 等待
            while running:
                time.sleep(1)
                
        except Exception as e:
            log(f"服务器异常: {e}", "ERROR")
        finally:
            self.stop()
    
    def stop(self):
        """停止服务器"""
        global running
        running = False
        
        self.register_server.stop()
        self.relay_server.stop()
        
        log("服务器已停止")
    
    @staticmethod
    def get_local_ip():
        """获取本机IP"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def generate_qrcode(self):
        """生成二维码"""
        data = json.dumps({
            "id": self.server_id,
            "ip": self.get_local_ip(),
            "port": self.register_port
        })
        
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        return img

# ============== 图形界面 ==============
class ServerGUI:
    """服务器图形界面"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("RemoteLink 服务端")
        self.root.geometry("650x600")
        self.root.resizable(True, True)
        self.root.configure(bg="#1a1a2e")
        
        self.server = None
        self.server_thread = None
        self.qr_image = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """设置UI"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # 主框架
        main_frame = tk.Frame(self.root, bg="#1a1a2e")
        main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # 标题
        title = tk.Label(main_frame, text="RemoteLink", 
                         font=("微软雅黑", 24, "bold"),
                         bg="#1a1a2e", fg="#00d9ff")
        title.pack(pady=(0, 10))
        
        subtitle = tk.Label(main_frame, text="远程控制服务器", 
                            font=("微软雅黑", 12),
                            bg="#1a1a2e", fg="#888")
        subtitle.pack(pady=(0, 20))
        
        # ID显示卡片
        id_card = tk.Frame(main_frame, bg="#16213e", relief=tk.RAISED, bd=2)
        id_card.pack(fill=tk.X, pady=10)
        
        tk.Label(id_card, text="您的ID", font=("微软雅黑", 10),
                bg="#16213e", fg="#888").pack(pady=(15, 5))
        
        self.id_label = tk.Label(id_card, text="--------",
                                  font=("Consolas", 36, "bold"),
                                  bg="#16213e", fg="#00d9ff")
        self.id_label.pack(pady=5)
        
        tk.Label(id_card, text="将ID告诉您的伙伴，让他们连接您",
                font=("微软雅黑", 9), bg="#16213e", fg="#666").pack(pady=(5, 15))
        
        # 二维码区域
        qr_card = tk.Frame(main_frame, bg="#16213e", relief=tk.RAISED, bd=2)
        qr_card.pack(fill=tk.BOTH, expand=True, pady=10)
        
        tk.Label(qr_card, text="扫码连接", font=("微软雅黑", 10),
                bg="#16213e", fg="#888").pack(pady=10)
        
        self.qr_label = tk.Label(qr_card, bg="#16213e")
        self.qr_label.pack(pady=10)
        
        # 状态信息
        status_frame = tk.Frame(main_frame, bg="#1a1a2e")
        status_frame.pack(fill=tk.X, pady=10)
        
        self.status_label = tk.Label(status_frame, text="● 离线",
                                      font=("微软雅黑", 11),
                                      bg="#1a1a2e", fg="#ff4444")
        self.status_label.pack()
        
        self.ip_label = tk.Label(status_frame, text="",
                                  font=("Consolas", 10),
                                  bg="#1a1a2e", fg="#888")
        self.ip_label.pack()
        
        # 控制按钮
        btn_frame = tk.Frame(main_frame, bg="#1a1a2e")
        btn_frame.pack(pady=20)
        
        self.start_btn = tk.Button(btn_frame, text="启动服务",
                                    font=("微软雅黑", 12),
                                    bg="#00d9ff", fg="#000",
                                    padx=30, pady=10,
                                    relief=tk.FLAT, cursor="hand2",
                                    command=self.start_server)
        self.start_btn.pack(side=tk.LEFT, padx=10)
        
        self.stop_btn = tk.Button(btn_frame, text="停止服务",
                                   font=("微软雅黑", 12),
                                   bg="#ff4444", fg="#fff",
                                   padx=30, pady=10,
                                   relief=tk.FLAT, cursor="hand2",
                                   state=tk.DISABLED,
                                   command=self.stop_server)
        self.stop_btn.pack(side=tk.LEFT, padx=10)
        
        # 日志区域
        log_frame = tk.Frame(main_frame, bg="#0f0f23")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        tk.Label(log_frame, text="运行日志", font=("微软雅黑", 10),
                bg="#0f0f23", fg="#888").pack(anchor=tk.W, padx=10, pady=5)
        
        self.log_text = tk.Text(log_frame, height=8, 
                                  font=("Consolas", 9),
                                  bg="#0f0f23", fg="#00ff00",
                                  relief=tk.FLAT, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))
        
    def log(self, message):
        """添加日志"""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
        
        global log_callback
        log_callback = self.log
    
    def start_server(self):
        """启动服务器"""
        try:
            self.server = RemoteControlServer()
            self.server_thread = threading.Thread(target=self.server.start)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            # 更新UI
            self.root.after(500, self.update_ui)
            
        except Exception as e:
            messagebox.showerror("错误", f"启动失败:\n{e}")
    
    def update_ui(self):
        """更新UI"""
        if self.server and self.server.server_id:
            self.id_label.config(text=self.server.server_id)
            
            # 生成二维码
            try:
                qr_img = self.server.generate_qrcode()
                qr_img = qr_img.resize((200, 200))
                self.qr_photo = ImageTk.PhotoImage(qr_img)
                self.qr_label.config(image=self.qr_photo)
            except:
                pass
            
            self.status_label.config(text="● 在线", fg="#00ff00")
            self.ip_label.config(text=f"IP: {self.server.get_local_ip()} | 端口: {DEFAULT_PORT}")
            
            self.start_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
    
    def stop_server(self):
        """停止服务器"""
        if self.server:
            self.server.stop()
            self.server = None
            
        self.status_label.config(text="● 离线", fg="#ff4444")
        self.ip_label.config(text="")
        self.id_label.config(text="--------")
        self.qr_label.config(image="")
        
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
    
    def on_closing(self):
        """关闭时"""
        if self.server:
            if messagebox.askokcancel("退出", "确定要停止服务并退出吗?"):
                self.stop_server()
                self.root.destroy()
        else:
            self.root.destroy()
    
    def run(self):
        """运行"""
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.mainloop()

# ============== 主程序 ==============
if __name__ == "__main__":
    gui = ServerGUI()
    gui.run()
