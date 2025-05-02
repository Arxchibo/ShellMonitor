import logging
import os
import sys
from datetime import datetime

def setup_logger():
    """设置日志记录器"""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)  # 设置为DEBUG级别以捕获更多信息
    
    # 确保logs目录存在
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 文件处理器
    file_handler = logging.FileHandler('logs/app.log', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 设置格式
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger
