#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os
import json
import pandas as pd
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QPushButton, QTabWidget, QGroupBox, 
                            QProgressBar, QStatusBar, QAction, QMenu, 
                            QSplitter, QTableWidget, QHeaderView, QMessageBox,
                            QTableWidgetItem, QToolBar, QComboBox, QSpinBox,
                            QScrollArea, QTextBrowser, QDialog, QApplication,
                            QSlider, QCheckBox)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot, QThread, QSize, QObject, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QColor, QPalette, QPixmap, QBrush
from PyQt5.QtChart import QChart, QChartView, QLineSeries, QDateTimeAxis, QValueAxis

from ui.settings_dialog import SettingsDialog
from ui.chart_widget import PriceChartWidget, MacdChartWidget
from shell_tracker_core import ShellTrackerCore
import logging
import traceback
import io
import requests
import time

# 控制台输出重定向类
class ConsoleRedirector(QObject):
    output_written = pyqtSignal(str)
    
    def __init__(self, original_stream=None):
        super().__init__()
        self.original_stream = original_stream
        self.buffer = io.StringIO()
        self.encoding = 'utf-8'  # 使用UTF-8编码
        
    def write(self, text):
        if text:  # 忽略空字符串
            # 确保text是字符串
            if not isinstance(text, str):
                try:
                    text = str(text)
                except:
                    text = repr(text)
            
            # 写入到原始流（如果有）
            if self.original_stream:
                try:
                    self.original_stream.write(text)
                    self.original_stream.flush()
                except:
                    pass  # 忽略写入原始流的错误
            
            # 将文本追加到缓冲区
            try:
                self.buffer.write(text)
            except:
                # 如果写入缓冲区失败，尝试使用repr
                self.buffer.write(repr(text))
            
            # 发出信号，通知UI更新
            self.output_written.emit(text)
        
    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except:
                pass
                
    def isatty(self):
        # 兼容性方法，某些库可能会调用此方法
        if self.original_stream and hasattr(self.original_stream, 'isatty'):
            return self.original_stream.isatty()
        return False
        
    def fileno(self):
        # 兼容性方法，某些库可能会调用此方法
        if self.original_stream and hasattr(self.original_stream, 'fileno'):
            return self.original_stream.fileno()
        return -1
    
    def get_buffer_contents(self):
        # 获取缓冲区内容
        return self.buffer.getvalue()

class MainWindow(QMainWindow):
    """主应用窗口类"""
    
    def __init__(self):
        super().__init__()
        
        # 设置窗口属性
        self.setWindowTitle("SHELL币行情监控")
        self.setMinimumSize(1000, 700)
        
        # 设置中心控件
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # 创建布局
        self.main_layout = QVBoxLayout(self.central_widget)
        
        # 加载配置
        self.config_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.json")
        self.config = self.load_config()
        
        # 初始化核心追踪器
        self.tracker = ShellTrackerCore(self.config)
        
        # Telegram发送控制变量
        self.telegram_send_interrupted = False
        self.report_data = None
        
        # 创建专门的图表目录
        self.charts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "charts")
        if not os.path.exists(self.charts_dir):
            os.makedirs(self.charts_dir)
            
        # 创建专门的日志目录
        self.log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "price_logs")
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)
        
        # 设置终端输出重定向
        self.stdout_redirector = ConsoleRedirector(sys.stdout)
        self.stderr_redirector = ConsoleRedirector(sys.stderr)
        sys.stdout = self.stdout_redirector
        sys.stderr = self.stderr_redirector
        self.stdout_redirector.output_written.connect(self.on_console_output)
        self.stderr_redirector.output_written.connect(self.on_console_output)
        
        # 控制台日志内容
        self.console_log = []
        self.max_log_lines = 1000  # 最大保留日志行数
        
        # 创建并初始化UI元素
        self.init_ui()
        
        # 初始化追踪器并获取初始数据
        self.initialize_tracker()
        
        # 创建菜单栏和工具栏
        self.create_menu()
        
        # 创建状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.statusBar.showMessage("就绪")
        
        # 连接信号和槽
        self.connect_signals()
        
        # 初始化计时器
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_ui)
        
        self.last_chart_update = datetime.now()
        self.chart_update_interval = 1.0  # 秒
        
    def load_config(self):
        """加载配置文件"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "配置错误", f"无法加载配置文件: {str(e)}")
            # 返回默认配置
            return {
                "api": {"binance": {"api_key": "", "api_secret": ""}},
                "trading": {"symbol": "SHELLUSDT", "interval": "15m"},
                "monitoring": {"duration_minutes": 120, "refresh_interval_seconds": 15}
            }
    
    def initialize_tracker(self):
        """初始化追踪器"""
        try:
            # 在初始化追踪器时设置charts_dir和log_dir
            self.tracker.charts_dir = self.charts_dir
            self.tracker.log_dir = self.log_dir
            
            success = self.tracker.initialize(self.config)
            if not success:
                QMessageBox.warning(self, "初始化警告", "Binance API 初始化失败，将使用有限功能。")
            else:
                logging.info("Binance API 初始化成功")
                
                # 同步价格图表的周期选择框和配置
                if hasattr(self, 'price_chart') and 'trading' in self.config and 'interval' in self.config['trading']:
                    interval = self.config['trading']['interval']
                    # 将配置中的周期映射到UI显示的周期
                    interval_to_ui = {
                        '1m': '1分钟',
                        '5m': '5分钟', 
                        '15m': '15分钟',
                        '1h': '1小时',
                        '1d': '1天'
                    }
                    ui_interval = interval_to_ui.get(interval, '15分钟')
                    index = self.price_chart.timeframe_combo.findText(ui_interval)
                    if index >= 0:
                        self.price_chart.timeframe_combo.setCurrentIndex(index)
                        logging.info(f"价格图表周期已设置为: {ui_interval}")
                
                # 在单独的线程中获取初始数据，避免阻塞UI
                def get_initial_data():
                    try:
                        # 获取最新价格
                        price = self.tracker.get_latest_price()
                        if price:
                            # 使用信号槽机制更新UI，避免直接调用UI方法
                            self.tracker.price_updated.emit(price, 0.0)
                            
                        # 获取账户余额
                        self.tracker.check_account_balance()
                    except Exception as e:
                        logging.error(f"获取初始数据失败: {e}")
                
                # 创建并启动线程
                import threading
                initial_data_thread = threading.Thread(target=get_initial_data)
                initial_data_thread.daemon = True
                initial_data_thread.start()
        except Exception as e:
            logging.error(f"初始化追踪器失败: {e}")
            QMessageBox.critical(self, "初始化错误", f"初始化过程中发生错误: {str(e)}")

    def init_ui(self):
        """初始化UI组件"""
        # 创建主分割器，分为左侧主面板和右侧报告面板
        self.splitter = QSplitter(Qt.Horizontal)
        
        # 左侧主面板容器
        self.main_panel = QWidget()
        self.main_layout = QVBoxLayout(self.main_panel)
        
        # 顶部控制面板
        self.control_panel = QWidget()
        control_layout = QHBoxLayout(self.control_panel)
        
        # 开始/停止按钮
        self.start_button = QPushButton("开始监控")
        self.start_button.setMinimumHeight(40)
        self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        
        # 监控时长设置
        duration_group = QGroupBox("监控时长")
        duration_layout = QHBoxLayout(duration_group)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(1, 1440)  # 1分钟到1天
        self.duration_spin.setValue(120)
        self.duration_spin.setSuffix(" 分钟")
        duration_layout.addWidget(self.duration_spin)
        
        # 刷新间隔设置
        interval_group = QGroupBox("刷新间隔")
        interval_layout = QHBoxLayout(interval_group)
        self.interval_spin = QSpinBox()
        self.interval_spin.setRange(5, 300)  # 5秒到5分钟
        self.interval_spin.setValue(15)
        self.interval_spin.setSuffix(" 秒")
        interval_layout.addWidget(self.interval_spin)
        
        # 报告按钮
        self.report_button = QPushButton("显示报告")
        self.report_button.setMinimumHeight(40)
        self.report_button.setStyleSheet("QPushButton { background-color: #2196F3; color: white; }")
        self.report_button.clicked.connect(self.toggle_report_panel)
        
        # 添加到控制面板
        control_layout.addWidget(self.start_button, 1)
        control_layout.addWidget(duration_group, 1)
        control_layout.addWidget(interval_group, 1)
        control_layout.addWidget(self.report_button, 1)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        # 价格显示面板
        self.price_panel = QWidget()
        price_layout = QVBoxLayout(self.price_panel)
        
        # 大字体显示当前价格
        self.price_label = QLabel("---.----")
        self.price_label.setAlignment(Qt.AlignCenter)
        font = QFont("Arial", 24, QFont.Bold)
        self.price_label.setFont(font)
        
        # 价格变化百分比
        self.price_change_label = QLabel("+0.00%")
        self.price_change_label.setAlignment(Qt.AlignCenter)
        change_font = QFont("Arial", 16)
        self.price_change_label.setFont(change_font)
        
        # 价格信息和账户余额布局
        price_info_layout = QHBoxLayout()
        
        # 高低价格信息
        self.price_info_label = QLabel("高: ---.---- | 低: ---.----")
        self.price_info_label.setAlignment(Qt.AlignCenter)
        
        # 账户余额信息
        self.balance_label = QLabel("余额: --- | 价值: --- USDT")
        self.balance_label.setAlignment(Qt.AlignCenter)
        
        price_info_layout.addWidget(self.price_info_label)
        price_info_layout.addWidget(self.balance_label)
        
        # 添加组件到价格面板
        price_layout.addWidget(self.price_label)
        price_layout.addWidget(self.price_change_label)
        price_layout.addLayout(price_info_layout)
        
        # 图表和指标区
        self.tabs = QTabWidget()
        
        # 价格图表标签页
        self.price_chart_tab = QWidget()
        price_chart_layout = QVBoxLayout(self.price_chart_tab)
        self.price_chart = PriceChartWidget()
        price_chart_layout.addWidget(self.price_chart)
        
        # 技术指标标签页
        self.indicator_tab = QWidget()
        indicator_layout = QVBoxLayout(self.indicator_tab)
        
        # MACD图表
        self.macd_chart = MacdChartWidget()
        
        # 技术指标卡片
        indicator_cards = QWidget()
        cards_layout = QHBoxLayout(indicator_cards)
        
        # RSI卡片
        rsi_group = QGroupBox("RSI")
        rsi_layout = QVBoxLayout(rsi_group)
        self.rsi_value = QLabel("--")
        self.rsi_value.setAlignment(Qt.AlignCenter)
        self.rsi_value.setFont(QFont("Arial", 14, QFont.Bold))
        rsi_layout.addWidget(self.rsi_value)
        
        # MACD卡片
        macd_group = QGroupBox("MACD")
        macd_layout = QVBoxLayout(macd_group)
        self.macd_value = QLabel("--")
        self.macd_value.setAlignment(Qt.AlignCenter)
        self.macd_value.setFont(QFont("Arial", 14, QFont.Bold))
        macd_layout.addWidget(self.macd_value)
        
        # 均线卡片
        ma_group = QGroupBox("均线状态")
        ma_layout = QVBoxLayout(ma_group)
        self.ma_value = QLabel("--")
        self.ma_value.setAlignment(Qt.AlignCenter)
        self.ma_value.setFont(QFont("Arial", 14, QFont.Bold))
        ma_layout.addWidget(self.ma_value)
        
        # 添加卡片到布局
        cards_layout.addWidget(rsi_group)
        cards_layout.addWidget(macd_group)
        cards_layout.addWidget(ma_group)
        
        # 添加到指标布局
        indicator_layout.addWidget(self.macd_chart, 2)
        indicator_layout.addWidget(indicator_cards, 1)
        
        # 新闻和情感分析标签页
        self.news_tab = QWidget()
        news_layout = QVBoxLayout(self.news_tab)
        
        # 情感分析指示器
        sentiment_group = QGroupBox("市场情感")
        sentiment_layout = QHBoxLayout(sentiment_group)
        self.sentiment_label = QLabel("未知")
        self.sentiment_label.setAlignment(Qt.AlignCenter)
        self.sentiment_label.setFont(QFont("Arial", 14, QFont.Bold))
        sentiment_layout.addWidget(self.sentiment_label)
        
        # 新闻表格
        self.news_table = QTableWidget(0, 2)
        self.news_table.setHorizontalHeaderLabels(["时间", "新闻摘要"])
        self.news_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        
        news_layout.addWidget(sentiment_group)
        news_layout.addWidget(self.news_table)
        
        # RSS新闻标签页
        self.rss_tab = QWidget()
        rss_layout = QVBoxLayout(self.rss_tab)
        
        # RSS新闻表格
        self.rss_table = QTableWidget(0, 4)
        self.rss_table.setHorizontalHeaderLabels(["时间", "来源", "标题", "摘要"])
        self.rss_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        
        rss_layout.addWidget(self.rss_table)
        
        # 添加标签页
        self.tabs.addTab(self.price_chart_tab, "价格图表")
        self.tabs.addTab(self.indicator_tab, "技术指标")
        self.tabs.addTab(self.news_tab, "新闻与情感")
        self.tabs.addTab(self.rss_tab, "RSS新闻")
        
        # 信号面板
        self.signal_panel = QGroupBox("交易信号")
        signal_layout = QHBoxLayout(self.signal_panel)
        
        # 最新信号显示
        self.latest_signal = QLabel("等待信号...")
        self.latest_signal.setAlignment(Qt.AlignCenter)
        self.latest_signal.setFont(QFont("Arial", 16, QFont.Bold))
        
        # 推荐操作显示
        self.recommendation = QLabel("暂无推荐")
        self.recommendation.setAlignment(Qt.AlignCenter)
        
        # 信号置信度
        self.confidence_bar = QProgressBar()
        self.confidence_bar.setRange(0, 100)
        self.confidence_bar.setValue(0)
        self.confidence_bar.setTextVisible(True)
        self.confidence_bar.setFormat("置信度: %p%")
        
        signal_layout.addWidget(self.latest_signal, 2)
        signal_layout.addWidget(self.recommendation, 2)
        signal_layout.addWidget(self.confidence_bar, 1)
        
        # 将组件添加到主布局
        self.main_layout.addWidget(self.control_panel)
        self.main_layout.addWidget(self.price_panel)
        self.main_layout.addWidget(self.tabs, 3)
        self.main_layout.addWidget(self.signal_panel)
        
        # 右侧报告面板
        self.report_panel = QWidget()
        self.report_panel.setVisible(False)  # 默认隐藏
        self.report_layout = QVBoxLayout(self.report_panel)
        # 设置报告面板的深色背景
        self.report_panel.setStyleSheet("background-color: #2c3e50;")
        
        # 报告标题
        self.report_title = QLabel("SHELL币行情监控报告")
        self.report_title.setAlignment(Qt.AlignCenter)
        title_font = QFont("Arial", 16, QFont.Bold)
        self.report_title.setFont(title_font)
        self.report_title.setStyleSheet("color: white; margin: 10px;")
        
        # 报告内容滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("background-color: #34495e; border-radius: 5px;")
        
        # 报告内容容器
        report_content_widget = QWidget()
        report_content_widget.setStyleSheet("background-color: #34495e;")
        self.report_content_layout = QVBoxLayout(report_content_widget)
        
        # 报告文本区域
        self.report_text = QTextBrowser()
        self.report_text.setOpenExternalLinks(True)
        self.report_text.setStyleSheet("background-color: #ecf0f1; border: 1px solid #bdc3c7; border-radius: 5px; padding: 10px; color: #2c3e50;")
        self.report_text.setMinimumHeight(300)  # 设置最小高度以确保文本区域足够大
        
        # 图表区域标题
        charts_title = QLabel("分析图表")
        charts_title.setAlignment(Qt.AlignCenter)
        charts_title.setFont(QFont("Arial", 12, QFont.Bold))
        charts_title.setStyleSheet("color: white; margin-top: 15px;")
        
        # 图表容器 - 横向布局
        charts_container = QWidget()
        charts_container.setStyleSheet("background-color: #34495e;")
        charts_layout = QHBoxLayout(charts_container)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        
        # 价格图表缩略图
        price_chart_container = QWidget()
        price_chart_container.setStyleSheet("background-color: #34495e;")
        price_chart_layout = QVBoxLayout(price_chart_container)
        price_chart_layout.setContentsMargins(5, 5, 5, 5)
        
        price_chart_title = QLabel("价格趋势")
        price_chart_title.setAlignment(Qt.AlignCenter)
        price_chart_title.setStyleSheet("color: white;")
        
        self.price_chart_label = QLabel()
        self.price_chart_label.setAlignment(Qt.AlignCenter)
        self.price_chart_label.setScaledContents(False)
        self.price_chart_label.setMaximumSize(300, 200)  # 限制图片大小
        self.price_chart_label.setCursor(Qt.PointingHandCursor)  # 鼠标指针变为手型
        self.price_chart_label.setStyleSheet("border: 1px solid #bdc3c7; background-color: white; padding: 5px;")
        self.price_chart_label.mousePressEvent = self.show_price_chart_fullsize  # 为图片添加点击事件
        
        price_chart_layout.addWidget(price_chart_title)
        price_chart_layout.addWidget(self.price_chart_label)
        price_chart_layout.addStretch()
        
        # MACD图表缩略图
        macd_chart_container = QWidget()
        macd_chart_container.setStyleSheet("background-color: #34495e;")
        macd_chart_layout = QVBoxLayout(macd_chart_container)
        macd_chart_layout.setContentsMargins(5, 5, 5, 5)
        
        macd_chart_title = QLabel("MACD指标")
        macd_chart_title.setAlignment(Qt.AlignCenter)
        macd_chart_title.setStyleSheet("color: white;")
        
        self.macd_chart_label = QLabel()
        self.macd_chart_label.setAlignment(Qt.AlignCenter)
        self.macd_chart_label.setScaledContents(False)
        self.macd_chart_label.setMaximumSize(300, 200)  # 限制图片大小
        self.macd_chart_label.setCursor(Qt.PointingHandCursor)  # 鼠标指针变为手型
        self.macd_chart_label.setStyleSheet("border: 1px solid #bdc3c7; background-color: white; padding: 5px;")
        self.macd_chart_label.mousePressEvent = self.show_macd_chart_fullsize  # 为图片添加点击事件
        
        macd_chart_layout.addWidget(macd_chart_title)
        macd_chart_layout.addWidget(self.macd_chart_label)
        macd_chart_layout.addStretch()
        
        # 将图表添加到图表布局
        charts_layout.addWidget(price_chart_container)
        charts_layout.addWidget(macd_chart_container)
        
        # 添加组件到报告内容布局
        self.report_content_layout.addWidget(self.report_text, 3)  # 文本区域占更大比例
        self.report_content_layout.addWidget(charts_title)
        self.report_content_layout.addWidget(charts_container, 1)  # 图表区域占比减小
        
        # 设置滚动区域的内容
        scroll_area.setWidget(report_content_widget)
        
        # 报告生成控制区域
        report_controls = QWidget()
        report_controls_layout = QHBoxLayout(report_controls)
        report_controls_layout.setContentsMargins(5, 5, 5, 5)
        
        # 自动生成报告设置区域
        auto_report_group = QWidget()
        auto_report_layout = QHBoxLayout(auto_report_group)
        auto_report_layout.setContentsMargins(0, 0, 0, 0)
        
        # 自动生成报告标签
        auto_report_label = QLabel("自动生成报告:")
        auto_report_label.setStyleSheet("color: white;")
        auto_report_layout.addWidget(auto_report_label)
        
        # 自动生成报告的间隔选择器
        self.auto_report_interval = QComboBox()
        self.auto_report_interval.addItems(["1分钟", "5分钟", "15分钟", "30分钟", "1小时"])
        self.auto_report_interval.setStyleSheet("background-color: #34495e; color: white; padding: 3px;")
        auto_report_layout.addWidget(self.auto_report_interval)
        
        # 自动生成报告开关
        self.auto_report_toggle = QPushButton("开启自动")
        self.auto_report_toggle.setStyleSheet("QPushButton { background-color: #3498db; color: white; padding: 5px; }")
        self.auto_report_toggle.setCheckable(True)
        self.auto_report_toggle.clicked.connect(self.toggle_auto_report)
        auto_report_layout.addWidget(self.auto_report_toggle)
        
        # 手动生成报告按钮
        self.refresh_report_button = QPushButton("手动生成报告")
        self.refresh_report_button.setStyleSheet("QPushButton { background-color: #3498db; color: white; padding: 8px; }")
        self.refresh_report_button.setCursor(Qt.PointingHandCursor)
        self.refresh_report_button.clicked.connect(self.generate_report)
        
        # 添加到报告控制布局
        report_controls_layout.addWidget(auto_report_group)
        report_controls_layout.addStretch(1)  # 添加弹性空间
        report_controls_layout.addWidget(self.refresh_report_button)
        
        # 自动报告定时器
        self.auto_report_timer = QTimer(self)
        self.auto_report_timer.timeout.connect(self.generate_report)
        
        # 添加Telegram自动发送选项
        telegram_container = QWidget()
        telegram_layout = QHBoxLayout(telegram_container)
        telegram_layout.setContentsMargins(0, 5, 0, 5)
        telegram_layout.setSpacing(8)  # 增加控件间距
        
        # 设置一个固定宽度的标签区域
        telegram_label_container = QWidget()
        telegram_label_container.setFixedWidth(120)  # 增加宽度
        telegram_label_layout = QVBoxLayout(telegram_label_container)
        telegram_label_layout.setContentsMargins(0, 0, 0, 0)
        
        telegram_label = QLabel("发送至Telegram:")
        telegram_label.setStyleSheet("color: white; font-size: 12px;")  # 增大字体
        telegram_label_layout.addWidget(telegram_label)
        
        # 创建状态文本框
        self.telegram_status = QLabel("")
        self.telegram_status.setStyleSheet("color: #3498db; font-size: 11px;")  # 增大字体
        telegram_label_layout.addWidget(self.telegram_status)
        
        # 控件布局
        controls_container = QWidget()
        controls_layout = QHBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)  # 增加控件间距
        
        # 自动发送复选框
        self.auto_telegram_checkbox = QCheckBox("自动")
        self.auto_telegram_checkbox.setChecked(False)  # 默认不开启
        self.auto_telegram_checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                font-size: 12px;  /* 增大字体 */
            }
            QCheckBox::indicator {
                width: 16px;  /* 增大复选框尺寸 */
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: #e74c3c;
                border: 1px solid #c0392b;
                border-radius: 8px;
            }
            QCheckBox::indicator:checked {
                background-color: #2ecc71;
                border: 1px solid #27ae60;
                border-radius: 8px;
            }
        """)
        
        # 手动发送按钮
        self.send_telegram_button = QPushButton("发送")
        self.send_telegram_button.setFixedSize(50, 24)  # 增大按钮尺寸
        self.send_telegram_button.setStyleSheet("""
            QPushButton { 
                background-color: #2980b9; 
                color: white; 
                padding: 3px; 
                font-size: 12px;  /* 增大字体 */
                border-radius: 4px;
            }
        """)
        self.send_telegram_button.setCursor(Qt.PointingHandCursor)
        self.send_telegram_button.clicked.connect(self.send_report_to_telegram)
        
        # 中断发送按钮
        self.stop_telegram_button = QPushButton("中断")
        self.stop_telegram_button.setFixedSize(50, 24)  # 增大按钮尺寸
        self.stop_telegram_button.setStyleSheet("""
            QPushButton { 
                background-color: #e74c3c; 
                color: white; 
                padding: 3px; 
                font-size: 12px;  /* 增大字体 */
                border-radius: 4px;
            }
        """)
        self.stop_telegram_button.setCursor(Qt.PointingHandCursor)
        self.stop_telegram_button.clicked.connect(self.stop_telegram_sending)
        self.stop_telegram_button.setEnabled(False)  # 默认禁用
        
        # 添加控件到布局
        controls_layout.addWidget(self.auto_telegram_checkbox)
        controls_layout.addWidget(self.send_telegram_button)
        controls_layout.addWidget(self.stop_telegram_button)
        
        # 将标签区域和控件区域添加到主布局
        telegram_layout.addWidget(telegram_label_container)
        telegram_layout.addWidget(controls_container, 1)  # 控件区域可扩展
        
        # 添加组件到报告面板
        self.report_layout.addWidget(self.report_title)
        self.report_layout.addWidget(scroll_area)
        self.report_layout.addWidget(telegram_container)
        self.report_layout.addWidget(report_controls)
        
        # 添加主面板和报告面板到分割器
        self.splitter.addWidget(self.main_panel)
        self.splitter.addWidget(self.report_panel)
        self.splitter.setSizes([700, 0])  # 初始状态下右侧不显示
        
        # 设置中央控件为分割器
        self.setCentralWidget(self.splitter)
        
        # 添加底部日志面板（默认隐藏）
        self.log_panel = QWidget()
        self.log_panel.setVisible(False)  # 默认隐藏
        self.log_layout = QVBoxLayout(self.log_panel)
        self.log_panel.setStyleSheet("background-color: #2c3e50;")
        
        # 日志面板标题和控制按钮
        log_header = QWidget()
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(5, 5, 5, 5)
        
        log_title = QLabel("系统终端输出")
        log_title.setStyleSheet("color: white; font-weight: bold;")
        log_header_layout.addWidget(log_title)
        
        log_header_layout.addStretch()
        
        refresh_log_button = QPushButton("刷新")
        refresh_log_button.setStyleSheet("QPushButton { background-color: #2980b9; color: white; padding: 3px 8px; }")
        refresh_log_button.clicked.connect(self.update_log_display)
        log_header_layout.addWidget(refresh_log_button)
        
        clear_log_button = QPushButton("清空")
        clear_log_button.setStyleSheet("QPushButton { background-color: #3498db; color: white; padding: 3px 8px; }")
        clear_log_button.clicked.connect(self.clear_log)
        log_header_layout.addWidget(clear_log_button)
        
        close_log_button = QPushButton("关闭")
        close_log_button.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; padding: 3px 8px; }")
        close_log_button.clicked.connect(self.toggle_log_panel)
        log_header_layout.addWidget(close_log_button)
        
        # 日志文本区域
        self.log_text = QTextBrowser()
        self.log_text.setStyleSheet("background-color: #34495e; color: #ecf0f1; font-family: Consolas, monospace;")
        
        # 添加到日志面板
        self.log_layout.addWidget(log_header)
        self.log_layout.addWidget(self.log_text)
        
        # 创建垂直分割器，包含主界面和日志面板
        self.vertical_splitter = QSplitter(Qt.Vertical)
        self.vertical_splitter.addWidget(self.splitter)  # 添加已有的水平分割器
        self.vertical_splitter.addWidget(self.log_panel)
        self.vertical_splitter.setSizes([700, 0])  # 初始状态下底部不显示
        
        # 将垂直分割器设置为中央控件
        self.setCentralWidget(self.vertical_splitter)
        
    def create_menu(self):
        """创建菜单栏和工具栏"""
        # 菜单栏
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        # 设置操作
        settings_action = QAction("设置", self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self.open_settings)
        file_menu.addAction(settings_action)
        
        # 退出操作
        exit_action = QAction("退出", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 工具菜单
        tools_menu = menubar.addMenu("工具")
        
        # 刷新操作
        refresh_action = QAction("刷新数据", self)
        refresh_action.setShortcut("F5")
        refresh_action.triggered.connect(self.refresh_data)
        tools_menu.addAction(refresh_action)
        
        # 生成报告操作
        report_action = QAction("生成报告", self)
        report_action.setShortcut("Ctrl+R")
        report_action.triggered.connect(self.show_and_generate_report)
        tools_menu.addAction(report_action)
        
        # 保存图表操作
        save_chart_action = QAction("保存图表", self)
        save_chart_action.triggered.connect(self.save_chart)
        tools_menu.addAction(save_chart_action)
        
        # 查看终端输出操作
        view_logs_action = QAction("终端输出", self)
        view_logs_action.triggered.connect(self.toggle_log_panel)
        tools_menu.addAction(view_logs_action)
        
        # 帮助菜单
        help_menu = menubar.addMenu("帮助")
        
        # 关于操作
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        # 工具栏
        toolbar = QToolBar("主工具栏")
        self.addToolBar(toolbar)
        
        # 添加工具栏按钮
        toolbar.addAction(settings_action)
        toolbar.addAction(refresh_action)
        toolbar.addAction(report_action)  # 添加报告按钮到工具栏
        toolbar.addSeparator()
        
        # 添加货币选择器到工具栏
        symbol_label = QLabel("交易对:")
        toolbar.addWidget(symbol_label)
        
        self.symbol_combo = QComboBox()
        self.symbol_combo.addItem("SHELLUSDT")
        self.symbol_combo.addItem("BTCUSDT")
        self.symbol_combo.addItem("ETHUSDT")
        toolbar.addWidget(self.symbol_combo)
    
    def connect_signals(self):
        """连接信号与槽"""
        self.start_button.clicked.connect(self.toggle_monitoring)
        
        # 连接追踪器信号
        self.tracker.price_updated.connect(self.on_price_updated)
        self.tracker.trade_signal.connect(self.on_trade_signal)
        self.tracker.monitoring_error.connect(self.on_monitoring_error)
        self.tracker.news_processed.connect(self.on_news_processed)
        self.tracker.signal_status_updated.connect(self.on_signal_status_updated)
        self.tracker.chart_data_ready.connect(self.on_chart_data_ready)
        self.tracker.monitoring_started.connect(self.on_monitoring_started)
        self.tracker.monitoring_stopped.connect(self.on_monitoring_stopped)
        
        # 连接新增的信号
        self.tracker.account_balance_updated.connect(self.on_account_balance_updated)
        self.tracker.rss_news_received.connect(self.on_rss_news_received)
        self.tracker.alert_triggered.connect(self.on_alert_triggered)
        
        # 连接图表点击事件
        self.price_chart_label.mousePressEvent = self.show_price_chart_fullsize
        self.macd_chart_label.mousePressEvent = self.show_macd_chart_fullsize
        
        # 连接自定义表格点击事件
        self.rss_table.cellDoubleClicked.connect(self.on_rss_table_cell_double_clicked)
        self.news_table.cellDoubleClicked.connect(self.on_news_table_cell_double_clicked)
        
        # 连接价格图表周期变化信号
        self.price_chart.timeframe_changed.connect(self.on_timeframe_changed)
        
        # 连接交易对选择框信号
        self.symbol_combo.currentTextChanged.connect(self.on_symbol_changed)
    
    def on_timeframe_changed(self, interval):
        """处理图表时间周期变化"""
        try:
            # 更新配置
            if 'trading' not in self.config:
                self.config['trading'] = {}
                
            self.config['trading']['interval'] = interval
            
            # 更新追踪器配置
            if hasattr(self, 'tracker') and self.tracker:
                self.tracker.config = self.config
                
            # 如果正在监控中，重新获取K线数据
            if self.start_button.text() != "开始监控":
                # 获取最新K线数据
                df = self.tracker.get_klines()
                if df is not None and not df.empty:
                    # 触发图表更新
                    self.tracker.chart_data_ready.emit(df)
                    
            # 记录日志
            logging.info(f"交易时间周期已更改为: {interval}")
            self.statusBar.showMessage(f"已更改K线时间周期为: {interval}", 3000)
            
        except Exception as e:
            logging.error(f"更改时间周期时出错: {e}")
            self.statusBar.showMessage(f"更改时间周期失败: {str(e)}", 3000)
    
    def on_symbol_changed(self, symbol):
        """处理交易对变化"""
        try:
            # 更新配置
            if 'trading' not in self.config:
                self.config['trading'] = {}
                
            self.config['trading']['symbol'] = symbol
            
            # 更新追踪器配置
            if hasattr(self, 'tracker') and self.tracker:
                self.tracker.config = self.config
                
            # 如果正在监控中，重新获取数据
            if self.start_button.text() != "开始监控":
                # 获取最新价格
                price = self.tracker.get_latest_price()
                if price:
                    self.tracker.price_updated.emit(price, 0.0)
                
                # 获取最新K线数据
                df = self.tracker.get_klines()
                if df is not None and not df.empty:
                    # 触发图表更新
                    self.tracker.chart_data_ready.emit(df)
                    
            # 记录日志
            logging.info(f"交易对已更改为: {symbol}")
            self.statusBar.showMessage(f"已更改交易对为: {symbol}", 3000)
            
        except Exception as e:
            logging.error(f"更改交易对时出错: {e}")
            self.statusBar.showMessage(f"更改交易对失败: {str(e)}", 3000)
    
    def open_settings(self):
        """打开设置对话框"""
        dialog = SettingsDialog(self)
        if dialog.exec_():
            # 应用新设置
            self.apply_settings()
    
    def apply_settings(self):
        """应用设置更改"""
        # TODO: 实现设置应用逻辑
        pass
    
    def refresh_data(self):
        """手动刷新数据"""
        # TODO: 实现数据刷新逻辑
        self.statusBar.showMessage("数据刷新中...", 2000)
    
    def save_chart(self):
        """保存当前图表为图片"""
        # TODO: 实现图表保存逻辑
        self.statusBar.showMessage("图表已保存", 2000)
    
    def show_about(self):
        """显示关于对话框"""
        QMessageBox.about(self, "关于", 
                          "SHELL币监控器 v1.0\n\n"
                          "基于 Python 和 PyQt5 开发的加密货币监控工具\n"
                          "支持技术分析、新闻情感分析和交易信号生成")
    
    def toggle_monitoring(self):
        """开始或停止监控"""
        if self.start_button.text() == "开始监控":
            # 开始监控
            self.start_monitoring()
            self.start_button.setText("停止监控")
            self.start_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
        else:
            # 停止监控
            self.stop_monitoring()
            self.start_button.setText("开始监控")
            self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
    
    def start_monitoring(self):
        """开始监控"""
        try:
            # 确保目录设置正确
            self.tracker.charts_dir = self.charts_dir  
            self.tracker.log_dir = self.log_dir
            
            # 获取设置值
            duration = self.duration_spin.value()
            interval = self.interval_spin.value()
            
            # 调用追踪器的监控方法
            self.tracker.start_monitoring(duration, interval)
            
            # 更新UI状态
            self.start_button.setText("停止监控")
            self.start_button.setStyleSheet("QPushButton { background-color: #f44336; color: white; }")
            
            # 启动UI更新计时器
            self.timer.start(1000)  # 每秒更新一次UI
        except Exception as e:
            QMessageBox.critical(self, "监控错误", f"启动监控时发生错误: {str(e)}")
            logging.error(f"启动监控失败: {e}")
    
    def stop_monitoring(self):
        """停止监控逻辑"""
        # 停止UI更新计时器
        self.timer.stop()
        
        # 停止追踪器监控
        self.tracker.stop_monitoring()
        
        self.statusBar.showMessage("监控已停止")
    
    @pyqtSlot()
    def update_ui(self):
        """更新UI显示"""
        # 这个方法会被计时器定期调用
        
        # 如果正在监控状态，尝试触发信号状态检查，以保持交易信号面板的更新
        if self.start_button.text() != "开始监控" and hasattr(self, 'tracker') and self.tracker:
            try:
                # 记录当前时间
                current_time = datetime.now()
                
                # 初始化上次更新时间（如果不存在）
                if not hasattr(self, 'last_signal_update_time'):
                    self.last_signal_update_time = current_time
                    
                # 获取用户设置的刷新间隔（单位：秒）
                refresh_interval = self.interval_spin.value()
                
                # 计算自上次更新以来经过的时间（单位：秒）
                elapsed_seconds = (current_time - self.last_signal_update_time).total_seconds()
                
                # 仅当经过的时间大于等于刷新间隔时才更新交易信号
                if elapsed_seconds >= refresh_interval:
                    # 获取最新K线数据
                    df = self.tracker.get_klines()
                    if df is not None and not df.empty:
                        # 检查交易信号
                        self.tracker.check_signals(df)
                        
                    # 更新上次更新时间
                    self.last_signal_update_time = current_time
                    logging.info(f"交易信号已按照设定间隔({refresh_interval}秒)更新")
            except Exception as e:
                logging.error(f"自动更新交易信号时出错: {str(e)}")
    
    @pyqtSlot(float, float)
    def on_price_updated(self, price, pct_change):
        """更新价格显示"""
        # 安全检查：确保UI元素已经初始化
        if not hasattr(self, 'price_label') or self.price_label is None:
            return
            
        self.price_label.setText(f"{price:.4f}")
        
        # 设置价格变化显示和颜色
        change_text = f"{pct_change:+.2f}%"
        self.price_change_label.setText(change_text)
        
        color = "#4CAF50" if pct_change >= 0 else "#f44336"
        self.price_change_label.setStyleSheet(f"color: {color};")
        
        # 更新价格图表数据
        current_time = datetime.now()
        if not hasattr(self, 'price_data_points'):
            self.price_data_points = []
        
        self.price_data_points.append((current_time, price))
        
        # 只保留最近300个点以避免内存占用过多
        if len(self.price_data_points) > 300:
            self.price_data_points = self.price_data_points[-300:]
        
        # 更新高低价格标签
        if hasattr(self, 'price_data_points') and self.price_data_points:
            prices = [p[1] for p in self.price_data_points]
            high_price = max(prices)
            low_price = min(prices)
            self.price_info_label.setText(f"高: {high_price:.4f} | 低: {low_price:.4f}")
        
        # 限制图表更新频率
        if (current_time - self.last_chart_update).total_seconds() >= self.chart_update_interval:
            if hasattr(self, 'price_chart') and self.price_chart is not None:
                self.price_chart.update_line_chart(self.price_data_points)
            self.last_chart_update = current_time
    
    @pyqtSlot(str, float)
    def on_trade_signal(self, signal_type, price):
        """处理交易信号"""
        if signal_type == 'BUY':
            QMessageBox.information(self, "交易信号", f"触发买入信号，价格: {price:.4f}")
        elif signal_type == 'SELL':
            QMessageBox.information(self, "交易信号", f"触发卖出信号，价格: {price:.4f}")
    
    @pyqtSlot(str)
    def on_monitoring_error(self, error_message):
        """处理监控错误"""
        self.statusBar.showMessage(f"错误: {error_message}")
    
    @pyqtSlot(str, str, float)
    def on_news_processed(self, processed_news, sentiment, score):
        """处理新闻分析结果"""
        # 更新情感标签
        sentiment_text = {
            "positive": "积极 😀",
            "neutral": "中性 😐",
            "negative": "消极 😟"
        }.get(sentiment, "未知")
        
        self.sentiment_label.setText(f"{sentiment_text} ({score:.1f})")
        
        # 添加新闻到表格
        row = self.news_table.rowCount()
        self.news_table.insertRow(row)
        
        time_item = QTableWidgetItem(datetime.now().strftime("%H:%M:%S"))
        news_item = QTableWidgetItem(processed_news)
        
        # 设置工具提示，使时间项上悬停显示完整时间
        time_item.setToolTip(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # 设置新闻项上的工具提示，表明双击可查看详情
        news_item.setToolTip("双击查看详情")
        news_item.setForeground(QBrush(QColor('#0066cc')))
        
        # 保存完整内容
        news_item.setData(Qt.UserRole, processed_news)
        
        self.news_table.setItem(row, 0, time_item)
        self.news_table.setItem(row, 1, news_item)
    
    @pyqtSlot(str, str, int)
    def on_signal_status_updated(self, signal_type, recommendation, confidence):
        """更新信号状态"""
        signal_text = {
            "BUY": "买入信号",
            "SELL": "卖出信号",
            "NEUTRAL": "中性信号"
        }.get(signal_type, "未知信号")
        
        color = {
            "BUY": "#4CAF50",
            "SELL": "#f44336",
            "NEUTRAL": "#FFC107"
        }.get(signal_type, "#607D8B")
        
        self.latest_signal.setText(signal_text)
        self.latest_signal.setStyleSheet(f"color: {color};")
        self.recommendation.setText(recommendation)
        self.confidence_bar.setValue(confidence)
    
    @pyqtSlot(object)
    def on_chart_data_ready(self, data):
        """处理K线数据"""
        # 检查数据是否有效
        if data is None or data.empty:
            self.statusBar.showMessage("收到空K线数据，暂不更新图表", 3000)
            return
            
        # 打印日志用于调试
        logging.info(f"收到K线数据：{len(data)} 条记录")
        
        try:
            # 更新技术指标
            latest = data.iloc[-1]
            logging.info(f"最新数据: {latest.name}")
            
            # 检查数据中是否包含所需的指标
            if 'rsi' in latest and not pd.isna(latest['rsi']):
                self.rsi_value.setText(f"{latest['rsi']:.1f}")
                logging.info(f"更新RSI: {latest['rsi']:.1f}")
            else:
                logging.warning("K线数据中缺少RSI指标")
            
            if 'macd' in latest and 'macd_signal' in latest and not pd.isna(latest['macd']) and not pd.isna(latest['macd_signal']):
                self.macd_value.setText(f"{latest['macd']:.4f} / {latest['macd_signal']:.4f}")
                logging.info(f"更新MACD: {latest['macd']:.4f} / {latest['macd_signal']:.4f}")
            else:
                logging.warning("K线数据中缺少MACD指标")
            
            if 'ma5' in latest and 'ma25' in latest and not pd.isna(latest['ma5']) and not pd.isna(latest['ma25']):
                if latest['ma5'] > latest['ma25']:
                    self.ma_value.setText("多头排列")
                    self.ma_value.setStyleSheet("color: #4CAF50;")
                elif latest['ma5'] < latest['ma25']:
                    self.ma_value.setText("空头排列")
                    self.ma_value.setStyleSheet("color: #f44336;")
                else:
                    self.ma_value.setText("交叉区域")
                    self.ma_value.setStyleSheet("color: #FFC107;")
                logging.info(f"更新MA: MA5={latest['ma5']:.4f}, MA25={latest['ma25']:.4f}")
            else:
                logging.warning("K线数据中缺少MA指标")
            
            # 更新MACD图表
            if hasattr(self, 'macd_chart') and self.macd_chart is not None:
                # 检查是否有MACD数据
                if all(col in data.columns for col in ['macd', 'macd_signal', 'macd_diff']):
                    self.macd_chart.update_macd_chart(data)
                    logging.info("MACD图表已更新")
                else:
                    logging.warning("K线数据中缺少MACD图表所需指标 (macd, macd_signal, macd_diff)")
            
        except Exception as e:
            error_msg = f"更新图表数据出错: {str(e)}"
            self.statusBar.showMessage(error_msg)
            logging.error(error_msg)
            traceback.print_exc()  # 打印详细的错误堆栈
    
    @pyqtSlot(int, int)
    def on_monitoring_started(self, duration, interval):
        """监控开始处理"""
        self.statusBar.showMessage(f"监控已启动 - 持续时间: {duration}分钟, 刷新间隔: {interval}秒")
    
    @pyqtSlot()
    def on_monitoring_stopped(self):
        """监控停止处理"""
        self.statusBar.showMessage("监控已停止")
        self.start_button.setText("开始监控")
        self.start_button.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; }")
        self.timer.stop()
    
    @pyqtSlot(float, float)
    def on_account_balance_updated(self, balance, value):
        """处理账户余额更新"""
        # 安全检查：确保UI元素已经初始化
        if not hasattr(self, 'balance_label') or self.balance_label is None:
            logging.debug(f"账户余额更新尝试但 balance_label 未初始化 - 余额: {balance:.6f}, 价值: {value:.2f} USDT")
            return
            
        self.balance_label.setText(f"余额: {balance:.6f} | 价值: {value:.2f} USDT")
        # 记录到日志以便调试
        logging.info(f"账户余额更新 - 余额: {balance:.6f}, 价值: {value:.2f} USDT")
        
        # 根据余额是否大于0更新UI状态
        if balance > 0:
            self.balance_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            self.balance_label.setStyleSheet("")
    
    @pyqtSlot(list)
    def on_rss_news_received(self, articles):
        """处理RSS新闻接收"""
        # 清空表格
        self.rss_table.setRowCount(0)
        
        # 添加文章到表格
        for article in articles:
            row = self.rss_table.rowCount()
            self.rss_table.insertRow(row)
            
            # 转换时间为字符串
            time_str = article['time'].strftime("%Y-%m-%d %H:%M") if isinstance(article['time'], datetime) else str(article['time'])
            
            # 创建表格项
            time_item = QTableWidgetItem(time_str)
            source_item = QTableWidgetItem(article['source'])
            title_item = QTableWidgetItem(article['title'])
            summary_item = QTableWidgetItem(article['summary'])
            
            # 设置工具提示，显示完整内容
            time_item.setToolTip(time_str)
            source_item.setToolTip(article['source'])
            title_item.setToolTip(article['title'])
            
            # 保存URL数据到摘要项
            if 'url' in article and article['url']:
                summary_item.setData(Qt.UserRole, article['url'])
                # 设置工具提示，显示这是可点击项
                summary_item.setToolTip("双击查看详情")
                # 改变字体颜色，表明是可点击的链接
                summary_item.setForeground(QBrush(QColor('#0066cc')))
                
            # 设置表格项
            self.rss_table.setItem(row, 0, time_item)
            self.rss_table.setItem(row, 1, source_item)
            self.rss_table.setItem(row, 2, title_item)
            self.rss_table.setItem(row, 3, summary_item)
        
        # 更新状态栏
        self.statusBar.showMessage(f"已更新 {len(articles)} 条 RSS 新闻", 3000)
    
    @pyqtSlot(str, str, float)
    def on_alert_triggered(self, alert_type, message, value):
        """处理警报触发"""
        if alert_type == 'PRICE_CHANGE':
            # 显示价格变化警报
            title = "价格变动警报"
            icon = QMessageBox.Information
        else:
            # 显示其他类型的警报
            title = "系统警报"
            icon = QMessageBox.Warning
            
        # 使用非模态对话框显示警报，不阻塞UI
        msg = QMessageBox(icon, title, message, QMessageBox.Ok, self)
        msg.setWindowModality(Qt.NonModal)
        msg.show()
    
    def view_price_logs(self):
        """查看终端输出"""
        # 现在直接调用终端输出面板
        self.toggle_log_panel()

    def send_report_to_telegram(self):
        """发送当前报告到Telegram（在后台线程中执行）"""
        # 检查是否已经生成报告
        if not hasattr(self, 'report_data') or not self.report_data:
            QMessageBox.warning(self, "无法发送", "请先生成报告再发送到Telegram")
            return
        
        # 设置发送状态
        self.telegram_status.setText("正在发送...")
        self.telegram_status.setStyleSheet("color: #f39c12; font-size: 9px;")
        self.stop_telegram_button.setEnabled(True)
        self.send_telegram_button.setEnabled(False)
        
        # 设置中断标志
        self.telegram_send_interrupted = False
        
        # 使用线程来执行发送操作，避免阻塞UI
        import threading
        self.telegram_thread = threading.Thread(target=self._send_telegram_report_thread)
        self.telegram_thread.daemon = True
        self.telegram_thread.start()
    
    def _send_telegram_report_thread(self):
        """在后台线程中执行Telegram发送操作"""
        try:
            # 获取报告文本内容
            report_text = self.report_data.get('text_report', '')
            price_chart_path = self.report_data.get('charts', {}).get('price')
            macd_chart_path = self.report_data.get('charts', {}).get('macd')
            
            # 直接从配置文件中获取Telegram信息，确保这里是最新的配置
            try:
                # 重新加载配置文件，以获取最新的配置
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 获取Telegram配置
                TELEGRAM_TOKEN = config.get('api', {}).get('telegram', {}).get('token', '')
                TELEGRAM_CHAT_ID = config.get('api', {}).get('telegram', {}).get('chat_id', '')
                
                print(f"从配置文件获取Telegram配置 - Token长度: {len(TELEGRAM_TOKEN)}, Chat ID: {TELEGRAM_CHAT_ID}")
                
                # 如果TOKEN或CHAT_ID为空，使用自定义的发送函数
                if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
                    self._update_telegram_status("无效的Telegram配置", "red")
                    raise Exception(f"Telegram Token或Chat ID未配置：Token={TELEGRAM_TOKEN}, Chat ID={TELEGRAM_CHAT_ID}")
                
                # 自定义发送消息函数，确保使用正确的TOKEN
                def send_telegram_message(message):
                    """发送文本消息到 Telegram, 自动处理长消息分割 (增加重试机制和错误处理)"""
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
                    max_length = 4096
                    messages_to_send = []

                    # 消息分割逻辑
                    if len(message) > max_length:
                        print(f"警告:消息过长,尝试分段发送")
                        start = 0
                        while start < len(message):
                            split_point = message.rfind('\n', start, start + max_length)
                            if split_point == -1 or split_point <= start:
                                split_point = start + max_length
                            if split_point <= start:
                                 split_point = len(message)

                            part = message[start:split_point].strip()
                            if part:
                                messages_to_send.append(part)
                            start = split_point
                            if start < len(message) and message[start] == '\n':
                                start += 1
                    else:
                        messages_to_send.append(message)

                    # 循环发送分割后的消息片段，增加重试机制
                    for i, msg_part in enumerate(messages_to_send):
                        if not msg_part: continue
                        payload = {'chat_id': TELEGRAM_CHAT_ID, 'text': msg_part}

                        # 增加调试信息
                        print(f"准备发送Telegram消息: URL={url}")
                        print(f"Payload: chat_id={TELEGRAM_CHAT_ID}, 消息长度={len(msg_part)}")

                        # 增加重试机制
                        max_retries = 3
                        retry_delay = 2
                        for attempt in range(max_retries):
                            try:
                                # 增加超时时间，并使用更安全的 SSL 配置
                                session = requests.Session()
                                session.mount('https://', requests.adapters.HTTPAdapter(max_retries=3))
                                response = session.post(url, data=payload, timeout=30, verify=True)
                                response.raise_for_status()
                                print(f"Telegram消息发送成功：状态码 {response.status_code}")
                                if len(messages_to_send) > 1: time.sleep(0.5)
                                break  # 成功发送，跳出重试循环
                            except requests.exceptions.SSLError as e:
                                print(f"Telegram SSL错误 (尝试 {attempt+1}/{max_retries}): {e}")
                                if attempt < max_retries - 1:
                                    print(f"等待 {retry_delay} 秒后重试...")
                                    time.sleep(retry_delay)
                                    retry_delay *= 2  # 指数退避策略
                                else:
                                    print(f"Telegram SSL连接失败，已达最大重试次数")
                                    # 尝试备用通知方式，例如打印到控制台或记录到日志
                                    print(f"【重要通知】{msg_part}")
                            except requests.exceptions.RequestException as e:
                                print(f"Telegram通知失败 (尝试 {attempt+1}/{max_retries}): {e}")
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay)
                                    retry_delay *= 2
                                else:
                                    print(f"Telegram通知失败，已达最大重试次数")
                                    print(f"【重要通知】{msg_part}")
                            except Exception as e:
                                print(f"发送Telegram时未知错误: {e}")
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay)
                                else:
                                    print(f"【重要通知】{msg_part}")
                
                # 自定义发送图片函数，确保使用正确的TOKEN
                def send_telegram_photo(photo_path, caption=""):
                    """发送图片到 Telegram (增加重试机制和错误处理)"""
                    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
                    print(f"准备发送Telegram图片: URL={url}")

                    # 增加重试机制
                    max_retries = 3
                    retry_delay = 2

                    for attempt in range(max_retries):
                        try:
                            with open(photo_path, 'rb') as f:
                                files = {'photo': f}
                                data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': caption}

                                # 使用会话和更安全的 SSL 配置
                                session = requests.Session()
                                session.mount('https://', requests.adapters.HTTPAdapter(max_retries=3))
                                response = session.post(url, files=files, data=data, timeout=60, verify=True)
                                response.raise_for_status()
                                print(f"成功发送图片: {os.path.basename(photo_path)}")
                                return  # 成功发送，退出函数

                        except FileNotFoundError:
                            print(f"错误:找不到图片 {photo_path}")
                            # 文件不存在不需要重试
                            return

                        except requests.exceptions.SSLError as e:
                            print(f"Telegram图片发送 SSL错误 (尝试 {attempt+1}/{max_retries}): {e}")
                            if attempt < max_retries - 1:
                                print(f"等待 {retry_delay} 秒后重试...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                            else:
                                print(f"Telegram图片发送 SSL连接失败，已达最大重试次数")
                                print(f"无法发送图片: {os.path.basename(photo_path)}")

                        except requests.exceptions.RequestException as e:
                            print(f"Telegram图片通知失败 (尝试 {attempt+1}/{max_retries}): {e}")
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                retry_delay *= 2
                            else:
                                print(f"Telegram图片通知失败，已达最大重试次数")

                        except Exception as e:
                            print(f"发送Telegram图片未知错误: {e}")
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                            else:
                                print(f"发送图片失败: {os.path.basename(photo_path)}")
            except Exception as config_error:
                raise Exception(f"获取Telegram配置失败: {config_error}")
            
            # 检查中断标志
            if self.telegram_send_interrupted:
                self._update_telegram_status("已中断", "red")
                return
                
            # 发送文本报告
            if report_text:
                send_telegram_message(report_text)
            
            # 检查中断标志
            if self.telegram_send_interrupted:
                self._update_telegram_status("已中断", "red")
                return
                
            # 发送价格图表
            if price_chart_path and os.path.exists(price_chart_path):
                send_telegram_photo(price_chart_path, "SHELL/USDT 价格走势图")
            
            # 检查中断标志
            if self.telegram_send_interrupted:
                self._update_telegram_status("已中断", "red")
                return
                
            # 发送MACD图表
            if macd_chart_path and os.path.exists(macd_chart_path):
                send_telegram_photo(macd_chart_path, "SHELL/USDT MACD技术指标")
            elif report_text and not self.telegram_send_interrupted:
                send_telegram_message("ℹ️ MACD 技术指标图因数据不足未生成。")
            
            # 完成发送后更新状态
            if not self.telegram_send_interrupted:
                self._update_telegram_status("发送成功", "green")
        except Exception as e:
            # 发送失败更新状态
            self._update_telegram_status("发送失败", "red")
            print(f"发送报告到Telegram失败: {str(e)}")
        finally:
            # 在UI线程中重置按钮状态
            from PyQt5.QtCore import QMetaObject, Qt, Q_ARG
            QMetaObject.invokeMethod(self.stop_telegram_button, "setEnabled", 
                                   Qt.QueuedConnection, Q_ARG(bool, False))
            QMetaObject.invokeMethod(self.send_telegram_button, "setEnabled", 
                                   Qt.QueuedConnection, Q_ARG(bool, True))
    
    def _update_telegram_status(self, status, color):
        """在UI线程中更新Telegram状态文本"""
        from PyQt5.QtCore import QMetaObject, Qt, Q_ARG
        color_map = {
            "red": "#e74c3c",
            "green": "#2ecc71",
            "orange": "#f39c12"
        }
        style = f"color: {color_map.get(color, '#3498db')}; font-size: 9px;"
        QMetaObject.invokeMethod(self.telegram_status, "setText", 
                               Qt.QueuedConnection, Q_ARG(str, status))
        QMetaObject.invokeMethod(self.telegram_status, "setStyleSheet", 
                               Qt.QueuedConnection, Q_ARG(str, style))
    
    def stop_telegram_sending(self):
        """中断Telegram发送过程"""
        if hasattr(self, 'telegram_thread') and self.telegram_thread.is_alive():
            self.telegram_send_interrupted = True
            self.telegram_status.setText("正在中断...")
            self.telegram_status.setStyleSheet("color: #e67e22; font-size: 9px;")

    def toggle_report_panel(self):
        """切换报告面板的显示与隐藏状态，不自动生成报告"""
        if self.report_panel.isVisible():
            # 如果当前可见，则隐藏面板
            self.report_panel.setVisible(False)
            self.splitter.setSizes([1000, 0])
            self.report_button.setText("显示报告")
            
            # 设置窗口最小宽度为更小的值，允许用户调整为更窄的窗口
            self.setMinimumSize(800, 700)
        else:
            # 如果当前隐藏，则只显示面板，不生成报告
            self.report_panel.setVisible(True)
            self.splitter.setSizes([500, 500])  # 左右等分
            self.report_button.setText("隐藏报告")
            
            # 恢复窗口最小宽度
            self.setMinimumSize(1000, 700)

    def show_and_generate_report(self):
        """显示侧边栏并生成新报告"""
        # 确保报告面板可见
        self.report_panel.setVisible(True)
        self.splitter.setSizes([500, 500])  # 左右等分
        self.report_button.setText("隐藏报告")
        
        # 生成新报告
        self.generate_report()

    def generate_report(self):
        """生成并显示完整报告"""
        # 检查是否有监控数据
        if not hasattr(self.tracker, 'price_log') or not self.tracker.price_log:
            # 如果没有监控数据，询问用户是否想要生成当前快照报告
            reply = QMessageBox.question(self, "没有监控数据",
                                "您当前没有启动监控或没有收集到价格数据。是否要生成当前市场快照报告？",
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            
            if reply == QMessageBox.No:
                return
                
        # 显示生成报告中的提示
        self.statusBar.showMessage("正在生成报告，请稍候...")
        
        # 设置图表保存目录和日志目录
        self.tracker.charts_dir = self.charts_dir
        self.tracker.log_dir = self.log_dir
                
        # 调用追踪器的报告生成方法
        self.report_data = self.tracker.generate_status_report()
        
        if 'error' in self.report_data:
            QMessageBox.warning(self, "报告生成失败", self.report_data['error'])
            self.statusBar.showMessage("报告生成失败", 3000)
            return
            
        # 更新报告文本内容 - 使用HTML格式美化输出
        report_text = self.report_data['text_report'].replace('\n', '<br>')
        # 应用一些基本HTML样式
        styled_report = f"""
        <div style='font-family: Arial, sans-serif; line-height: 1.6;'>
            {report_text}
        </div>
        """
        self.report_text.setHtml(styled_report)
        
        # 重置图表路径
        self.price_chart_path = None
        self.macd_chart_path = None
        
        # 更新图表
        if 'price' in self.report_data.get('charts', {}):
            self.price_chart_path = self.report_data['charts']['price']
            pixmap = QPixmap(self.price_chart_path)
            if not pixmap.isNull():
                # 调整图片大小为固定宽度300像素，保持比例
                pixmap = pixmap.scaledToWidth(300, Qt.SmoothTransformation)
                self.price_chart_label.setPixmap(pixmap)
                self.price_chart_label.setVisible(True)
                self.price_chart_label.setToolTip("点击查看大图")
                
                # 记录日志
                logging.info(f"已加载价格图表: {self.price_chart_path}")
            else:
                self.price_chart_label.setVisible(False)
                logging.warning(f"无法加载价格图表: {self.price_chart_path}")
        else:
            self.price_chart_label.setVisible(False)
            logging.info("报告中不包含价格图表")
            
        if 'macd' in self.report_data.get('charts', {}):
            self.macd_chart_path = self.report_data['charts']['macd']
            pixmap = QPixmap(self.macd_chart_path)
            if not pixmap.isNull():
                # 调整图片大小为固定宽度300像素，保持比例
                pixmap = pixmap.scaledToWidth(300, Qt.SmoothTransformation)
                self.macd_chart_label.setPixmap(pixmap)
                self.macd_chart_label.setVisible(True)
                self.macd_chart_label.setToolTip("点击查看大图")
                
                # 记录日志
                logging.info(f"已加载MACD图表: {self.macd_chart_path}")
            else:
                self.macd_chart_label.setVisible(False)
                logging.warning(f"无法加载MACD图表: {self.macd_chart_path}")
        else:
            self.macd_chart_label.setVisible(False)
            logging.info("报告中不包含MACD图表")
        
        # 更新交易信号 - 从报告数据中获取
        self.update_trading_signals_from_report()
            
        # 显示报告面板
        self.report_panel.setVisible(True)
        self.splitter.setSizes([500, 500])  # 左右等分
        
        # 更新状态栏和按钮文本
        self.statusBar.showMessage("报告生成成功", 3000)
        self.report_button.setText("隐藏报告")
        
        # 如果开启了自动发送到Telegram的选项，则自动发送
        if hasattr(self, 'auto_telegram_checkbox') and self.auto_telegram_checkbox.isChecked():
            self.send_report_to_telegram()
            
    def update_trading_signals_from_report(self):
        """从报告数据中更新交易信号显示"""
        if not hasattr(self, 'report_data') or not self.report_data:
            return
            
        try:
            # 从报告数据中提取技术分析信息
            tech_analysis = self.report_data.get('tech_analysis', {})
            sentiment_info = self.report_data.get('sentiment', {})
            
            if tech_analysis:
                # 确定信号类型
                macd_trend = tech_analysis.get('macd_trend', '')
                ma_trend = tech_analysis.get('ma_trend', '')
                rsi = tech_analysis.get('rsi')
                
                # 根据技术指标确定信号
                signal_type = "NEUTRAL"
                recommendation = tech_analysis.get('advice', '无法提供建议')
                
                # 直接根据建议文本判断信号类型
                if "买入" in recommendation or "反弹" in recommendation:
                    signal_type = "BUY"
                elif "卖出" in recommendation or "回调" in recommendation:
                    signal_type = "SELL"
                # 如果建议文本不明确，再根据指标判断
                else:
                    if macd_trend == "看涨" and ma_trend == "多头排列":
                        signal_type = "BUY"
                    elif macd_trend == "看跌" and ma_trend == "空头排列":
                        signal_type = "SELL"
                    elif rsi is not None:
                        if rsi > 70:
                            signal_type = "SELL"  # RSI超买
                        elif rsi < 30:
                            signal_type = "BUY"   # RSI超卖
                
                # 计算置信度
                confidence = 50  # 默认中等置信度
                if signal_type != "NEUTRAL":
                    # 使用波动率、RSI偏离中值程度、MACD信号强度等计算置信度
                    if rsi is not None:
                        # RSI偏离中值(50)越远，置信度越高
                        rsi_confidence = min(100, int(abs(rsi - 50) * 2))
                        confidence = max(confidence, rsi_confidence)
                    
                    # 如果有情感分析，考虑情感因素
                    sentiment = sentiment_info.get('sentiment', 'neutral')
                    sentiment_confidence = sentiment_info.get('confidence', 50)
                    
                    # 如果情感和技术信号一致，提高置信度
                    if (signal_type == "BUY" and sentiment == "positive") or \
                       (signal_type == "SELL" and sentiment == "negative"):
                        confidence = min(100, confidence + 10)
                
                # 更新UI
                self.on_signal_status_updated(signal_type, recommendation, confidence)
        except Exception as e:
            logging.error(f"从报告更新交易信号时出错: {e}")
            # 出错时不更新信号，保持当前状态

    def show_price_chart_fullsize(self, event):
        """显示价格图表的全尺寸视图"""
        if hasattr(self, 'price_chart_path') and self.price_chart_path:
            self.show_fullsize_image(self.price_chart_path, "价格图表")
            
    def show_macd_chart_fullsize(self, event):
        """显示MACD图表的全尺寸视图"""
        if hasattr(self, 'macd_chart_path') and self.macd_chart_path:
            self.show_fullsize_image(self.macd_chart_path, "MACD图表")
            
    def show_fullsize_image(self, image_path, title):
        """显示全尺寸图像的对话框"""
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setModal(True)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        
        # 创建图像标签
        image_label = QLabel()
        pixmap = QPixmap(image_path)
        
        # 如果图像太大，则调整大小以适应屏幕
        screen_size = QApplication.desktop().availableGeometry(self).size()
        if pixmap.width() > screen_size.width() * 0.8 or pixmap.height() > screen_size.height() * 0.8:
            pixmap = pixmap.scaled(screen_size.width() * 0.8, screen_size.height() * 0.8, 
                                Qt.KeepAspectRatio, Qt.SmoothTransformation)
        
        image_label.setPixmap(pixmap)
        layout.addWidget(image_label)
        
        # 添加关闭按钮
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        
        # 显示对话框
        dialog.resize(pixmap.width() + 40, pixmap.height() + 80)  # 添加一些边距
        dialog.exec_()

    def on_rss_table_cell_double_clicked(self, row, column):
        """处理RSS表格双击事件"""
        # 只处理摘要列的双击事件
        if column != 3:  # 摘要列索引为3
            return
            
        # 显示RSS文章详情
        self.show_rss_article_detail(row)
    
    def on_news_table_cell_double_clicked(self, row, column):
        """处理新闻表格双击事件"""
        # 只处理新闻摘要列的双击事件
        if column != 1:  # 新闻摘要列索引为1
            return
            
        # 显示新闻详情
        self.show_news_detail(row)
        
    def show_news_detail(self, row):
        """显示新闻详情"""
        # 检查行索引是否有效
        if row < 0 or row >= self.news_table.rowCount():
            return
            
        # 获取新闻项和时间项
        news_item = self.news_table.item(row, 1)
        time_item = self.news_table.item(row, 0)
        
        if not news_item or not time_item:
            return
            
        news_text = news_item.text()
        time_text = time_item.text()
        
        # 获取可能的完整内容
        full_text = news_item.data(Qt.UserRole) if news_item.data(Qt.UserRole) else news_text
        
        # 创建详情对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"新闻详情")
        dialog.setMinimumSize(600, 300)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        
        # 创建时间标签
        time_label = QLabel(f"发布时间: {time_text}")
        time_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(time_label)
        
        # 创建内容文本框
        content_text = QTextBrowser()
        content_text.setHtml(f"<p style='font-size: 12px; line-height: 1.5;'>{full_text}</p>")
        layout.addWidget(content_text)
        
        # 添加关闭按钮
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        
        # 显示对话框
        dialog.exec_()

    def show_rss_article_detail(self, row):
        """显示RSS文章的详细内容"""
        # 检查行索引是否有效
        if row < 0 or row >= self.rss_table.rowCount():
            return
            
        # 获取文章标题和摘要
        title = self.rss_table.item(row, 2).text()  # 标题在第3列
        summary = self.rss_table.item(row, 3).text()  # 摘要在第4列
        source = self.rss_table.item(row, 1).text()  # 来源在第2列
        time = self.rss_table.item(row, 0).text()    # 时间在第1列
        
        # 尝试获取URL（保存在item的userData中）
        url = None
        try:
            url_item = self.rss_table.item(row, 3)  # URL存储在摘要项的userData中
            if url_item and hasattr(url_item, 'data'):
                url_role = Qt.UserRole  # Qt.UserRole是用于存储自定义数据的角色
                url = url_item.data(url_role)
        except Exception as e:
            logging.error(f"获取RSS文章URL时出错: {e}")
        
        # 创建详情对话框
        dialog = QDialog(self)
        dialog.setWindowTitle(f"RSS文章详情 - {source}")
        dialog.setMinimumSize(600, 400)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        
        # 创建时间标签
        time_label = QLabel(f"发布时间: {time}")
        time_label.setStyleSheet("color: #666; font-size: 10px;")
        layout.addWidget(time_label)
        
        # 创建标题标签
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        title_label.setWordWrap(True)
        layout.addWidget(title_label)
        
        # 创建内容文本框
        content_text = QTextBrowser()
        content_text.setHtml(f"<p style='font-size: 12px; line-height: 1.5;'>{summary}</p>")
        content_text.setOpenExternalLinks(True)  # 允许打开外部链接
        layout.addWidget(content_text)
        
        # 如果有URL，添加按钮打开在浏览器中查看
        if url:
            button_layout = QHBoxLayout()
            
            open_button = QPushButton("在浏览器中查看")
            open_button.clicked.connect(lambda: self.open_url_in_browser(url))
            button_layout.addWidget(open_button)
            
            close_button = QPushButton("关闭")
            close_button.clicked.connect(dialog.accept)
            button_layout.addWidget(close_button)
            
            layout.addLayout(button_layout)
        else:
            # 没有URL，只添加关闭按钮
            close_button = QPushButton("关闭")
            close_button.clicked.connect(dialog.accept)
            layout.addWidget(close_button)
        
        # 显示对话框
        dialog.exec_()
    
    def open_url_in_browser(self, url):
        """在默认浏览器中打开URL"""
        if not url:
            return
            
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception as e:
            logging.error(f"打开URL失败: {e}")
            QMessageBox.warning(self, "打开失败", f"无法打开URL: {e}")

    def toggle_log_panel(self):
        """切换日志面板的显示与隐藏"""
        if self.log_panel.isVisible():
            # 如果当前可见，则隐藏面板
            self.log_panel.setVisible(False)
            self.vertical_splitter.setSizes([1, 0])
        else:
            # 如果当前隐藏，则显示面板
            self.log_panel.setVisible(True)
            self.vertical_splitter.setSizes([700, 300])  # 调整大小比例
            
            # 清空当前内容并重新显示最近的日志
            self.log_text.clear()
            if self.console_log:
                # 获取最近的最多100行
                last_lines = self.console_log[-100:] if len(self.console_log) > 100 else self.console_log
                log_content = "".join(last_lines)
                self.log_text.setText(f"系统终端输出：\n\n{log_content}")
                self.log_text.moveCursor(self.log_text.textCursor().End)
            else:
                self.log_text.setText("暂无系统终端输出。")
            
    def clear_log(self):
        """清空日志显示"""
        self.log_text.clear()
        self.log_text.setText("系统终端输出：\n\n")
        # 清空日志缓存
        self.console_log = []
    
    def update_log_display(self):
        """刷新日志显示，重新加载完整的控制台日志"""
        try:
            # 清空当前文本
            self.log_text.clear()
            
            # 获取最近的控制台输出
            if self.console_log:
                # 最多显示最后200行以提供更多上下文
                last_lines = self.console_log[-200:] if len(self.console_log) > 200 else self.console_log
                log_content = "".join(last_lines)
                self.log_text.setText(f"系统终端输出：\n\n{log_content}")
            else:
                self.log_text.setText("暂无系统终端输出。")
                
            # 输出一条测试信息，以验证日志捕获功能
            print("系统日志已刷新 - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            # 滚动到底部
            self.log_text.moveCursor(self.log_text.textCursor().End)
            
        except Exception as e:
            self.log_text.setText(f"读取日志信息失败: {str(e)}\n{traceback.format_exc()}")
            
    @pyqtSlot(str)
    def on_console_output(self, text):
        """处理控制台输出信号"""
        # 添加新的输出内容到日志列表
        self.console_log.append(text)
        
        # 限制日志列表的大小
        if len(self.console_log) > self.max_log_lines:
            self.console_log = self.console_log[-self.max_log_lines:]
        
        # 如果日志面板正在显示，则追加内容
        if self.log_panel.isVisible():
            # 追加新内容而不是替换整个文本
            self.log_text.append(text)
            
            # 确保滚动到底部，以显示最新内容
            self.log_text.moveCursor(self.log_text.textCursor().End)
    
    def toggle_auto_report(self):
        """切换自动生成报告功能的开/关状态"""
        if self.auto_report_toggle.isChecked():
            # 获取所选时间间隔（毫秒）
            interval_text = self.auto_report_interval.currentText()
            if interval_text == "1分钟":
                interval_ms = 60 * 1000
            elif interval_text == "5分钟":
                interval_ms = 5 * 60 * 1000
            elif interval_text == "15分钟":
                interval_ms = 15 * 60 * 1000
            elif interval_text == "30分钟":
                interval_ms = 30 * 60 * 1000
            elif interval_text == "1小时":
                interval_ms = 60 * 60 * 1000
            else:
                interval_ms = 5 * 60 * 1000  # 默认5分钟
            
            # 设置定时器并启动
            self.auto_report_timer.setInterval(interval_ms)
            self.auto_report_timer.start()
            
            # 更新按钮文本和样式
            self.auto_report_toggle.setText("停止自动")
            self.auto_report_toggle.setStyleSheet("QPushButton { background-color: #e74c3c; color: white; padding: 5px; }")
            
            # 更新状态栏
            self.statusBar.showMessage(f"自动报告已开启，时间间隔: {interval_text}", 3000)
            
            # 立即生成一份报告
            self.generate_report()
        else:
            # 停止定时器
            self.auto_report_timer.stop()
            
            # 更新按钮文本和样式
            self.auto_report_toggle.setText("开启自动")
            self.auto_report_toggle.setStyleSheet("QPushButton { background-color: #3498db; color: white; padding: 5px; }")
            
            # 更新状态栏
            self.statusBar.showMessage("自动报告已停止", 3000)
    
    def closeEvent(self, event):
        """在应用程序关闭前恢复原始输出流，停止所有定时器"""
        # 停止自动报告定时器
        if hasattr(self, 'auto_report_timer'):
            self.auto_report_timer.stop()
            
        # 恢复标准输出和标准错误输出流
        if hasattr(self, 'stdout_redirector') and hasattr(self.stdout_redirector, 'original_stream'):
            sys.stdout = self.stdout_redirector.original_stream
        if hasattr(self, 'stderr_redirector') and hasattr(self.stderr_redirector, 'original_stream'):
            sys.stderr = self.stderr_redirector.original_stream
            
        # 记录应用关闭信息
        logging.info("应用程序正常关闭")
        
        # 继续标准的关闭事件
        super().closeEvent(event)