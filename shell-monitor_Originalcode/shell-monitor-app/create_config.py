import json
import os

# 默认配置
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

# 将配置写入文件
try:
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(default_config, f, indent=4, ensure_ascii=False)
    print("已成功创建配置文件 config.json")
except Exception as e:
    print(f"创建配置文件失败: {e}")
