"""
@ Author ：weicai
@ Date ： 2024/8/12
@ Description：I'm in charge of my Code
"""
import os
import logging.config

from pathlib import Path

log_path = Path(__file__).resolve().parent.parent / "logs"
if not log_path.exists():
    os.makedirs(log_path)

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s %(thread)d %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s'
        },
        'recode': {
            'format': '%(message)s,'
        },
    },
    'handlers': {
        'console': {
            'level': 'DEBUG',
            'class': 'logging.StreamHandler',
            'formatter': 'standard'
        },
        'file': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'formatter': 'standard',
            'filename': f'{log_path}/info.log',
            'encoding': 'utf-8',
            'when': 'D',
            'backupCount': 20
        },
        'recode': {
            'level': 'INFO',
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'formatter': 'recode',
            'filename': f'{log_path}/recode.log',
            'encoding': 'utf-8',
            'when': 'D',
            'backupCount': 100
        }
    },
    'loggers': {
        '': {
            'handlers': ['console', 'file'],
            'level': 'INFO',
            'propagate': False
        },
        "recode": {
            "handlers": ["recode"],
            "level": "INFO",
            "propagate": False
        }
    }
}

# 加载配置字典
logging.config.dictConfig(LOGGING_CONFIG)

# 获取日志记录器
logger = logging.getLogger(__name__)
logger_recode = logging.getLogger('recode')
