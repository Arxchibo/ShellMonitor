#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import json
import logging
from PyQt5.QtWidgets import (QDialog, QTabWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QDoubleSpinBox, QSpinBox, 
                            QCheckBox, QGroupBox, QPushButton, QFileDialog,
                            QComboBox, QDialogButtonBox, QFormLayout, QMessageBox,
                            QWidget)
from PyQt5.QtCore import Qt, QSettings

class SettingsDialog(QDialog):
    """设置对话框，用于配置应用程序参数"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 使用绝对路径
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_file = os.path.join(script_dir, "config.json")
        logging.info(f"配置文件路径: {self.config_file}")
        
        self.config = self.load_config()
        
        self.setWindowTitle("设置")
        self.resize(600, 500)
        
        self.setup_ui()
        self.load_settings_to_ui()
    
    def setup_ui(self):
        """设置UI组件"""
        main_layout = QVBoxLayout(self)
        
        # 创建选项卡
        self.tab_widget = QTabWidget()
        
        # === API设置选项卡 ===
        api_tab = QWidget()
        api_layout = QVBoxLayout(api_tab)
        
        # Binance API设置
        binance_group = QGroupBox("Binance API")
        binance_form = QFormLayout(binance_group)
        
        self.binance_key = QLineEdit()
        self.binance_secret = QLineEdit()
        self.binance_secret.setEchoMode(QLineEdit.Password)
        
        binance_form.addRow("API Key:", self.binance_key)
        binance_form.addRow("API Secret:", self.binance_secret)
        
        # Telegram设置
        telegram_group = QGroupBox("Telegram 通知")
        telegram_form = QFormLayout(telegram_group)
        
        self.telegram_enabled = QCheckBox("启用 Telegram 通知")
        self.telegram_token = QLineEdit()
        self.telegram_chat_id = QLineEdit()
        
        telegram_form.addRow(self.telegram_enabled)
        telegram_form.addRow("Bot Token:", self.telegram_token)
        telegram_form.addRow("Chat ID:", self.telegram_chat_id)
        
        # 新闻API设置
        news_group = QGroupBox("新闻与情感分析 API")
        news_form = QFormLayout(news_group)
        
        self.news_enabled = QCheckBox("启用新闻获取和情感分析")
        self.gnews_key = QLineEdit()
        self.newsapi_key = QLineEdit()
        self.deepseek_key = QLineEdit()
        
        news_form.addRow(self.news_enabled)
        news_form.addRow("GNews API Key:", self.gnews_key)
        news_form.addRow("NewsAPI Key:", self.newsapi_key)
        news_form.addRow("DeepSeek API Key:", self.deepseek_key)
        
        # 添加到API设置布局
        api_layout.addWidget(binance_group)
        api_layout.addWidget(telegram_group)
        api_layout.addWidget(news_group)
        
        # === 交易设置选项卡 ===
        trading_tab = QWidget()
        trading_layout = QVBoxLayout(trading_tab)
        
        # 交易对设置
        symbol_group = QGroupBox("交易对设置")
        symbol_form = QFormLayout(symbol_group)
        
        self.symbol_input = QLineEdit()
        self.interval_combo = QComboBox()
        self.interval_combo.addItems(["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "1d"])
        
        symbol_form.addRow("交易对:", self.symbol_input)
        symbol_form.addRow("K线间隔:", self.interval_combo)
        
        # 风险管理设置
        risk_group = QGroupBox("风险管理")
        risk_form = QFormLayout(risk_group)
        
        self.stop_loss = QDoubleSpinBox()
        self.stop_loss.setRange(0.5, 50.0)
        self.stop_loss.setSingleStep(0.5)
        self.stop_loss.setSuffix("%")
        
        self.take_profit = QDoubleSpinBox()
        self.take_profit.setRange(0.5, 100.0)
        self.take_profit.setSingleStep(0.5)
        self.take_profit.setSuffix("%")
        
        self.trade_quantity = QDoubleSpinBox()
        self.trade_quantity.setRange(1, 10000)
        self.trade_quantity.setSingleStep(10)
        
        risk_form.addRow("止损百分比:", self.stop_loss)
        risk_form.addRow("止盈百分比:", self.take_profit)
        risk_form.addRow("交易数量:", self.trade_quantity)
        
        # 情感分析设置
        sentiment_group = QGroupBox("情感分析")
        sentiment_form = QFormLayout(sentiment_group)
        
        self.sentiment_enabled = QCheckBox("将情感分析纳入交易决策")
        self.sentiment_weight = QDoubleSpinBox()
        self.sentiment_weight.setRange(0.0, 1.0)
        self.sentiment_weight.setSingleStep(0.1)
        self.sentiment_weight.setDecimals(1)
        
        sentiment_form.addRow(self.sentiment_enabled)
        sentiment_form.addRow("情感权重:", self.sentiment_weight)
        
        # 添加到交易设置布局
        trading_layout.addWidget(symbol_group)
        trading_layout.addWidget(risk_group)
        trading_layout.addWidget(sentiment_group)
        
        # === 监控设置选项卡 ===
        monitor_tab = QWidget()
        monitor_layout = QVBoxLayout(monitor_tab)
        
        # 时间设置
        time_group = QGroupBox("时间设置")
        time_form = QFormLayout(time_group)
        
        self.duration = QSpinBox()
        self.duration.setRange(1, 1440)  # 1分钟到24小时
        self.duration.setSuffix(" 分钟")
        
        self.refresh_interval = QSpinBox()
        self.refresh_interval.setRange(5, 300)  # 5秒到5分钟
        self.refresh_interval.setSuffix(" 秒")
        
        time_form.addRow("监控持续时间:", self.duration)
        time_form.addRow("数据刷新间隔:", self.refresh_interval)
        
        # 提醒设置
        alert_group = QGroupBox("提醒设置")
        alert_form = QFormLayout(alert_group)
        
        self.price_alert = QDoubleSpinBox()
        self.price_alert.setRange(0.1, 10.0)
        self.price_alert.setSingleStep(0.1)
        self.price_alert.setDecimals(1)
        self.price_alert.setSuffix("%")
        
        alert_form.addRow("价格波动提醒阈值:", self.price_alert)
        
        # 新闻查询设置
        news_query_group = QGroupBox("新闻查询设置")
        news_query_form = QFormLayout(news_query_group)
        
        self.news_query = QLineEdit()
        self.max_news = QSpinBox()
        self.max_news.setRange(1, 10)
        
        news_query_form.addRow("新闻搜索关键词:", self.news_query)
        news_query_form.addRow("每个来源最大新闻数:", self.max_news)
        
        # 添加到监控设置布局
        monitor_layout.addWidget(time_group)
        monitor_layout.addWidget(alert_group)
        monitor_layout.addWidget(news_query_group)
        
        # === UI设置选项卡 ===
        ui_tab = QWidget()
        ui_layout = QVBoxLayout(ui_tab)
        
        # 主题设置
        theme_group = QGroupBox("主题设置")
        theme_form = QFormLayout(theme_group)
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["亮色", "暗色"])
        
        theme_form.addRow("主题:", self.theme_combo)
        
        # 提示音设置
        sound_group = QGroupBox("提示音设置")
        sound_form = QFormLayout(sound_group)
        
        self.sound_enabled = QCheckBox("启用声音提示")
        self.desktop_notification = QCheckBox("启用桌面通知")
        
        sound_form.addRow(self.sound_enabled)
        sound_form.addRow(self.desktop_notification)
        
        # 图表设置
        chart_group = QGroupBox("图表设置")
        chart_form = QFormLayout(chart_group)
        
        self.chart_update = QSpinBox()
        self.chart_update.setRange(500, 10000)
        self.chart_update.setSingleStep(100)
        self.chart_update.setSuffix(" 毫秒")
        
        chart_form.addRow("图表更新间隔:", self.chart_update)
        
        # 添加到UI设置布局
        ui_layout.addWidget(theme_group)
        ui_layout.addWidget(sound_group)
        ui_layout.addWidget(chart_group)
        
        # 添加选项卡到选项卡控件
        self.tab_widget.addTab(api_tab, "API设置")
        self.tab_widget.addTab(trading_tab, "交易设置")
        self.tab_widget.addTab(monitor_tab, "监控设置")
        self.tab_widget.addTab(ui_tab, "界面设置")
        
        # 添加到主布局
        main_layout.addWidget(self.tab_widget)
        
        # 对话框按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        
        main_layout.addWidget(button_box)
    
    def load_config(self):
        """从配置文件加载设置"""
        try:
            logging.info(f"尝试加载配置文件: {self.config_file}")
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    logging.info("配置文件存在，正在读取")
                    config = json.load(f)
                    logging.debug(f"读取到的配置内容: {config}")
                    return config
            else:
                logging.warning("配置文件不存在，将使用默认配置")
                # 返回默认配置
                default_config = {
                    "api": {
                        "binance": {"api_key": "", "api_secret": ""},
                        "telegram": {"token": "", "chat_id": "", "enabled": True},
                        "news": {
                            "gnews_api_key": "",
                            "newsapi_api_key": "",
                            "deepseek_api_key": "",
                            "deepseek_api_url": "https://api.deepseek.com/v1/chat/completions",
                            "enabled": True
                        }
                    },
                    "trading": {
                        "symbol": "SHELLUSDT",
                        "interval": "15m",
                        "stop_loss_percent": 5.0,
                        "take_profit_percent": 10.0,
                        "trade_quantity": 100,
                        "sentiment_influence_enabled": True,
                        "sentiment_influence_weight": 0.5
                    },
                    "monitoring": {
                        "duration_minutes": 120,
                        "refresh_interval_seconds": 15,
                        "price_alert_threshold": 1.0,
                        "news_query": "MyShell OR SHELL coin crypto",
                        "max_news_per_source": 3
                    },
                    "ui": {
                        "theme": "dark",
                        "language": "zh_CN",
                        "chart_update_interval_ms": 1000,
                        "enable_sound_alerts": True,
                        "show_desktop_notifications": True
                    }
                }
                logging.debug(f"默认配置: {default_config}")
                return default_config
        except Exception as e:
            logging.error(f"加载配置文件出错: {e}", exc_info=True)
            QMessageBox.warning(self, "配置加载错误", f"加载配置文件时出错: {str(e)}")
            return {}
    
    def load_settings_to_ui(self):
        """将配置加载到UI控件"""
        if not self.config:
            return
        
        # API设置
        try:
            # Binance
            self.binance_key.setText(self.config["api"]["binance"]["api_key"])
            self.binance_secret.setText(self.config["api"]["binance"]["api_secret"])
            
            # Telegram
            self.telegram_enabled.setChecked(self.config["api"]["telegram"]["enabled"])
            self.telegram_token.setText(self.config["api"]["telegram"]["token"])
            self.telegram_chat_id.setText(self.config["api"]["telegram"]["chat_id"])
            
            # 新闻API
            self.news_enabled.setChecked(self.config["api"]["news"]["enabled"])
            self.gnews_key.setText(self.config["api"]["news"]["gnews_api_key"])
            self.newsapi_key.setText(self.config["api"]["news"]["newsapi_api_key"])
            self.deepseek_key.setText(self.config["api"]["news"]["deepseek_api_key"])
            
            # 交易设置
            self.symbol_input.setText(self.config["trading"]["symbol"])
            self.interval_combo.setCurrentText(self.config["trading"]["interval"])
            self.stop_loss.setValue(self.config["trading"]["stop_loss_percent"])
            self.take_profit.setValue(self.config["trading"]["take_profit_percent"])
            self.trade_quantity.setValue(self.config["trading"]["trade_quantity"])
            self.sentiment_enabled.setChecked(self.config["trading"]["sentiment_influence_enabled"])
            self.sentiment_weight.setValue(self.config["trading"]["sentiment_influence_weight"])
            
            # 监控设置
            self.duration.setValue(self.config["monitoring"]["duration_minutes"])
            self.refresh_interval.setValue(self.config["monitoring"]["refresh_interval_seconds"])
            self.price_alert.setValue(self.config["monitoring"]["price_alert_threshold"])
            self.news_query.setText(self.config["monitoring"]["news_query"])
            self.max_news.setValue(self.config["monitoring"]["max_news_per_source"])
            
            # UI设置
            theme_index = 1 if self.config["ui"]["theme"] == "dark" else 0
            self.theme_combo.setCurrentIndex(theme_index)
            self.sound_enabled.setChecked(self.config["ui"]["enable_sound_alerts"])
            self.desktop_notification.setChecked(self.config["ui"]["show_desktop_notifications"])
            self.chart_update.setValue(self.config["ui"]["chart_update_interval_ms"])
        except Exception as e:
            QMessageBox.warning(self, "设置加载错误", f"加载设置到UI时出错: {str(e)}")
    
    def accept(self):
        """保存设置并关闭对话框"""
        try:
            logging.info("开始保存设置")
            
            # 记录配置结构
            logging.debug(f"配置对象结构: {type(self.config)}")
            logging.debug(f"配置内容: {self.config}")
            
            # 更新配置
            # API设置
            logging.debug("更新 Binance API 设置")
            if "api" not in self.config:
                logging.warning("配置中缺少'api'键，初始化为空字典")
                self.config["api"] = {}
            
            if "binance" not in self.config["api"]:
                logging.warning("配置中缺少'binance'键，初始化为空字典")
                self.config["api"]["binance"] = {}
            
            self.config["api"]["binance"]["api_key"] = self.binance_key.text()
            self.config["api"]["binance"]["api_secret"] = self.binance_secret.text()
            
            self.config["api"]["telegram"]["enabled"] = self.telegram_enabled.isChecked()
            self.config["api"]["telegram"]["token"] = self.telegram_token.text()
            self.config["api"]["telegram"]["chat_id"] = self.telegram_chat_id.text()
            
            self.config["api"]["news"]["enabled"] = self.news_enabled.isChecked()
            self.config["api"]["news"]["gnews_api_key"] = self.gnews_key.text()
            self.config["api"]["news"]["newsapi_api_key"] = self.newsapi_key.text()
            self.config["api"]["news"]["deepseek_api_key"] = self.deepseek_key.text()
            
            # 交易设置
            self.config["trading"]["symbol"] = self.symbol_input.text()
            self.config["trading"]["interval"] = self.interval_combo.currentText()
            self.config["trading"]["stop_loss_percent"] = self.stop_loss.value()
            self.config["trading"]["take_profit_percent"] = self.take_profit.value()
            self.config["trading"]["trade_quantity"] = self.trade_quantity.value()
            self.config["trading"]["sentiment_influence_enabled"] = self.sentiment_enabled.isChecked()
            self.config["trading"]["sentiment_influence_weight"] = self.sentiment_weight.value()
            
            # 监控设置
            self.config["monitoring"]["duration_minutes"] = self.duration.value()
            self.config["monitoring"]["refresh_interval_seconds"] = self.refresh_interval.value()
            self.config["monitoring"]["price_alert_threshold"] = self.price_alert.value()
            self.config["monitoring"]["news_query"] = self.news_query.text()
            self.config["monitoring"]["max_news_per_source"] = self.max_news.value()
            
            # UI设置
            self.config["ui"]["theme"] = "dark" if self.theme_combo.currentIndex() == 1 else "light"
            self.config["ui"]["enable_sound_alerts"] = self.sound_enabled.isChecked()
            self.config["ui"]["show_desktop_notifications"] = self.desktop_notification.isChecked()
            self.config["ui"]["chart_update_interval_ms"] = self.chart_update.value()
            
            # 保存到文件
            logging.info(f"保存配置到文件: {self.config_file}")
            config_dir = os.path.dirname(self.config_file)
            if config_dir and not os.path.exists(config_dir):
                logging.info(f"配置目录不存在，创建目录: {config_dir}")
                os.makedirs(config_dir)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
                logging.info("配置成功保存到文件")
            
            # 接受对话框
            logging.info("关闭设置对话框")
            super().accept()
        except Exception as e:
            logging.error(f"保存设置失败: {e}", exc_info=True)
            QMessageBox.critical(self, "保存设置失败", f"无法保存设置: {str(e)}") 