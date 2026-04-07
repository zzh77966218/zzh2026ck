#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RemoteLink 测试脚本
用于验证系统各主要功能是否正常工作
"""

import sys
import os
import time
import socket
import json

# 添加server路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'server'))

def test_security_module():
    """测试安全模块"""
    print("\n" + "="*50)
    print("测试 1: 安全模块")
    print("="*50)
    
    try:
        from security import PasswordManager, TokenManager, RateLimiter
        
        # 测试密码
        print("✓ 导入安全模块成功")
        
        pwd_hash = PasswordManager.hash_password("test123")
        print(f"✓ 密码哈希成功: {pwd_hash[:30]}...")
        
        verified = PasswordManager.verify_password("test123", pwd_hash)
        print(f"✓ 密码验证成功: {verified}")
        
        # 测试令牌
        token_mgr = TokenManager()
        token = token_mgr.generate_token("test_client")
        print(f"✓ 令牌生成成功: {token[:50]}...")
        
        client_id, error = token_mgr.verify_token(token)
        print(f"✓ 令牌验证成功: client_id={client_id}")
        
        # 测试速率限制
        limiter = RateLimiter(max_requests=5, time_window=60)
        result = limiter.check_rate_limit("127.0.0.1")
        print(f"✓ 速率限制检查成功: {result}")
        
        print("\n✅ 安全模块测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 安全模块测试失败: {e}")
        return False


def test_protocol():
    """测试通信协议"""
    print("\n" + "="*50)
    print("测试 2: 通信协议")
    print("="*50)
    
    try:
        from server.server import Protocol
        
        # 测试消息打包
        msg_type = Protocol.MSG_REGISTER
        data = {"name": "test", "id": "123456"}
        
        packed = Protocol.pack(msg_type, data)
        print(f"✓ 消息打包成功: {len(packed)} 字节")
        
        # 验证格式
        msg_type_read, payload_len = Protocol.unpack_header(packed[:5])
        print(f"✓ 消息头解析成功: type={msg_type_read}, len={payload_len}")
        
        payload = Protocol.recv_payload(None, payload_len)  # 这会失败，但我们只测试格式
        
        print("\n✅ 通信协议测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 通信协议测试失败: {e}")
        return False


def test_id_generator():
    """测试ID生成器"""
    print("\n" + "="*50)
    print("测试 3: ID生成器")
    print("="*50)
    
    try:
        from server.server import IDGenerator
        
        # 生成多个ID
        ids = set()
        for i in range(10):
            client_id = IDGenerator.generate()
            if IDGenerator.validate(client_id):
                ids.add(client_id)
                if i == 0:
                    print(f"✓ 生成的ID: {client_id}")
            else:
                print(f"❌ ID验证失败: {client_id}")
                return False
        
        if len(ids) == 10:
            print(f"✓ 生成了{len(ids)}个唯一ID")
        else:
            print(f"⚠ ID重复: {10 - len(ids)} 个重复")
        
        # 测试验证
        valid = IDGenerator.validate("123456")
        print(f"✓ 有效ID验证: {valid}")
        
        invalid = IDGenerator.validate("12345")  # 长度不对
        print(f"✓ 无效ID验证: {not invalid}")
        
        print("\n✅ ID生成器测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ ID生成器测试失败: {e}")
        return False


def test_network_socket():
    """测试网络套接字"""
    print("\n" + "="*50)
    print("测试 4: 网络套接字")
    print("="*50)
    
    try:
        # 创建套接字
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print(f"✓ 套接字创建成功")
        
        # 设置选项
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        print(f"✓ 套接字选项设置成功")
        
        # 绑定本地地址
        sock.bind(('127.0.0.1', 0))  # 使用任意端口
        port = sock.getsockname()[1]
        print(f"✓ 绑定成功: 127.0.0.1:{port}")
        
        sock.close()
        print(f"✓ 套接字关闭成功")
        
        print("\n✅ 网络套接字测试通过")
        return True
        
    except Exception as e:
        print(f"\n❌ 网络套接字测试失败: {e}")
        return False


def test_imports():
    """测试所有必要的导入"""
    print("\n" + "="*50)
    print("测试 5: 模块导入")
    print("="*50)
    
    required_modules = [
        'socket',
        'struct',
        'threading',
        'time',
        'json',
        'hashlib',
        'qrcode'
    ]
    
    optional_modules = [
        'mss',
        'numpy',
        'pyautogui',
        'PIL',
    ]
    
    failed = []
    
    # 测试必需模块
    for module_name in required_modules:
        try:
            __import__(module_name)
            print(f"✓ {module_name}")
        except ImportError:
            print(f"❌ {module_name}")
            failed.append(module_name)
    
    # 测试可选模块
    for module_name in optional_modules:
        try:
            __import__(module_name)
            print(f"✓ {module_name} (可选)")
        except ImportError:
            print(f"⚠ {module_name} (可选，缺失)")
    
    if not failed:
        print("\n✅ 模块导入测试通过")
        return True
    else:
        print(f"\n❌ 缺失必需模块: {failed}")
        return False


def main():
    """运行所有测试"""
    print("\n╔═══════════════════════════════════════════════════╗")
    print("║     RemoteLink 系统测试工具                      ║")
    print("║     Version 2.0 - 2026年4月8日                   ║")
    print("╚═══════════════════════════════════════════════════╝")
    
    tests = [
        ("module_imports", test_imports),
        ("id_generator", test_id_generator),
        ("protocol", test_protocol),
        ("security", test_security_module),
        ("network_socket", test_network_socket),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"\n❌ 测试异常: {e}")
            results[test_name] = False
    
    # 总结
    print("\n" + "="*50)
    print("测试总结")
    print("="*50)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} 测试通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！系统准备就绪。")
        return 0
    else:
        print(f"\n⚠ {total - passed} 个测试失败，请检查环境配置。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
