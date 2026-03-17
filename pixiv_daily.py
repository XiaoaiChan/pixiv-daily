#!/usr/bin/env python3
"""
🎨 Pixiv 每日精选推送
由 aimy 直接抓图并发送飞书，本地只负责调度

用法：
  python3 pixiv_daily.py           # 日榜 Top 5
  python3 pixiv_daily.py --top 3   # Top 3
  python3 pixiv_daily.py --mode weekly
"""

import json, os, sys, argparse, subprocess, tempfile
from datetime import datetime
from pathlib import Path

FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_USER_ID = os.environ.get("FEISHU_USER_ID", "")
AIMY_HOST = os.environ.get("AIMY_HOST", "aimy@your-server")

MODE_LABELS = {"daily":"日榜","weekly":"周榜","monthly":"月榜","rookie":"新人榜"}

# 在 aimy 上执行的完整脚本（抓图 + 直接发飞书）
AIMY_FULL_SCRIPT = '''\
import requests, json, sys

FEISHU_APP_ID = "{app_id}"
FEISHU_APP_SECRET = "{app_secret}"
FEISHU_USER_ID = "{user_id}"
MODE = "{mode}"
TOP_N = {top_n}
TODAY = "{today}"
LABEL = "{label}"

headers = {{
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.pixiv.net/",
}}

def feishu_token():
    r = requests.post("https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={{"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET}}, timeout=10)
    return r.json()["tenant_access_token"]

def send_text(token, text):
    requests.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        headers={{"Authorization": f"Bearer {{token}}", "Content-Type": "application/json"}},
        json={{"receive_id": FEISHU_USER_ID, "msg_type": "text", "content": json.dumps({{"text": text}})}}, timeout=10)

def send_image(token, img_bytes, filename="img.jpg"):
    r = requests.post("https://open.feishu.cn/open-apis/im/v1/images",
        headers={{"Authorization": f"Bearer {{token}}"}},
        files={{"image_type": (None, "message"), "image": (filename, img_bytes, "image/jpeg")}}, timeout=30)
    image_key = r.json()["data"]["image_key"]
    requests.post("https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
        headers={{"Authorization": f"Bearer {{token}}", "Content-Type": "application/json"}},
        json={{"receive_id": FEISHU_USER_ID, "msg_type": "image", "content": json.dumps({{"image_key": image_key}})}}, timeout=10)

# 1. 抓排行榜
print(f"抓取 Pixiv {{LABEL}} Top {{TOP_N}}...")
r = requests.get(f"https://www.pixiv.net/ranking.php?mode={{MODE}}&content=illust&format=json&p=1",
    headers=headers, timeout=15)
items = r.json().get("contents", [])[:TOP_N]

# 2. 发标题文字
header = f"🎨 Pixiv {{LABEL}}精选 · {{TODAY}}\\n\\n"
for item in items:
    header += f"#{{item['rank']}} 《{{item['title']}}》\\n"
    header += f"   👤 {{item['user_name']}}  🔗 https://www.pixiv.net/artworks/{{item['illust_id']}}\\n"
token = feishu_token()
send_text(token, header)
print("标题发送完成")

# 3. 逐张下载并发图
for item in items:
    illust_id = item["illust_id"]
    r2 = requests.get(f"https://www.pixiv.net/ajax/illust/{{illust_id}}/pages", headers=headers, timeout=10)
    pages = r2.json().get("body", [])
    if not pages:
        print(f"  跳过 #{{item['rank']}}：无图片")
        continue
    img_url = pages[0]["urls"]["regular"]
    img_data = requests.get(img_url, headers=headers, timeout=20)
    token = feishu_token()
    send_image(token, img_data.content, f"pixiv_{{illust_id}}.jpg")
    sz = len(img_data.content)//1024
    print(f"  ✅ #{{item['rank']}} {{item['title'][:20]}} ({{sz}}KB)")

print("DONE")
'''


def main():
    parser = argparse.ArgumentParser(description="🎨 Pixiv 每日精选推送")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--mode", default="daily", choices=["daily","weekly","monthly","rookie"])
    args = parser.parse_args()

    today = datetime.now().strftime("%Y年%m月%d日")
    label = MODE_LABELS.get(args.mode, args.mode)

    script = AIMY_FULL_SCRIPT.format(
        app_id=FEISHU_APP_ID, app_secret=FEISHU_APP_SECRET,
        user_id=FEISHU_USER_ID, mode=args.mode, top_n=args.top,
        today=today, label=label
    )

    # 写脚本到 aimy
    script_path = "/tmp/pixiv_daily_run.py"
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as f:
        f.write(script)
        tmp = f.name

    subprocess.run(["scp", "-q", tmp, f"{AIMY_HOST}:{script_path}"], check=True, timeout=10)
    os.unlink(tmp)

    print(f"🚀 启动 aimy 执行（{label} Top {args.top}）...")
    result = subprocess.run(
        ["ssh", AIMY_HOST, f"python3 {script_path}"],
        timeout=300
    )

    if result.returncode == 0:
        print("✅ 全部完成！")
    else:
        print("❌ 执行失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
