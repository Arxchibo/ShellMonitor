#!/usr/bin/env python
# -*- coding: utf-8 -*-

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSizePolicy
from PyQt5.QtCore import Qt, QDateTime, QRectF, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QPainter, QPen, QColor, QLinearGradient, QBrush, QFont
from PyQt5.QtChart import (QChart, QChartView, QLineSeries, QCandlestickSeries, 
                          QBarSeries, QBarSet, QDateTimeAxis, QValueAxis,
                          QBarCategoryAxis, QCandlestickSet)
import pandas as pd
from datetime import datetime, timedelta
import numpy as np
import logging

class BaseChartWidget(QWidget):
    """基础图表组件，其他图表组件的父类"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 创建布局
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # 创建图表和视图
        self.chart = QChart()
        self.chart.setAnimationOptions(QChart.SeriesAnimations)
        self.chart.legend().setVisible(True)
        self.chart.legend().setAlignment(Qt.AlignBottom)
        
        self.chartview = QChartView(self.chart)
        self.chartview.setRenderHint(QPainter.Antialiasing)
        
        # 添加到布局
        self.layout.addWidget(self.chartview)
        
    def clear_chart(self):
        """清除图表上的所有系列"""
        self.chart.removeAllSeries()
        
        # 删除所有轴
        axes = self.chart.axes()
        for axis in axes:
            self.chart.removeAxis(axis)


class PriceChartWidget(BaseChartWidget):
    """价格图表组件"""
    
    # 添加自定义信号，用于通知周期变化
    timeframe_changed = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置图表标题
        self.chart.setTitle("价格走势图")
        
        # 创建顶部控制栏
        self.control_bar = QWidget()
        control_layout = QHBoxLayout(self.control_bar)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        # 移除图表类型选择器，只保留周期选择器
        timeframe_label = QLabel("周期:")
        self.timeframe_combo = QComboBox()
        self.timeframe_combo.addItems(["1分钟", "5分钟", "15分钟", "1小时", "1天"])
        # 添加信号连接
        self.timeframe_combo.currentTextChanged.connect(self.on_timeframe_changed)
        
        # 添加到控制栏布局
        control_layout.addWidget(timeframe_label)
        control_layout.addWidget(self.timeframe_combo)
        control_layout.addStretch()
        
        # 将控制栏添加到主布局
        self.layout.insertWidget(0, self.control_bar)
        
        # 初始化价格系列
        self.price_series = QLineSeries()
        self.price_series.setName("价格")
        
        # 设置价格系列样式
        pen = QPen(QColor("#1E88E5"))
        pen.setWidth(2)
        self.price_series.setPen(pen)
        
        # 添加系列到图表
        self.chart.addSeries(self.price_series)
        
        # 创建轴
        self.setup_axes()
        
        # 设置当前图表类型为线图
        self.current_chart_type = "line"
        
    def on_timeframe_changed(self, timeframe):
        """处理周期变化事件"""
        # 映射UI选项到实际时间间隔格式
        timeframe_map = {
            "1分钟": "1m",
            "5分钟": "5m",
            "15分钟": "15m",
            "1小时": "1h",
            "1天": "1d"
        }
        
        # 获取映射后的时间间隔
        interval = timeframe_map.get(timeframe, "15m")
        
        # 发送信号通知周期变化
        self.timeframe_changed.emit(interval)
        logging.info(f"图表周期已变更为: {timeframe} ({interval})")
        
    def setup_axes(self):
        """设置图表轴"""
        # 日期时间轴 (X轴)
        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("HH:mm:ss")
        self.axis_x.setTitleText("时间")
        self.axis_x.setLabelsAngle(-45)
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        
        # 价格轴 (Y轴)
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("价格 (USDT)")
        self.axis_y.setLabelFormat("%.4f")
        self.chart.addAxis(self.axis_y, Qt.AlignRight)
        
        # 将系列附加到轴
        self.price_series.attachAxis(self.axis_x)
        self.price_series.attachAxis(self.axis_y)
    
    def update_line_chart(self, price_data):
        """使用价格数据更新线图
        
        Args:
            price_data: 包含(时间, 价格)元组的列表
        """
        # 清除当前数据点
        self.price_series.clear()
        
        if not price_data:
            return
            
        # 查找最小和最大价格，用于设置Y轴范围
        prices = [p[1] for p in price_data]
        min_price = min(prices) * 0.999  # 留出一点边距
        max_price = max(prices) * 1.001
        
        # 将价格数据转换为图表数据点
        for timestamp, price in price_data:
            # 将时间转换为毫秒时间戳
            if isinstance(timestamp, datetime):
                msecs = int(timestamp.timestamp() * 1000)
            else:
                msecs = int(timestamp * 1000)
                
            self.price_series.append(msecs, price)
        
        # 更新X轴范围
        if price_data:
            first_time = price_data[0][0]
            last_time = price_data[-1][0]
            
            if isinstance(first_time, datetime) and isinstance(last_time, datetime):
                self.axis_x.setRange(first_time, last_time)
            
            # 更新Y轴范围，增加一点边距
            self.axis_y.setRange(min_price, max_price)


class MacdChartWidget(BaseChartWidget):
    """MACD图表组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 设置图表标题
        self.chart.setTitle("MACD指标")
        
        # 创建MACD系列
        self.macd_series = QLineSeries()
        self.macd_series.setName("MACD")
        
        self.signal_series = QLineSeries()
        self.signal_series.setName("Signal")
        
        # 设置样式
        macd_pen = QPen(QColor("#2196F3"))
        macd_pen.setWidth(2)
        self.macd_series.setPen(macd_pen)
        
        signal_pen = QPen(QColor("#FF9800"))
        signal_pen.setWidth(2)
        self.signal_series.setPen(signal_pen)
        
        # 添加系列到图表
        self.chart.addSeries(self.macd_series)
        self.chart.addSeries(self.signal_series)
        
        # 创建柱状图系列（用于表示MACD Histogram）
        self.histogram_pos = QBarSet("Histogram+")
        self.histogram_pos.setColor(QColor("#4CAF50"))
        
        self.histogram_neg = QBarSet("Histogram-")
        self.histogram_neg.setColor(QColor("#F44336"))
        
        # 创建轴
        self.setup_axes()
        
    def setup_axes(self):
        """设置图表轴"""
        # 日期时间轴 (X轴)
        self.axis_x = QDateTimeAxis()
        self.axis_x.setFormat("HH:mm:ss")
        self.axis_x.setTitleText("时间")
        self.axis_x.setLabelsAngle(-45)
        self.chart.addAxis(self.axis_x, Qt.AlignBottom)
        
        # MACD值轴 (Y轴)
        self.axis_y = QValueAxis()
        self.axis_y.setTitleText("值")
        self.chart.addAxis(self.axis_y, Qt.AlignRight)
        
        # 将系列附加到轴
        self.macd_series.attachAxis(self.axis_x)
        self.macd_series.attachAxis(self.axis_y)
        
        self.signal_series.attachAxis(self.axis_x)
        self.signal_series.attachAxis(self.axis_y)
    
    def update_macd_chart(self, macd_data):
        """使用MACD数据更新图表
        
        Args:
            macd_data: pandas DataFrame，包含 timestamp, macd, signal, histogram 列
        """
        # 清除当前数据点
        self.macd_series.clear()
        self.signal_series.clear()
        
        # 柱状图需要移除旧的系列
        chart_series = self.chart.series()
        for series in chart_series:
            if isinstance(series, QBarSeries):
                self.chart.removeSeries(series)
        
        if macd_data.empty:
            logging.warning("MacdChartWidget 收到空数据")
            return
            
        # 检查关键列是否存在
        required_cols = ['macd', 'macd_signal', 'macd_diff']
        if not all(col in macd_data.columns for col in required_cols):
            missing = [col for col in required_cols if col not in macd_data.columns]
            logging.warning(f"MacdChartWidget 数据缺少必要的列: {missing}")
            return
            
        # 去除NaN值以避免图表问题
        valid_data = macd_data.dropna(subset=required_cols)
        
        if valid_data.empty:
            logging.warning("MacdChartWidget 所有MACD数据都是NaN")
            return
            
        logging.info(f"MacdChartWidget 更新图表，有效数据: {len(valid_data)}/{len(macd_data)} 行")
        
        try:
            # 查找最小和最大值，用于设置Y轴范围
            all_values = []
            all_values.extend(valid_data['macd'].tolist())
            all_values.extend(valid_data['macd_signal'].tolist())
            all_values.extend(valid_data['macd_diff'].tolist())
            
            min_value = min(all_values) * 1.1 if all_values else -0.1  # 留出一点边距
            max_value = max(all_values) * 1.1 if all_values else 0.1
            
            # 添加MACD和Signal线数据
            for timestamp, row in valid_data.iterrows():
                if isinstance(timestamp, datetime):
                    msecs = int(timestamp.timestamp() * 1000)
                else:
                    try:
                        dt = pd.to_datetime(timestamp)
                        msecs = int(dt.timestamp() * 1000)
                    except:
                        logging.warning(f"无法转换时间戳: {timestamp}")
                        continue
                    
                self.macd_series.append(msecs, float(row['macd']))
                self.signal_series.append(msecs, float(row['macd_signal']))
            
            # 创建柱状图系列
            pos_bars = QBarSet("上升")
            pos_bars.setColor(QColor("#4CAF50"))
            
            neg_bars = QBarSet("下降")
            neg_bars.setColor(QColor("#F44336"))
            
            # 添加柱状图数据
            categories = []
            has_histogram_data = False
            
            for timestamp, row in valid_data.iterrows():
                # 将时间格式化为字符串用作类别
                if isinstance(timestamp, datetime):
                    time_str = timestamp.strftime("%H:%M")
                else:
                    try:
                        time_str = pd.to_datetime(timestamp).strftime("%H:%M")
                    except:
                        time_str = str(timestamp)[:5]
                        
                categories.append(time_str)
                
                # 根据值是正数还是负数，添加到不同的柱状图集合中
                macd_diff = float(row['macd_diff'])
                if macd_diff >= 0:
                    pos_bars.append(macd_diff)
                    neg_bars.append(0)
                    has_histogram_data = True
                else:
                    pos_bars.append(0)
                    neg_bars.append(abs(macd_diff))
                    has_histogram_data = True
            
            if has_histogram_data:
                # 创建柱状图系列
                bar_series = QBarSeries()
                bar_series.append(pos_bars)
                bar_series.append(neg_bars)
                
                # 添加柱状图系列到图表
                self.chart.addSeries(bar_series)
                
                # 创建类别轴
                category_axis = QBarCategoryAxis()
                category_axis.append(categories)
                
                # 将柱状图系列附加到Y轴
                bar_series.attachAxis(self.axis_y)
            
            # 更新X轴范围 - 只使用有效数据的首尾时间戳
            if not valid_data.empty:
                first_time = valid_data.index[0]
                last_time = valid_data.index[-1]
                
                if isinstance(first_time, datetime):
                    first_msecs = int(first_time.timestamp() * 1000)
                    last_msecs = int(last_time.timestamp() * 1000)
                else:
                    try:
                        first_msecs = int(pd.to_datetime(first_time).timestamp() * 1000)
                        last_msecs = int(pd.to_datetime(last_time).timestamp() * 1000)
                    except:
                        logging.warning("无法设置X轴范围，时间戳转换失败")
                        return
                        
                self.axis_x.setRange(QDateTime.fromMSecsSinceEpoch(first_msecs), 
                                    QDateTime.fromMSecsSinceEpoch(last_msecs))
            
            # 更新Y轴范围
            self.axis_y.setRange(min_value, max_value)
            
            logging.info("MACD图表更新成功")
            
        except Exception as e:
            logging.error(f"更新MACD图表时出错: {str(e)}")
            import traceback
            traceback.print_exc() 