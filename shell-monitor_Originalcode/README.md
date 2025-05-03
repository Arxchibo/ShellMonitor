# SHELL币监控器 (SHELL Coin Monitor)

一款基于PyQt5的加密货币监控应用程序，专注于SHELL币的交易信号分析和价格监控。

## 功能特点

- **实时价格监控**: 追踪SHELL/USDT价格变动
- **技术分析**: 自动计算并显示MA, RSI, MACD等技术指标
- **交易信号**: 自动生成买入/卖出信号
- **止盈止损**: 配置自动止盈止损点位
- **图表分析**: 价格走势图和MACD指标图表
- **新闻情感分析**: 通过DeepSeek API分析新闻情感，辅助交易决策
- **多平台通知**: 可选择桌面通知和Telegram通知
- **自定义配置**: 灵活的配置选项，满足不同交易策略需求

## 系统要求

- Windows系统
- Python 3.7或更高版本
- 网络连接

## 安装步骤

1. 克隆或下载此仓库
   ```
   git clone https://your-repository-url/shell-monitor-app.git
   cd shell-monitor-app
   ```

2. 安装依赖项
   ```
   pip install -r requirements.txt
   ```

3. 运行应用程序
   ```
   python main.py
   ```

## 配置说明

首次启动程序后，需要进行配置：

1. 点击"设置"按钮
2. 在"API设置"选项卡中填入以下信息:
   - Binance API密钥和密钥
   - Telegram机器人Token和Chat ID (可选)
   - 新闻API密钥 (可选)
   - DeepSeek API密钥 (可选，用于情感分析)
3. 在"交易设置"选项卡中配置交易参数:
   - 调整止损和止盈百分比
   - 设置交易数量
   - 配置交易信号计算参数
4. 保存设置并开始监控

## 文件结构

```
shell-monitor-app/
│
├── main.py                 # 应用程序入口点
├── config.json             # 配置文件，存储API密钥和设置
├── shell_tracker_core.py   # 核心监控和交易逻辑
│
├── ui/                     # UI相关文件
│   ├── main_window.py      # 主窗口定义
│   ├── settings_dialog.py  # 设置对话框
│   └── chart_widget.py     # 自定义图表组件
│
└── requirements.txt        # 依赖项清单
```

## 注意事项

- 此应用仅为模拟交易工具，不会实际执行交易操作
- 交易信号仅供参考，不构成投资建议
- 请妥善保管您的API密钥信息

## 许可证

MIT License 