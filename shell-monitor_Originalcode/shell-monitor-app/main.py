#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import logging
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QCoreApplication
from ui.main_window import MainWindow
import qdarkstyle

# 导入日志模块
from utils.logger import setup_logger

def main():
    """
    应用程序主入口点
    """
    # 设置全局代理环境变量（如果需要）
    # os.environ['HTTPS_PROXY'] = 'http://your-proxy:port'
    # os.environ['HTTP_PROXY'] = 'http://your-proxy:port'
    
    # 初始化日志
    logger = setup_logger()
    logging.info("应用程序启动")
    
    # 启用高DPI支持
    QCoreApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QCoreApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("SHELL币监控器")
    
    # 设置应用样式
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    
    # 创建并显示主窗口
    window = MainWindow()
    window.show()
    
    # 运行应用
    logging.info("启动应用程序主循环")
    sys.exit(app.exec_())

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"应用程序发生致命错误: {e}", exc_info=True) 