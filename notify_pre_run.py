"""预跑提醒：通过 Server酱 推送到个人微信。

由计划任务 SecurityIntelDailyBrief_Notify 在每天 08:28（北京时间）触发。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import requests

from app.config import Config


def main() -> None:
    key = Config().serverchan_key
    if not key:
        print("未配置 SERVERCHAN_KEY，跳过")
        return

    title = "安防日报提醒"
    desp = "今日安防日报将在 2 分钟后自动生成（08:30），稍后请查收 Outlook 草稿箱"
    url = f"https://sctapi.ftqq.com/{key}.send"

    try:
        session = requests.Session()
        session.trust_env = False  # 不走代理（Server酱为国内服务）
        resp = session.post(url, data={"title": title, "desp": desp}, timeout=20)
        data = resp.json()
        if data.get("code") == 0:
            print("Server酱推送成功")
        else:
            print("Server酱返回：", data)
    except Exception as exc:
        print("Server酱推送失败：", exc)


if __name__ == "__main__":
    main()
