import os
import json
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def fix_config():
    """修复配置文件"""
    config_file = "config.json"
    backup_file = "config.json.bak"
    
    # 检查配置文件是否存在
    if os.path.exists(config_file):
        # 尝试读取和解析
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                existing_config = json.load(f)
            logging.info(f"配置文件 {config_file} 内容有效")
            # 可以选择在这里添加结构检查
        except json.JSONDecodeError:
            logging.error(f"配置文件 {config_file} 不是有效的JSON格式")
            # 创建备份并重置
            if os.path.exists(config_file):
                os.rename(config_file, backup_file)
                logging.info(f"已将无效的配置文件备份为 {backup_file}")
            create_default_config(config_file)
        except Exception as e:
            logging.error(f"读取配置文件时出错: {e}")
            # 创建备份并重置
            if os.path.exists(config_file):
                os.rename(config_file, backup_file)
                logging.info(f"已将可能损坏的配置文件备份为 {backup_file}")
            create_default_config(config_file)
    else:
        logging.warning(f"配置文件 {config_file} 不存在")
        create_default_config(config_file)

def create_default_config(config_file):
    """创建默认配置文件"""
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
    
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, indent=4, ensure_ascii=False)
        logging.info(f"已创建默认配置文件 {config_file}")
    except Exception as e:
        logging.error(f"创建默认配置文件失败: {e}")

if __name__ == "__main__":
    fix_config()
    print("配置文件检查/修复完成")
