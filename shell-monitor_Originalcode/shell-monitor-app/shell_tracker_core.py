#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
from datetime import datetime, timedelta
import pandas as pd
import ta
import requests
import os
import json
import traceback
import re
import threading
import feedparser  # 用于解析RSS源
import html  # 用于处理HTML实体
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from binance.client import Client
from binance.exceptions import BinanceAPIException

class ShellTrackerCore(QObject):
    """
    Shell追踪器核心类，从原始脚本提取核心逻辑，并提供与GUI交互的接口
    """
    # 信号定义
    price_updated = pyqtSignal(float, float)  # 价格, 百分比变化
    trade_signal = pyqtSignal(str, float)  # 信号类型 ('BUY'/'SELL'), 价格
    stop_condition_triggered = pyqtSignal(str, float, float)  # 类型 ('STOP_LOSS'/'TAKE_PROFIT'), 价格, 盈亏百分比
    monitoring_started = pyqtSignal(int, int)  # 持续时间(分钟), 刷新间隔(秒)
    monitoring_stopped = pyqtSignal()
    monitoring_error = pyqtSignal(str)  # 错误信息
    news_processed = pyqtSignal(str, str, float)  # 处理后的新闻, 情感类型, 情感分数
    chart_data_ready = pyqtSignal(object)  # K线数据
    signal_status_updated = pyqtSignal(str, str, int)  # 类型, 推荐操作, 置信度(%)
    alert_triggered = pyqtSignal(str, str, float)  # 类型, 消息, 数值
    account_balance_updated = pyqtSignal(float, float)  # 余额, 估算价值(USDT)
    rss_news_received = pyqtSignal(list)  # RSS新闻列表(包含时间、标题、内容、来源)
    
    def __init__(self, config=None):
        """初始化追踪器"""
        super().__init__()
        
        # 配置信息
        self.config = config or {}
        
        # API客户端
        self.client = None
        
        # 价格和持仓信息
        self.last_price = None
        self.previous_price = None
        self.entry_price = None
        self.position = None
        self.price_log = []
        self.session_high = None
        self.session_low = None
        
        # 账户信息
        self.account_balance = 0.0
        self.account_value = 0.0
        
        # 交易和信号信息
        self.current_signal = None
        self.stop_flag = False
        
        # 新闻和情感分析
        self.current_sentiment = None
        self.sentiment_score = 0.0
        self.last_processed_news = None  # 保存最近处理的新闻
        self.rss_feeds = []
        self.rss_keywords = []
        
        # 监控线程
        self.monitoring_thread = None
        
        # 日志和图表目录
        self.log_dir = "price_logs"
        self.log_filename = None
        self.charts_dir = "charts"  # 默认图表目录
        
        # 缓存相关
        self.news_cache = {}  # 用于缓存新闻查询结果
        self.cache_expiry = 3600  # 缓存有效期（秒）
        
    def initialize(self, config):
        """初始化追踪器，连接API"""
        self.config = config
        
        try:
            # 初始化Binance客户端
            api_key = config['api']['binance'].get('api_key', '')
            api_secret = config['api']['binance'].get('api_secret', '')
            
            # 设置RSS源 - 默认值
            self.rss_feeds = [
                "https://cointelegraph.com/rss",
                "https://www.coindesk.com/arc/outboundfeeds/rss/",
                "https://decrypt.co/feed",
                "https://www.theblock.co/rss.xml",
                "https://www.coingecko.com/en/news/feed.rss",
                "https://www.binance.com/en/feed",
                "https://research.binance.com/en/feed"
            ]
            self.rss_keywords = ['myshell', 'shell coin', ' shell ']
            
            # 如果配置中有RSS源，则使用配置的值
            if 'rss_feeds' in config.get('monitoring', {}):
                self.rss_feeds = config['monitoring']['rss_feeds']
            
            if 'rss_keywords' in config.get('monitoring', {}):
                self.rss_keywords = config['monitoring']['rss_keywords']
            
            # 检查API密钥是否配置
            if not api_key or not api_secret:
                self.monitoring_error.emit("未配置Binance API密钥，请在设置中配置")
                return False
                
            try:
                # 初始化Binance客户端
                self.client = Client(api_key, api_secret)
                
                # 检查连接
                self.client.get_server_time()
                print("Binance API连接成功")
                
                # 连接成功后检查账户余额
                self.check_account_balance()
                
                return True
            except Exception as e:
                self.monitoring_error.emit(f"Binance API初始化失败: {str(e)}")
                self.client = None
                return False
        except Exception as e:
            self.monitoring_error.emit(f"初始化追踪器失败: {str(e)}")
            return False
    
    def get_latest_price(self):
        """从Binance获取最新价格"""
        if not self.client:
            self.monitoring_error.emit("Binance客户端未初始化")
            return self._get_simulated_price()  # 使用模拟价格
            
        try:
            symbol = self.config['trading']['symbol']
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            self.monitoring_error.emit(f"获取最新价格失败，使用模拟数据: {str(e)}")
            return self._get_simulated_price()  # 失败时使用模拟价格
    
    def _get_simulated_price(self):
        """返回模拟价格（当API不可用时使用）"""
        # 如果之前获取过价格，返回略有变化的价格
        if hasattr(self, '_last_simulated_price') and self._last_simulated_price is not None:
            # 添加小幅随机波动(-0.5%到+0.5%)
            import random
            change = random.uniform(-0.005, 0.005)
            new_price = self._last_simulated_price * (1 + change)
            self._last_simulated_price = new_price
            return new_price
        else:
            # 首次调用，使用默认价格
            self._last_simulated_price = 1.2345  # SHELL币的模拟价格
            return self._last_simulated_price
    
    def get_klines(self):
        """获取K线数据并计算技术指标"""
        if not self.client:
            self.monitoring_error.emit("Binance客户端未初始化，尝试使用模拟数据")
            return self._get_simulated_klines()
            
        try:
            symbol = self.config['trading']['symbol']
            interval = self.config['trading']['interval']
            
            # 转换间隔格式为Binance API接受的格式
            interval_map = {
                '1m': Client.KLINE_INTERVAL_1MINUTE,
                '3m': Client.KLINE_INTERVAL_3MINUTE,
                '5m': Client.KLINE_INTERVAL_5MINUTE,
                '15m': Client.KLINE_INTERVAL_15MINUTE,
                '30m': Client.KLINE_INTERVAL_30MINUTE,
                '1h': Client.KLINE_INTERVAL_1HOUR,
                '2h': Client.KLINE_INTERVAL_2HOUR,
                '4h': Client.KLINE_INTERVAL_4HOUR,
                '1d': Client.KLINE_INTERVAL_1DAY
            }
            binance_interval = interval_map.get(interval, Client.KLINE_INTERVAL_15MINUTE)
            
            print(f"正在获取 {symbol} 的 {interval} K线数据...")
            
            # 根据时间间隔调整获取的数据量
            lookback_periods = {
                Client.KLINE_INTERVAL_1MINUTE: "1 day ago UTC",   # 1分钟K线获取1天数据
                Client.KLINE_INTERVAL_3MINUTE: "2 days ago UTC",  # 3分钟K线获取2天数据
                Client.KLINE_INTERVAL_5MINUTE: "3 days ago UTC",  # 5分钟K线获取3天数据
                Client.KLINE_INTERVAL_15MINUTE: "5 days ago UTC", # 15分钟K线获取5天数据
                Client.KLINE_INTERVAL_30MINUTE: "7 days ago UTC", # 30分钟K线获取7天数据
                Client.KLINE_INTERVAL_1HOUR: "14 days ago UTC",   # 1小时K线获取14天数据
                Client.KLINE_INTERVAL_2HOUR: "14 days ago UTC",   # 2小时K线获取14天数据
                Client.KLINE_INTERVAL_4HOUR: "30 days ago UTC",   # 4小时K线获取30天数据
                Client.KLINE_INTERVAL_1DAY: "90 days ago UTC"     # 1天K线获取90天数据
            }
            lookback = lookback_periods.get(binance_interval, "5 days ago UTC")
            
            # 获取K线数据，适应不同的时间间隔需要不同的数据量
            klines = self.client.get_historical_klines(
                symbol, binance_interval, lookback, limit=100
            )
            
            if len(klines) < 2:
                self.monitoring_error.emit(f"获取到的K线数据不足: {len(klines)} 条")
                return self._get_simulated_klines()
                
            # 转换为DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'num_trades',
                'taker_buy_base', 'taker_buy_quote', 'ignore'
            ])
            
            # 数据处理
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            num_cols = ['open', 'high', 'low', 'close', 'volume', 'quote_asset_volume']
            for col in num_cols:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            df.dropna(subset=['close'], inplace=True)
            
            if df.empty or len(df) < 2:
                self.monitoring_error.emit("处理后的K线数据为空")
                return self._get_simulated_klines()
                
            print(f"获取到 {len(df)} 条K线数据，开始计算技术指标...")
            
            # 计算技术指标
            data_len = len(df)
            
            # 移动平均线
            df['ma5'] = ta.trend.sma_indicator(df['close'], window=5) if data_len >= 5 else pd.NA
            df['ma25'] = ta.trend.sma_indicator(df['close'], window=25) if data_len >= 25 else pd.NA
            
            # RSI
            df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi() if data_len >= 14 else pd.NA
            
            # MACD
            if data_len >= 26:
                try:
                    macd = ta.trend.MACD(df['close'], 
                                      window_fast=12, 
                                      window_slow=26, 
                                      window_sign=9)
                    df['macd'] = macd.macd()
                    df['macd_signal'] = macd.macd_signal()
                    df['macd_diff'] = macd.macd_diff()
                    print(f"MACD计算完成: {len(df[df['macd'].notna()])} 行有效数据")
                except Exception as e:
                    self.monitoring_error.emit(f"计算MACD指标时出错: {str(e)}")
                    df['macd'] = pd.NA
                    df['macd_signal'] = pd.NA
                    df['macd_diff'] = pd.NA
            else:
                self.monitoring_error.emit(f"数据不足以计算MACD: 需要至少26条数据，只有{data_len}条")
                df['macd'] = pd.NA
                df['macd_signal'] = pd.NA
                df['macd_diff'] = pd.NA
                
            # 波动率
            if data_len >= 21:
                df['volatility'] = df['close'].pct_change().rolling(window=20).std() * 100
            else:
                df['volatility'] = pd.NA
                
            df.set_index('timestamp', inplace=True)
            
            # 检查并打印指标的完整度
            indicators = ['ma5', 'ma25', 'rsi', 'macd', 'macd_signal', 'macd_diff', 'volatility']
            for ind in indicators:
                valid_count = df[ind].notna().sum()
                print(f"指标 {ind}: {valid_count}/{len(df)} 行有效 ({valid_count/len(df)*100:.1f}%)")
            
            # 发送K线数据信号
            self.chart_data_ready.emit(df)
            
            return df
            
        except Exception as e:
            error_message = f"获取K线或计算指标失败: {str(e)}"
            self.monitoring_error.emit(error_message)
            traceback.print_exc()  # 打印详细错误堆栈
            return self._get_simulated_klines()
            
    def _get_simulated_klines(self):
        """生成模拟K线数据（当API不可用时使用）"""
        print("生成模拟K线数据...")
        
        # 创建时间序列，从昨天到现在，10分钟间隔
        end_time = datetime.now()
        start_time = end_time - timedelta(days=1)
        date_range = pd.date_range(start=start_time, end=end_time, freq='10min')
        
        # 创建基本价格，在1.0-2.0之间
        import random
        import numpy as np
        
        base_price = 1.5
        close_prices = []
        current_price = base_price
        
        # 生成随机走势
        for _ in range(len(date_range)):
            change = random.uniform(-0.02, 0.02)  # -2% 到 +2% 的变化
            current_price = current_price * (1 + change)
            # 确保价格不会太离谱
            current_price = max(0.8, min(3.0, current_price))
            close_prices.append(current_price)
        
        # 创建DataFrame
        df = pd.DataFrame(index=date_range)
        df['close'] = close_prices
        df['open'] = df['close'].shift(1).fillna(df['close'] * 0.99)
        df['high'] = df[['open', 'close']].max(axis=1) * (1 + np.random.uniform(0, 0.01, len(df)))
        df['low'] = df[['open', 'close']].min(axis=1) * (1 - np.random.uniform(0, 0.01, len(df)))
        df['volume'] = np.random.uniform(1000, 10000, len(df))
        
        # 计算技术指标
        df['ma5'] = ta.trend.sma_indicator(df['close'], window=5)
        df['ma25'] = ta.trend.sma_indicator(df['close'], window=25)
        df['rsi'] = ta.momentum.RSIIndicator(df['close'], window=14).rsi()
        
        # MACD
        macd = ta.trend.MACD(df['close'], window_fast=12, window_slow=26, window_sign=9)
        df['macd'] = macd.macd()
        df['macd_signal'] = macd.macd_signal()
        df['macd_diff'] = macd.macd_diff()
        
        # 波动率
        df['volatility'] = df['close'].pct_change().rolling(window=20).std() * 100
        
        # 清理NaN值
        df.fillna(method='bfill', inplace=True)
        
        print(f"已生成 {len(df)} 条模拟K线数据")
        
        # 发送K线数据信号
        self.chart_data_ready.emit(df)
        
        return df
    
    def check_signals(self, df):
        """根据技术指标判断买入/卖出信号"""
        if df.empty or len(df) < 26:
            return None
            
        try:
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            price = latest.get('close')
            ma5 = latest.get('ma5')
            ma25 = latest.get('ma25')
            rsi = latest.get('rsi')
            macd_val = latest.get('macd')
            macd_sig = latest.get('macd_signal')
            
            prev_ma5 = prev.get('ma5')
            prev_ma25 = prev.get('ma25')
            prev_macd_val = prev.get('macd')
            prev_macd_sig = prev.get('macd_signal')
            
            required_indicators = [
                price, ma5, ma25, rsi, macd_val, macd_sig,
                prev_ma5, prev_ma25, prev_macd_val, prev_macd_sig
            ]
            
            if any(i is None or pd.isna(i) for i in required_indicators):
                return None
                
            # 技术信号
            buy_signal_tech = (prev_ma5 <= prev_ma25 and ma5 > ma25) and \
                            rsi < 50 and \
                            (prev_macd_val <= prev_macd_sig and macd_val > macd_sig)
                            
            sell_signal_tech = (prev_ma5 >= prev_ma25 and ma5 < ma25) and \
                            rsi > 50 and \
                            (prev_macd_val >= prev_macd_sig and macd_val < macd_sig)
            
            # 情感因素
            sentiment_factor = 0.0
            sentiment_influence_enabled = self.config['trading'].get('sentiment_influence_enabled', True)
            sentiment_influence_weight = self.config['trading'].get('sentiment_influence_weight', 0.5)
            
            if sentiment_influence_enabled and self.current_sentiment is not None:
                sentiment_factor = self.sentiment_score * sentiment_influence_weight
            
            # 综合得分 - 修正卖出信号的情感因子处理
            buy_score = (1 if buy_signal_tech else 0) + sentiment_factor
            # 注意这里是减去情感因子，因为负面情感应该增强卖出信号
            sell_score = (-1 if sell_signal_tech else 0) - sentiment_factor
            
            # 信号阈值
            final_buy_threshold = 0.6
            final_sell_threshold = -0.6
            
            # 输出调试信息
            if buy_signal_tech or sell_signal_tech:
                print(f"Debug: 交易信号 - MA5={ma5:.4f}, MA25={ma25:.4f}, RSI={rsi:.1f}, MACD={macd_val:.4f}, Signal={macd_sig:.4f}")
                if buy_signal_tech:
                    print(f"Debug: 买入技术信号触发 (Score: {buy_score:.2f})")
                if sell_signal_tech:
                    print(f"Debug: 卖出技术信号触发 (Score: {sell_score:.2f})")
                if sentiment_influence_enabled and self.current_sentiment is not None:
                    sentiment_emoji = "😀" if self.current_sentiment == "positive" else "😐" if self.current_sentiment == "neutral" else "😟"
                    print(f"Debug: 情感因素: {sentiment_emoji} {self.sentiment_score:.1f} -> 影响: {sentiment_factor:.2f}")
            
            # 发送信号状态
            confidence = 0
            if buy_signal_tech or sell_signal_tech:
                total_score = buy_score if buy_score > 0 else sell_score
                total_factors = 1 + (1 if self.current_sentiment else 0)
                confidence = int(min(100, abs(total_score) / (total_factors * 2) * 100))
            
            recommendation = ""
            signal_type = ""
            
            if buy_score >= final_buy_threshold:
                signal_type = "BUY"
                stop_loss_price = price * (1 - self.config['trading']['stop_loss_percent']/100)
                recommendation = f"考虑分批买入，止损参考 {stop_loss_price:.4f}"
                self.signal_status_updated.emit(signal_type, recommendation, confidence)
                # 发送K线数据以更新MACD图表
                self.chart_data_ready.emit(df)
                return 'BUY'
            elif sell_score <= final_sell_threshold:
                signal_type = "SELL"
                take_profit_price = price * (1 + self.config['trading']['take_profit_percent']/100)
                recommendation = f"考虑减仓或观望，止盈参考 {take_profit_price:.4f}"
                self.signal_status_updated.emit(signal_type, recommendation, confidence)
                # 发送K线数据以更新MACD图表
                self.chart_data_ready.emit(df)
                return 'SELL'
            else:
                signal_type = "NEUTRAL"
                recommendation = "信号不明确，建议观望"
                neutrality_score = max(20, 100 - int(abs(buy_score - sell_score)*50))
                self.signal_status_updated.emit(signal_type, recommendation, neutrality_score)
                # 即使是中性信号，也更新MACD图表
                self.chart_data_ready.emit(df)
                return None
                
        except Exception as e:
            self.monitoring_error.emit(f"检查交易信号时出错: {str(e)}")
            traceback.print_exc()  # 打印详细错误堆栈
            return None
    
    def execute_trade(self, signal, price):
        """执行模拟交易"""
        if not price:
            return
            
        # 准备情感分析信息
        sentiment_info = ""
        if self.current_sentiment:
            sentiment_emoji = "😀" if self.current_sentiment == "positive" else "😐" if self.current_sentiment == "neutral" else "😟"
            sentiment_info = f"(情感分数: {sentiment_emoji} {self.sentiment_score:.1f})"
            
        if signal == 'BUY' and self.position is None:
            # 记录入场信息
            self.entry_price = price
            self.position = 'LONG'
            
            # 输出详细日志信息
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] BUY 信号触发 @ {price:.4f} {sentiment_info}")
            
            # 发出交易信号
            self.trade_signal.emit('BUY', price)
            
            # 更新K线数据，确保图表在交易后更新
            df = self.get_klines()
            if df is not None and not df.empty:
                self.chart_data_ready.emit(df)
            
        elif signal == 'SELL' and self.position == 'LONG':
            # 计算盈亏
            profit = ((price - self.entry_price) / self.entry_price) * 100 if self.entry_price else 0
            profit_info = f"(盈利: {profit:.2f}%)" if self.entry_price else "(无法计算盈亏)"
            
            # 输出详细日志信息
            print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] SELL 信号触发 @ {price:.4f} {profit_info} {sentiment_info}")
            
            # 清空持仓状态
            self.position = None
            self.entry_price = None
            
            # 发出交易信号
            self.trade_signal.emit('SELL', price)
            
            # 更新K线数据，确保图表在交易后更新
            df = self.get_klines()
            if df is not None and not df.empty:
                self.chart_data_ready.emit(df)
    
    def check_stop_conditions(self, current_price):
        """检查是否触发止盈或止损"""
        if self.position == 'LONG' and self.entry_price is not None and isinstance(current_price, (int, float)):
            stop_loss_percent = self.config['trading']['stop_loss_percent'] / 100
            take_profit_percent = self.config['trading']['take_profit_percent'] / 100
            
            stop_loss_price = self.entry_price * (1 - stop_loss_percent)
            take_profit_price = self.entry_price * (1 + take_profit_percent)
            
            # 计算当前盈亏百分比
            profit_percent = ((current_price - self.entry_price) / self.entry_price) * 100
            
            if current_price <= stop_loss_price:
                # 输出详细日志信息
                print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 止损触发 @ {current_price:.4f} (亏损: {profit_percent:.2f}%)")
                
                # 清空持仓状态
                self.position = None
                self.entry_price = None
                
                # 发出止损信号
                self.stop_condition_triggered.emit('STOP_LOSS', current_price, profit_percent)
                
                # 更新K线数据，确保图表在止损后更新
                df = self.get_klines()
                if df is not None and not df.empty:
                    self.chart_data_ready.emit(df)
                
                return True
                
            elif current_price >= take_profit_price:
                # 输出详细日志信息
                print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] 止盈触发 @ {current_price:.4f} (盈利: {profit_percent:.2f}%)")
                
                # 清空持仓状态
                self.position = None
                self.entry_price = None
                
                # 发出止盈信号
                self.stop_condition_triggered.emit('TAKE_PROFIT', current_price, profit_percent)
                
                # 更新K线数据，确保图表在止盈后更新
                df = self.get_klines()
                if df is not None and not df.empty:
                    self.chart_data_ready.emit(df)
                
                return True
                
        return False
    
    def fetch_and_process_news(self):
        """获取并处理新闻"""
        if not self.config['api']['news']['enabled']:
            return "新闻获取功能已禁用。", None, 0.0
            
        all_headlines = []
        processed_sources_count = 0
        
        # 获取GNews新闻
        if self.config['api']['news'].get('gnews_api_key'):
            try:
                query = self.config['monitoring']['news_query']
                max_news = self.config['monitoring']['max_news_per_source']
                api_key = self.config['api']['news']['gnews_api_key']
                
                # 使用简化查询（只包含关键词）
                simple_query = "SHELL coin"
                
                url = f"https://gnews.io/api/v4/search?q={requests.utils.quote(simple_query)}&lang=en&max={max_news}&token={api_key}"
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                data = response.json()
                
                gnews_headlines = [f"{a.get('title', '')}. {a.get('description', '')} (GNews)" for a in data.get('articles', []) if a.get('title')]
                all_headlines.extend(gnews_headlines)
                
                if gnews_headlines:
                    processed_sources_count += 1
            except Exception as e:
                self.monitoring_error.emit(f"GNews API错误: {str(e)}")
        
        # 获取NewsAPI新闻
        if self.config['api']['news'].get('newsapi_api_key'):
            try:
                query = self.config['monitoring']['news_query']
                max_news = self.config['monitoring']['max_news_per_source']
                api_key = self.config['api']['news']['newsapi_api_key']
                
                url = f"https://newsapi.org/v2/everything?q={requests.utils.quote(query)}&language=en&pageSize={max_news}&apiKey={api_key}"
                response = requests.get(url, timeout=20)
                response.raise_for_status()
                data = response.json()
                
                newsapi_headlines = [f"{a.get('title', '')}. {a.get('description', '')} (来源: {a.get('source', {}).get('name', 'NewsAPI')})" for a in data.get('articles', []) if a.get('title')]
                all_headlines.extend(newsapi_headlines)
                
                if newsapi_headlines:
                    processed_sources_count += 1
            except Exception as e:
                self.monitoring_error.emit(f"NewsAPI错误: {str(e)}")
        
        # 获取RSS新闻
        max_articles_per_rss = self.config['monitoring'].get('max_articles_per_rss', 2)
        rss_articles = self.fetch_rss_news(max_articles_per_rss)
        
        if rss_articles:
            rss_headlines = [f"{a['title']}. {a['summary']} (来源: {a['source']})" for a in rss_articles]
            all_headlines.extend(rss_headlines)
            processed_sources_count += 1
        
        if not all_headlines:
            self.last_processed_news = "未能获取到相关新闻。"
            return "未能获取到相关新闻。", "neutral", 0.0
            
        # 去重
        unique_headlines = list(dict.fromkeys(all_headlines))
        
        # 调用DeepSeek API进行分析
        processed_news, sentiment, score = self.call_deepseek_for_analysis(unique_headlines)
        
        # 保存新闻和情感结果，以便报告使用
        self.current_sentiment = sentiment
        self.sentiment_score = score
        self.last_processed_news = processed_news
        
        # 发送信号
        self.news_processed.emit(processed_news, sentiment, score)
        
        return processed_news, sentiment, score
    
    def call_deepseek_for_analysis(self, headlines):
        """调用DeepSeek API分析新闻"""
        # 生成缓存键
        cache_key = hash(tuple(sorted(headlines)))
        
        # 检查缓存
        current_time = time.time()
        if cache_key in self.news_cache:
            cache_time, cache_data = self.news_cache[cache_key]
            if current_time - cache_time < self.cache_expiry:
                return cache_data
        
        processed_chinese_news = "未能提取到中文摘要。"
        sentiment = "neutral"
        sentiment_score_value = 0.0
        
        if not self.config['api']['news'].get('deepseek_api_key'):
            return "DeepSeek API未配置。", sentiment, sentiment_score_value
            
        if not headlines:
            return "无新闻内容可供分析。", sentiment, sentiment_score_value
            
        combined_headlines = "\n".join([f"- {h}" for h in headlines])
        
        prompt = f"""请分析以下关于'{self.config['monitoring']['news_query']}'的新闻标题和描述：
{combined_headlines}

请完成以下任务：
1. 将上述新闻内容翻译成简洁流畅的中文。
2. 对翻译后的内容进行总结，提炼出最关键的信息点，生成一段不超过150字的中文摘要。
3. 基于这些新闻，判断市场对'{self.config['monitoring']['news_query']}'的整体情感倾向是积极(positive)、消极(negative)还是中性(neutral)。
4. （可选）如果能明确判断，请给出一个从-1.0 (极度消极) 到 1.0 (极度积极) 的情感分数。

请严格按照以下格式返回结果，确保每个标签都存在，标签和内容之间用冒号分隔：
情感: [positive/negative/neutral]
情感分数: [数值，如果无法判断则为 0.0]
中文摘要:
[这里是总结后的中文新闻内容]
"""
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.config['api']['news']['deepseek_api_key']}"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        try:
            api_url = self.config['api']['news'].get('deepseek_api_url', 'https://api.deepseek.com/v1/chat/completions')
            response = requests.post(api_url, headers=headers, json=payload, timeout=45)
            response.raise_for_status()
            response_data = response.json()
            
            if 'choices' not in response_data or not response_data['choices']:
                raise ValueError("DeepSeek API 返回的响应格式不正确: 'choices' 缺失")
                
            response_text = response_data['choices'][0]['message']['content']
            
            # 解析响应
            parsed_sentiment = None
            parsed_score = 0.0
            summary_content = None
            
            sentiment_match = re.search(r"^\s*情感\s*:\s*(positive|negative|neutral)\s*$", response_text, re.IGNORECASE | re.MULTILINE)
            score_match = re.search(r"^\s*情感分数\s*:\s*(-?\d+(\.\d+)?)\s*$", response_text, re.IGNORECASE | re.MULTILINE)
            summary_match = re.search(r"^\s*中文摘要\s*:(.*)", response_text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            
            if sentiment_match:
                parsed_sentiment = sentiment_match.group(1).lower()
            
            if score_match:
                try:
                    parsed_score = float(score_match.group(1))
                    parsed_score = max(-1.0, min(1.0, parsed_score))
                except ValueError:
                    pass
            
            if summary_match:
                summary_content = summary_match.group(1).strip()
                summary_content = re.sub(r"\n\s*(分析理由|情感|情感分数)\s*:.*", "", summary_content, flags=re.IGNORECASE | re.DOTALL)
                if not summary_content:
                    summary_content = "未能提取到有效的中文摘要内容。"
            else:
                summary_content = "未能找到中文摘要部分。"
            
            sentiment = parsed_sentiment if parsed_sentiment else "neutral"
            sentiment_score_value = parsed_score
            processed_chinese_news = summary_content
            
            if not parsed_sentiment and sentiment_score_value != 0.0:
                if sentiment_score_value >= 0.3:
                    sentiment = "positive"
                elif sentiment_score_value <= -0.3:
                    sentiment = "negative"
            
            # 缓存结果
            result = (processed_chinese_news, sentiment, sentiment_score_value)
            self.news_cache[cache_key] = (current_time, result)
            
            return result
            
        except requests.exceptions.RequestException as e:
            self.monitoring_error.emit(f"调用 DeepSeek API 时发生网络错误: {str(e)}")
            return f"调用 DeepSeek 失败 (网络错误): {str(e)}", sentiment, sentiment_score_value
        except ValueError as e:
            self.monitoring_error.emit(f"解析 DeepSeek 响应时出错: {str(e)}")
            return f"解析 DeepSeek 响应失败: {str(e)}", sentiment, sentiment_score_value
        except Exception as e:
            self.monitoring_error.emit(f"调用 DeepSeek API 或处理响应时发生未知错误: {str(e)}")
            return f"处理 DeepSeek 响应失败: {str(e)}", sentiment, sentiment_score_value
    
    def start_monitoring(self, duration_minutes, refresh_interval_seconds):
        """开始监控"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.stop_monitoring()
            time.sleep(1)  # 等待线程结束
        
        self.stop_flag = False
        self.price_log = []
        self.previous_price = None
        
        # 初始化价格日志文件
        self.initialize_price_log()
        
        # 创建并启动监控线程
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(duration_minutes, refresh_interval_seconds)
        )
        self.monitoring_thread.daemon = True
        self.monitoring_thread.start()
        
        # 获取和处理初始新闻（在单独的线程中进行，避免阻塞UI）
        if self.config['api']['news']['enabled']:
            news_thread = threading.Thread(target=self.fetch_and_process_news)
            news_thread.daemon = True
            news_thread.start()
        
        # 发送监控开始信号
        self.monitoring_started.emit(duration_minutes, refresh_interval_seconds)
    
    def initialize_price_log(self):
        """初始化价格日志文件"""
        # 确保日志目录存在
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
            except OSError as e:
                self.monitoring_error.emit(f"创建日志目录失败: {str(e)}")
                return
        
        # 创建日志文件
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_filename = f"{self.log_dir}/price_log_{timestamp}.csv"
            
            # 写入CSV头部
            with open(self.log_filename, 'w') as f:
                f.write("timestamp,price\n")
        except Exception as e:
            self.monitoring_error.emit(f"创建价格日志文件失败: {str(e)}")
            self.log_filename = None
    
    def log_price(self, timestamp, price):
        """记录价格到日志文件"""
        if not self.log_filename:
            return
            
        try:
            with open(self.log_filename, 'a') as f:
                f.write(f"{timestamp.isoformat()},{price}\n")
        except Exception as e:
            self.monitoring_error.emit(f"写入价格日志失败: {str(e)}")
            self.log_filename = None  # 停止后续写入尝试
    
    def stop_monitoring(self):
        """停止监控"""
        self.stop_flag = True
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_thread.join(2)  # 等待最多2秒
        
        # 发送监控停止信号
        self.monitoring_stopped.emit()
    
    def _monitoring_loop(self, duration_minutes, refresh_interval_seconds):
        """监控循环"""
        try:
            end_time = datetime.now() + timedelta(minutes=duration_minutes)
            iteration = 0
            last_news_time = datetime.now()
            last_kline_time = datetime.now() - timedelta(minutes=1)  # 首次进入立即获取K线
            
            # 跟踪会话中的高低价格
            session_high = None
            session_low = None
            
            while datetime.now() < end_time and not self.stop_flag:
                current_time = datetime.now()
                iteration += 1
                
                # 获取最新价格
                current_price = self.get_latest_price()
                
                if current_price is not None:
                    # 更新高低价格
                    if session_high is None or current_price > session_high:
                        session_high = current_price
                    if session_low is None or current_price < session_low:
                        session_low = current_price
                    
                    # 记录价格
                    self.price_log.append((current_time, current_price))
                    
                    # 写入价格日志
                    self.log_price(current_time, current_price)
                    
                    # 计算价格变化
                    pct_change = 0.0
                    if self.previous_price is not None and self.previous_price > 0:
                        pct_change = ((current_price - self.previous_price) / self.previous_price) * 100
                    
                    # 发送价格更新信号
                    self.price_updated.emit(current_price, pct_change)
                    
                    # 检查价格波动提醒
                    price_alert_threshold = self.config['monitoring'].get('price_alert_threshold', 1.0)
                    if self.previous_price is not None and abs(pct_change) >= price_alert_threshold:
                        direction = "上涨" if pct_change > 0 else "下跌"
                        self.alert_triggered.emit(
                            'PRICE_CHANGE',
                            f"{self.config['trading']['symbol']} 价格在过去 {refresh_interval_seconds}秒 内{direction} {abs(pct_change):.2f}%",
                            pct_change
                        )
                    
                    # 检查止盈止损
                    if self.position == 'LONG':
                        position_closed = self.check_stop_conditions(current_price)
                        if position_closed:
                            self.previous_price = current_price
                            
                            # 位置关闭时更新K线图
                            df = self.get_klines()
                            if df is not None and not df.empty:
                                self.chart_data_ready.emit(df)
                                
                            continue  # 更新价格并跳过信号检查
                    
                    # 检查交易信号 - 减少频率，每分钟一次或价格变化大时
                    kline_check_interval = max(1, int(60 / refresh_interval_seconds))
                    kline_elapsed = (current_time - last_kline_time).total_seconds()
                    should_check_klines = iteration % kline_check_interval == 0 or \
                                         (self.previous_price is not None and abs(pct_change) >= price_alert_threshold) or \
                                         kline_elapsed >= 60  # 至少每分钟更新一次
                    
                    if should_check_klines:
                        df = self.get_klines()
                        if df is not None and not df.empty:
                            # 更新图表数据
                            self.chart_data_ready.emit(df)
                            last_kline_time = current_time
                            
                            # 如果没有持仓，检查是否有买入信号
                            if self.position is None:
                                signal = self.check_signals(df)
                                if signal == 'BUY':
                                    self.execute_trade(signal, current_price)
                                    self.previous_price = current_price
                                    continue  # 买入后跳过本轮后续
                    
                    # 更新上一次价格
                    self.previous_price = current_price
                    
                    # 定期更新账户余额(每次迭代都更新)
                    if iteration % 1 == 0:  # 每次循环都检查
                        # 在单独的线程中检查账户余额，避免阻塞主循环
                        balance_thread = threading.Thread(target=self.check_account_balance)
                        balance_thread.daemon = True
                        balance_thread.start()
                
                # 定期更新新闻(每小时)
                news_update_interval = 3600  # 1小时
                if self.config['api']['news']['enabled'] and (current_time - last_news_time).total_seconds() >= news_update_interval:
                    # 在单独的线程中获取新闻，避免阻塞监控循环
                    news_thread = threading.Thread(target=self.fetch_and_process_news)
                    news_thread.daemon = True
                    news_thread.start()
                    last_news_time = current_time
                
                # 睡眠
                if not self.stop_flag:
                    time.sleep(refresh_interval_seconds)
            
            # 监控结束时生成最终报告
            if not self.stop_flag:  # 只有正常结束时才发出信号
                # 再次获取并发送最新的K线数据，确保最终视图是最新的
                final_df = self.get_klines()
                if final_df is not None and not final_df.empty:
                    self.chart_data_ready.emit(final_df)
                    
                self.monitoring_stopped.emit()
                
        except Exception as e:
            error_message = f"监控过程中发生错误: {str(e)}"
            self.monitoring_error.emit(error_message)
            traceback.print_exc()
    
    def check_account_balance(self):
        """检查当前账户余额"""
        if not self.client:
            self.monitoring_error.emit("Binance客户端未初始化，无法检查余额")
            return 0.0, 0.0
            
        try:
            # 获取交易对信息
            symbol = self.config['trading']['symbol']
            coin = symbol.replace('USDT', '')  # 假设所有交易对都是与USDT的交易
            
            # 获取账户余额
            balance_info = self.client.get_asset_balance(asset=coin)
            if balance_info and 'free' in balance_info:
                self.account_balance = float(balance_info['free'])
                
                # 获取当前价格计算价值
                price = self.get_latest_price()
                if price:
                    self.account_value = self.account_balance * price
                
                # 发送账户余额更新信号
                self.account_balance_updated.emit(self.account_balance, self.account_value)
                
                # 调试信息，帮助排查问题
                print(f"余额更新: {self.account_balance} SHELL, 价值: {self.account_value} USDT")
                
                # 如果余额大于阈值，认为有持仓
                if self.account_balance > 0.1:
                    self.position = 'LONG'
                    # entry_price保持None，因为无法知道初始持仓成本
                    
            return self.account_balance, self.account_value
        except BinanceAPIException as e:
            error_message = f"Binance API错误: {str(e)}"
            self.monitoring_error.emit(error_message)
            return 0.0, 0.0
        except Exception as e:
            self.monitoring_error.emit(f"检查账户余额失败: {str(e)}")
            traceback.print_exc()  # 打印详细的错误堆栈
            return 0.0, 0.0

    def fetch_rss_news(self, max_articles_per_rss=2):
        """获取RSS源新闻（并行处理）"""
        if not self.config['api']['news']['enabled']:
            return []
        
        all_articles = []
        rss_headers = {'User-Agent': 'Mozilla/5.0'}
        
        def fetch_single_rss(feed_url):
            """获取单个RSS源的新闻（线程函数）"""
            articles = []
            try:
                response = requests.get(feed_url, headers=rss_headers, timeout=25)
                response.raise_for_status()
                feed = feedparser.parse(response.content)
                
                # 获取源名称
                source_name = feed.feed.get('title', feed_url)
                
                # 检查解析错误
                if feed.bozo:
                    self.monitoring_error.emit(f"RSS解析警告 ({source_name}): {feed.bozo_exception}")
                
                # 获取相关文章
                relevant_count = 0
                for entry in feed.entries:
                    if relevant_count >= max_articles_per_rss:
                        break
                        
                    # 获取标题和摘要
                    title = entry.get('title', '')
                    summary = entry.get('summary', entry.get('description', ''))
                    
                    # 处理HTML格式
                    if isinstance(summary, str):
                        summary = html.unescape(re.sub('<[^<]+?>', '', summary))
                    else:
                        summary = ''
                    
                    # 获取发布时间
                    pub_time = None
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_time = datetime(*entry.published_parsed[:6])
                    else:
                        pub_time = datetime.now()
                    
                    # 检查关键词
                    content_lower = (title + ' ' + summary).lower()
                    if any(keyword in content_lower for keyword in self.rss_keywords):
                        article = {
                            'title': title,
                            'summary': summary[:200] + ('...' if len(summary) > 200 else ''),
                            'source': source_name,
                            'time': pub_time,
                            'url': entry.get('link', '')
                        }
                        articles.append(article)
                        relevant_count += 1
                
            except requests.exceptions.RequestException as e:
                self.monitoring_error.emit(f"RSS获取错误 ({feed_url}): {str(e)}")
            except Exception as e:
                self.monitoring_error.emit(f"RSS处理错误 ({feed_url}): {str(e)}")
            
            return articles
        
        # 创建线程池处理多个RSS源
        threads = []
        results = [[] for _ in range(len(self.rss_feeds))]
        
        for i, feed_url in enumerate(self.rss_feeds):
            thread = threading.Thread(
                target=lambda idx=i, url=feed_url: results[idx].extend(fetch_single_rss(url))
            )
            thread.daemon = True
            threads.append(thread)
            thread.start()
        
        # 等待所有线程完成
        for thread in threads:
            thread.join(timeout=30)  # 设置超时，避免永久等待
        
        # 合并结果
        for result in results:
            all_articles.extend(result)
        
        # 按时间排序
        all_articles.sort(key=lambda x: x['time'], reverse=True)
        
        # 发送新闻信号
        if all_articles:
            self.rss_news_received.emit(all_articles)
        
        return all_articles 

    def generate_status_report(self):
        """生成当前状态的完整报告，包括价格、技术指标、新闻和图表
        
        Returns:
            dict: 包含报告所有内容的字典，包括文本信息和图表路径
        """
        # 准备报告数据
        report_data = {
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': "监控中" if hasattr(self, 'monitoring_thread') and self.monitoring_thread and self.monitoring_thread.is_alive() else "未监控",
            'charts': {},
            'text_report': "",
            'position': self.position,
            'entry_price': self.entry_price,
            'telegram_config': {
                'token': self.config.get('api', {}).get('telegram', {}).get('token', ''),
                'chat_id': self.config.get('api', {}).get('telegram', {}).get('chat_id', ''),
                'enabled': self.config.get('api', {}).get('telegram', {}).get('enabled', True)
            }
        }
        
        try:
            # 获取最新价格和K线数据
            current_price = self.get_latest_price()
            df = self.get_klines()
            
            if not current_price:
                return {'error': "无法获取当前价格数据"}
                
            # 添加价格信息
            report_data['current_price'] = current_price
            
            # 如果有价格日志，计算价格统计信息
            session_stats = {}
            if hasattr(self, 'price_log') and self.price_log:
                times, prices = zip(*self.price_log)
                session_stats['min_price'] = min(prices)
                session_stats['max_price'] = max(prices)
                session_stats['price_change'] = ((prices[-1] - prices[0]) / prices[0]) * 100 if prices[0] != 0 else 0
                session_stats['price_volatility'] = max(prices) - min(prices)
                session_stats['volatility_percent'] = ((max(prices) - min(prices)) / min(prices)) * 100 if min(prices) > 0 else 0
                session_stats['duration'] = (datetime.now() - times[0]).total_seconds() / 60
                
                # 生成价格走势图
                try:
                    import matplotlib.pyplot as plt
                    # 设置中文字体
                    plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'SimHei', 'Microsoft YaHei']
                    plt.rcParams['axes.unicode_minus'] = False
                    
                    plt.style.use('ggplot')
                    fig, ax = plt.subplots(figsize=(10, 6))
                    ax.plot(times, prices, color='#1f77b4', linewidth=1.5, label='价格')
                    ax.grid(True, linestyle='--', alpha=0.7)
                    
                    # 计算实际的时间间隔并格式化标题
                    interval_seconds = (times[-1] - times[0]).total_seconds()
                    if interval_seconds < 60:
                        title_interval = f"{interval_seconds:.1f}秒"
                    elif interval_seconds < 3600:
                        title_interval = f"{interval_seconds/60:.1f}分钟"
                    elif interval_seconds < 86400:
                        title_interval = f"{interval_seconds/3600:.1f}小时"
                    else:
                        title_interval = f"{interval_seconds/86400:.1f}天"
                    
                    ax.set_title(f'{self.config["trading"]["symbol"]} {title_interval} 价格走势', fontsize=14, pad=10)
                    ax.set_xlabel('时间', fontsize=10)
                    ax.set_ylabel('价格 (USDT)', fontsize=10)
                    
                    ax.yaxis.set_major_formatter(plt.FormatStrFormatter('%.4f'))
                    plt.xticks(rotation=30, fontsize=8)
                    plt.yticks(fontsize=8)
                    ax.legend(loc='upper right', fontsize=10)
                    
                    for spine in ax.spines.values():
                        spine.set_visible(True)
                        spine.set_color('#cccccc')
                        
                    plt.tight_layout()
                    
                    # 保存图表
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    price_chart_filename = f'price_chart_{timestamp_str}.png'
                    
                    # 使用指定的图表目录
                    if hasattr(self, 'charts_dir') and self.charts_dir:
                        # 确保图表目录存在
                        if not os.path.exists(self.charts_dir):
                            try:
                                os.makedirs(self.charts_dir)
                            except OSError as e:
                                print(f"创建图表目录失败: {str(e)}")
                        
                        price_chart_path = os.path.join(self.charts_dir, price_chart_filename)
                    else:
                        price_chart_path = price_chart_filename
                        
                    plt.savefig(price_chart_path, dpi=100, bbox_inches='tight')
                    plt.close()
                    report_data['charts']['price'] = price_chart_path
                except Exception as e:
                    print(f"生成价格图表时出错: {str(e)}")
                
            report_data['session_stats'] = session_stats
            
            # 添加技术指标分析
            tech_analysis = {}
            if df is not None and not df.empty and len(df) >= 26:
                latest = df.iloc[-1]
                
                tech_analysis['rsi'] = latest.get('rsi', None)
                tech_analysis['macd'] = latest.get('macd', None)
                tech_analysis['macd_signal'] = latest.get('macd_signal', None)
                tech_analysis['macd_diff'] = latest.get('macd_diff', None)
                tech_analysis['ma5'] = latest.get('ma5', None)
                tech_analysis['ma25'] = latest.get('ma25', None)
                tech_analysis['volatility'] = latest.get('volatility', None)
                
                # MACD趋势
                tech_analysis['macd_trend'] = "看涨" if tech_analysis['macd_diff'] is not None and tech_analysis['macd_diff'] > 0 else "看跌" if tech_analysis['macd_diff'] is not None else "N/A"
                
                # 均线排列
                if tech_analysis['ma5'] is not None and tech_analysis['ma25'] is not None:
                    if tech_analysis['ma5'] > tech_analysis['ma25']:
                        tech_analysis['ma_trend'] = "多头排列"
                    elif tech_analysis['ma5'] < tech_analysis['ma25']:
                        tech_analysis['ma_trend'] = "空头排列"
                    else:
                        tech_analysis['ma_trend'] = "均线交叉"
                else:
                    tech_analysis['ma_trend'] = "N/A"
                
                # 交易建议
                if tech_analysis['rsi'] is not None:
                    if tech_analysis['rsi'] > 70:
                        tech_analysis['advice'] = "RSI超买，可能回调，建议谨慎。"
                    elif tech_analysis['rsi'] < 30:
                        tech_analysis['advice'] = "RSI超卖，可能反弹，可考虑买入。"
                    elif tech_analysis['macd_diff'] is not None and tech_analysis['ma5'] is not None and tech_analysis['ma25'] is not None:
                        if tech_analysis['macd_diff'] > 0 and tech_analysis['ma5'] > tech_analysis['ma25']:
                            tech_analysis['advice'] = "技术指标看涨，可考虑买入。"
                        elif tech_analysis['macd_diff'] < 0 and tech_analysis['ma5'] < tech_analysis['ma25']:
                            tech_analysis['advice'] = "技术指标看跌，可考虑卖出。"
                        else:
                            tech_analysis['advice'] = "信号不明确，建议观望。"
                else:
                    tech_analysis['advice'] = "无法提供建议"
                
                # 生成MACD图表
                try:
                    import matplotlib.pyplot as plt
                    plt.style.use('ggplot')
                    fig, ax = plt.subplots(figsize=(10, 6))
                    
                    # 绘制MACD指标
                    macd_line = ax.plot(df.index[-30:], df['macd'][-30:], color='#1f77b4', linewidth=1.5, label='MACD')
                    signal_line = ax.plot(df.index[-30:], df['macd_signal'][-30:], color='#ff7f0e', linewidth=1.5, label='Signal')
                    
                    # 绘制柱状图
                    colors = ['green' if val >= 0 else 'red' for val in df['macd_diff'][-30:]]
                    ax.bar(df.index[-30:], df['macd_diff'][-30:], color=colors, label='Histogram', alpha=0.7, width=0.01)
                    
                    ax.grid(True, linestyle='--', alpha=0.7)
                    ax.set_title('MACD 指标图', fontsize=14, pad=10)
                    ax.set_xlabel('时间', fontsize=10)
                    ax.set_ylabel('值', fontsize=10)
                    
                    plt.xticks(rotation=30, fontsize=8)
                    plt.yticks(fontsize=8)
                    
                    # 创建图例
                    handles = [
                        macd_line[0],
                        signal_line[0],
                        plt.Rectangle((0,0),1,1,color='green', alpha=0.7)
                    ]
                    labels = ['MACD', 'Signal', 'Histogram']
                    ax.legend(handles, labels, loc='upper left', fontsize=10)
                    
                    for spine in ax.spines.values():
                        spine.set_visible(True)
                        spine.set_color('#cccccc')
                        
                    plt.tight_layout()
                    
                    # 保存图表
                    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                    macd_chart_filename = f'macd_chart_{timestamp_str}.png'
                    
                    # 使用指定的图表目录
                    if hasattr(self, 'charts_dir') and self.charts_dir:
                        # 确保图表目录存在
                        if not os.path.exists(self.charts_dir):
                            try:
                                os.makedirs(self.charts_dir)
                            except OSError as e:
                                print(f"创建图表目录失败: {str(e)}")
                        
                        macd_chart_path = os.path.join(self.charts_dir, macd_chart_filename)
                    else:
                        macd_chart_path = macd_chart_filename
                        
                    plt.savefig(macd_chart_path, dpi=100, bbox_inches='tight')
                    plt.close()
                    report_data['charts']['macd'] = macd_chart_path
                except Exception as e:
                    print(f"生成MACD图表时出错: {str(e)}")
            
            report_data['tech_analysis'] = tech_analysis
            
            # 添加情感分析信息
            sentiment_info = {}
            if hasattr(self, 'current_sentiment') and self.current_sentiment:
                sentiment_info['sentiment'] = self.current_sentiment
                sentiment_info['score'] = self.sentiment_score
                
                if self.current_sentiment == "positive":
                    sentiment_info['emoji'] = "📈"
                    sentiment_info['text'] = "市场看涨"
                    sentiment_info['confidence'] = int((self.sentiment_score + 1) * 50)
                elif self.current_sentiment == "negative":
                    sentiment_info['emoji'] = "📉"
                    sentiment_info['text'] = "市场看跌"
                    sentiment_info['confidence'] = int((abs(self.sentiment_score)) * 100)
                else:
                    sentiment_info['emoji'] = "📊"
                    sentiment_info['text'] = "市场中性"
                    sentiment_info['confidence'] = int((1 - abs(self.sentiment_score)) * 100)
            else:
                sentiment_info = {
                    'sentiment': "neutral",
                    'score': 0.0,
                    'emoji': "📊",
                    'text': "市场中性",
                    'confidence': 50
                }
                
            report_data['sentiment'] = sentiment_info
            
            # 生成文本报告
            position_status_text = "当前无持仓"
            if self.position == 'LONG':
                if self.entry_price is not None:
                    position_status_text = f"当前持仓 @ {self.entry_price:.4f} USDT"
                else:
                    position_status_text = "当前持仓 (初始持仓，成本未知)"
            
            report_text = f"""🚀 {self.config['trading']['symbol']} 监控状态报告
时间: {report_data['timestamp']}
状态: {report_data['status']}

*持仓状态: {position_status_text}*

当前价格: {current_price:.4f} USDT"""

            # 添加价格统计信息
            if session_stats:
                report_text += f"""
监控时长: {session_stats['duration']:.1f} 分钟
最高价: {session_stats['max_price']:.4f} USDT
最低价: {session_stats['min_price']:.4f} USDT
价格变化: {session_stats['price_change']:+.2f}%
波动幅度: {session_stats['price_volatility']:.4f} USDT ({session_stats['volatility_percent']:.2f}% in range)
"""
            
            # 添加技术分析
            if tech_analysis:
                rsi_display = f"{tech_analysis['rsi']:.2f}" if tech_analysis.get('rsi') is not None else "N/A"
                volatility_display = f"{tech_analysis['volatility']:.2f}%" if tech_analysis.get('volatility') is not None else "N/A"
                
                report_text += f"""
---------------
{sentiment_info['emoji']} {sentiment_info['text']} (置信度: {sentiment_info['confidence']}%)
技术分析:
- RSI: {rsi_display}
- MACD: {tech_analysis.get('macd_trend', 'N/A')}
- 均线: {tech_analysis.get('ma_trend', 'N/A')}
- 波动率: {volatility_display}
建议操作: {tech_analysis.get('advice', '无法提供建议')}
"""
            
            # 如果有新闻分析，添加到报告中
            if hasattr(self, 'last_processed_news') and self.last_processed_news:
                report_text += f"""
新闻解读:
{self.last_processed_news}
"""
            
            report_data['text_report'] = report_text
            
            return report_data
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {'error': f"生成状态报告时出错: {str(e)}"} 