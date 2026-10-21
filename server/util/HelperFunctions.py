import re
import logging
import threading
import calendar
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Any

import requests

# 尝试导入主模块的日志上下文，失败则创建本地版本
try:
    from main import _log_ctx
except ImportError:
    _log_ctx = threading.local()

logger = logging.getLogger(__name__)


def get_current_month_info() -> Dict[str, str]:
    """
    获取当前月份的开始和结束时间。

    Returns:
        Dict[str, str]: 包含当前月份开始和结束时间的字典。
    """
    now = datetime.now()
    # 当前月份的第一天
    start_of_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    # 当前月份的最后一天
    _, last_day = calendar.monthrange(now.year, now.month)
    end_of_month = now.replace(day=last_day, hour=0, minute=0, second=0, microsecond=0)

    return {
        "startTime": start_of_month.strftime("%Y-%m-%d %H:%M:%S"),
        "endTime": end_of_month.strftime("%Y-%m-%d 00:00:00Z")
    }


def desensitize_name(name: str) -> str:
    """
    对姓名进行脱敏处理，将中间部分字符替换为星号。

    Args:
        name (str): 待脱敏的姓名。

    Returns:
        str: 脱敏后的姓名。
    """
    if not name:
        return ""
        
    name = name.strip()
    n = len(name)
    
    if n < 2:
        return name
    elif n == 2:
        return f"{name[0]}*"
    else:
        return f"{name[0]}{'*' * (n - 2)}{name[-1]}"


@lru_cache(maxsize=1)
def _fetch_holiday_data(year: int) -> List[Dict[str, Any]]:
    """
    从远程获取节假日数据并缓存。
    
    Args:
        year (int): 年份。
        
    Returns:
        List[Dict[str, Any]]: 节假日数据列表。
    """
    try:
        url = f"https://gh-proxy.com/https://raw.githubusercontent.com/NateScarlet/holiday-cn/master/{year}.json"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json().get("days", [])
    except Exception as e:
        logger.error(f"获取节假日数据失败: {e}")
        return []


def is_holiday(current_datetime: datetime = None) -> bool:
    """
    判断当前日期是否为节假日或周末。

    Args:
        current_datetime (datetime): 当前日期时间，默认为系统当前时间。

    Returns:
        bool: 是否为节假日。
    """
    if current_datetime is None:
        current_datetime = datetime.now()
        
    year = current_datetime.year
    current_date = current_datetime.strftime("%Y-%m-%d")

    holiday_list = _fetch_holiday_data(year)

    # 遍历节假日数据，检查当前日期是否为节假日
    for holiday in holiday_list:
        if holiday.get("date") == current_date:
            return holiday.get("isOffDay", False)

    # 如果不是节假日，检查是否为周末
    # 周末为星期六（5）和星期日（6）
    return current_datetime.weekday() > 4


def strip_markdown(text: str) -> str:
    """
    过滤Markdown标记，保留文本内容和换行符

    Args:
        text (str): 包含Markdown标记的原始文本

    Returns:
        str: 过滤后的纯文本
    """
    if not text:
        return ""

    # 1. 移除注释
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # 2. 移除代码块 (保留代码内容)
    text = re.sub(r"```[a-zA-Z0-9]*\n([\s\S]*?)\n```", r"\1", text)

    # 3. 移除行内代码标记
    text = re.sub(r"`([^`]+)`", r"\1", text)

    # 4. 移除图片标记（保留替代文本）
    text = re.sub(r"!\[(.*?)\]\(.*?\)", r"\1", text)

    # 5. 移除超链接标记 (保留链接文本)
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)

    # 6. 移除脚注引用 例如 [^1]
    text = re.sub(r"\[\^([^\]]+)\]", "", text)

    # 7. 移除脚注定义，例如 [^1]: 示例文本
    text = re.sub(r"^\[\^.+?\]:.*$", "", text, flags=re.MULTILINE)

    # 8. 移除表格分隔
    text = re.sub(r"^\s*\|?(?:\s*[:-]+\s*\|)+\s*[:-]+\s*\|?\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\|", " ", text)

    # 9. 移除水平分割线
    text = re.sub(r"^\s*([-*_])[ \1]{2,}\s*$", "", text, flags=re.MULTILINE)

    # 10. 移除删除线
    text = re.sub(r"~~(.*?)~~", r"\1", text)

    # 11. 移除粗体和斜体标记
    text = re.sub(r"\*\*\*(.*?)\*\*\*", r"\1", text)
    text = re.sub(r"___(.*?)___", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"_(.*?)_", r"\1", text)

    # 12. 移除标题标记
    text = re.sub(r"^#{1,6}\s+(.*)$", r"\1", text, flags=re.MULTILINE)

    # 13. 移除列表标记
    text = re.sub(r"^(\s*)[-*+]\s+\[.\]\s+", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)[-*+]\s+", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)\d+\.\s+", r"\1", text, flags=re.MULTILINE)

    # 14. 移除引用标记
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)

    # 15. 移除行内 HTML 标签
    text = re.sub(r"</?[^>]+>", "", text)

    # 16. 多空白行合并
    text = re.sub(r"\n\s*\n", "\n\n", text)
    
    return text.strip()
