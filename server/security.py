# -*- coding: utf-8 -*-
"""
安全模块 - 处理加密、认证和令牌管理
"""

import hashlib
import hmac
import json
import secrets
import time
from datetime import datetime, timedelta

# ============== 配置 ==============
TOKEN_EXPIRY = 3600  # token过期时间（秒）
SECRET_KEY = "remotelink-secret-key-2026"  # 应该从环境变量读取


# ============== 密码加密 ==============
class PasswordManager:
    """密码管理"""
    
    @staticmethod
    def hash_password(password, salt=None):
        """哈希密码"""
        if salt is None:
            salt = secrets.token_hex(16)
        
        # 使用PBKDF2进行多次迭代哈希
        pwd_hash = hashlib.pbkdf2_hmac(
            'sha256',
            password.encode('utf-8'),
            salt.encode('utf-8'),
            100000  # 迭代次数
        )
        
        return f"{salt}${pwd_hash.hex()}"
    
    @staticmethod
    def verify_password(password, hash_value):
        """验证密码"""
        try:
            salt, pwd_hash = hash_value.split('$')
            new_hash = hashlib.pbkdf2_hmac(
                'sha256',
                password.encode('utf-8'),
                salt.encode('utf-8'),
                100000
            )
            return hmac.compare_digest(new_hash.hex(), pwd_hash)
        except:
            return False


# ============== 令牌管理 ==============
class TokenManager:
    """令牌管理"""
    
    def __init__(self, secret_key=SECRET_KEY):
        self.secret_key = secret_key
    
    def generate_token(self, client_id, expiry_time=None):
        """生成令牌"""
        if expiry_time is None:
            expiry_time = time.time() + TOKEN_EXPIRY
        
        # 创建令牌数据
        payload = {
            "client_id": client_id,
            "exp": expiry_time,
            "iat": time.time(),
            "nonce": secrets.token_hex(16)
        }
        
        # 序列化
        payload_str = json.dumps(payload, sort_keys=True)
        
        # 生成签名
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload_str.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # 返回令牌（payload.signature格式）
        token = f"{payload_str}|{signature}"
        return token
    
    def verify_token(self, token):
        """验证令牌"""
        try:
            parts = token.split('|')
            if len(parts) != 2:
                return None, "令牌格式无效"
            
            payload_str, signature = parts
            
            # 验证签名
            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                payload_str.encode('utf-8'),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(signature, expected_signature):
                return None, "签名验证失败"
            
            # 解析payload
            payload = json.loads(payload_str)
            
            # 检查过期时间
            if payload.get("exp", 0) < time.time():
                return None, "令牌已过期"
            
            return payload.get("client_id"), None
            
        except Exception as e:
            return None, f"令牌验证异常: {str(e)}"


# ============== 会话管理 ==============
class SessionManager:
    """会话管理"""
    
    def __init__(self):
        self.sessions = {}  # session_id -> {client_id, created_at, last_activity}
        self.max_inactive_time = 1800  # 30分钟无活动则过期
    
    def create_session(self, client_id):
        """创建会话"""
        session_id = secrets.token_hex(32)
        self.sessions[session_id] = {
            "client_id": client_id,
            "created_at": time.time(),
            "last_activity": time.time()
        }
        return session_id
    
    def get_client_id(self, session_id):
        """获取会话对应的客户端ID"""
        if session_id not in self.sessions:
            return None
        
        session = self.sessions[session_id]
        
        # 检查是否过期
        if time.time() - session["last_activity"] > self.max_inactive_time:
            del self.sessions[session_id]
            return None
        
        # 更新最后活动时间
        session["last_activity"] = time.time()
        return session["client_id"]
    
    def destroy_session(self, session_id):
        """销毁会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def cleanup_expired(self):
        """清理过期会话"""
        expired = []
        for session_id, session in list(self.sessions.items()):
            if time.time() - session["last_activity"] > self.max_inactive_time:
                expired.append(session_id)
        
        for session_id in expired:
            del self.sessions[session_id]
        
        return len(expired)


# ============== 数据完整性检查 ==============
class ChecksumManager:
    """数据完整性检查"""
    
    @staticmethod
    def calculate_checksum(data, secret_key=SECRET_KEY):
        """计算数据校验和"""
        if isinstance(data, str):
            data = data.encode('utf-8')
        
        checksum = hmac.new(
            secret_key.encode('utf-8'),
            data,
            hashlib.sha256
        ).hexdigest()
        return checksum
    
    @staticmethod
    def verify_checksum(data, checksum, secret_key=SECRET_KEY):
        """验证数据校验和"""
        expected_checksum = ChecksumManager.calculate_checksum(data, secret_key)
        return hmac.compare_digest(expected_checksum, checksum)


# ============== 速率限制 ==============
class RateLimiter:
    """速率限制"""
    
    def __init__(self, max_requests=100, time_window=60):
        """
        max_requests: 时间窗口内的最大请求数
        time_window: 时间窗口大小（秒）
        """
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = {}  # ip/client_id -> [timestamp, timestamp, ...] 
    
    def check_rate_limit(self, identifier):
        """检查是否超限"""
        now = time.time()
        
        if identifier not in self.requests:
            self.requests[identifier] = []
        
        # 清理过期的时间戳
        self.requests[identifier] = [
            ts for ts in self.requests[identifier]
            if now - ts < self.time_window
        ]
        
        # 检查是否超限
        if len(self.requests[identifier]) >= self.max_requests:
            return False
        
        # 记录新请求
        self.requests[identifier].append(now)
        return True
    
    def get_remaining(self, identifier):
        """获取剩余请求数"""
        now = time.time()
        if identifier not in self.requests:
            return self.max_requests
        
        count = len([ts for ts in self.requests[identifier] if now - ts < self.time_window])
        return max(0, self.max_requests - count)


if __name__ == "__main__":
    # 测试
    print("密码管理测试:")
    pwd_hash = PasswordManager.hash_password("test123")
    print(f"密码哈希: {pwd_hash}")
    print(f"验证结果: {PasswordManager.verify_password('test123', pwd_hash)}")
    
    print("\n令牌管理测试:")
    token_mgr = TokenManager()
    token = token_mgr.generate_token("client123")
    print(f"令牌: {token[:50]}...")
    client_id, error = token_mgr.verify_token(token)
    print(f"验证结果: client_id={client_id}, error={error}")
    
    print("\n会话管理测试:")
    session_mgr = SessionManager()
    session_id = session_mgr.create_session("client456")
    print(f"会话ID: {session_id}")
    print(f"获取客户端ID: {session_mgr.get_client_id(session_id)}")
    
    print("\n速率限制测试:")
    limiter = RateLimiter(max_requests=5, time_window=60)
    for i in range(7):
        result = limiter.check_rate_limit("192.168.1.1")
        print(f"请求{i+1}: {result}, 剩余: {limiter.get_remaining('192.168.1.1')}")
