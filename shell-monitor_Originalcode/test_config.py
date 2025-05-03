#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json
import os
import sys

def test_config():
    """测试配置文件是否有效"""
    config_file = "config.json"
    
    print(f"当前工作目录: {os.getcwd()}")
    print(f"配置文件路径: {os.path.abspath(config_file)}")
    
    # 检查文件是否存在
    if not os.path.exists(config_file):
        print(f"错误: 配置文件 {config_file} 不存在!")
        return False
    
    # 检查文件大小
    file_size = os.path.getsize(config_file)
    print(f"配置文件大小: {file_size} 字节")
    
    # 尝试读取文件内容
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()
            print(f"成功读取文件内容，长度: {len(content)} 字符")
            print("文件前100个字符:")
            print(content[:100] + "...")
    except Exception as e:
        print(f"读取文件时出错: {e}")
        return False
    
    # 尝试解析JSON
    try:
        config = json.loads(content)
        print("JSON 解析成功!")
        
        # 检查必要的配置项
        required_keys = [
            "api", "trading", "monitoring", "ui"
        ]
        
        for key in required_keys:
            if key not in config:
                print(f"警告: 缺少必要的配置项 '{key}'")
        
        # 打印配置项数量
        print(f"配置顶级项目数: {len(config)}")
        
        # 检查 API 键
        if "api" in config and "binance" in config["api"]:
            api_key = config["api"]["binance"].get("api_key", "")
            api_secret = config["api"]["binance"].get("api_secret", "")
            print(f"Binance API 配置: {'已配置' if api_key and api_secret else '未配置'}")
        
        return True
    except json.JSONDecodeError as e:
        print(f"JSON 解析错误: {e}")
        
        # 尝试找出错误位置
        line_no = e.lineno
        col_no = e.colno
        print(f"错误位置: 行 {line_no}, 列 {col_no}")
        
        # 打印错误附近的内容
        lines = content.split('\n')
        if line_no <= len(lines):
            start = max(0, line_no - 3)
            end = min(len(lines), line_no + 2)
            
            print("\n错误附近的内容:")
            for i in range(start, end):
                prefix = "-> " if i + 1 == line_no else "   "
                print(f"{prefix}{i+1}: {lines[i]}")
            
            if col_no > 0 and line_no <= len(lines):
                print("   " + " " * (col_no + 3) + "^")
                
        return False
    except Exception as e:
        print(f"其他错误: {e}")
        return False

if __name__ == "__main__":
    if test_config():
        print("配置文件有效，测试通过!")
        sys.exit(0)
    else:
        print("配置文件测试失败!")
        sys.exit(1) 