#!/usr/bin/env python3
"""clc - Claude Code のレート残量を表示する CLI ツール。

使い方:
    clc rate          レート残量をプログレスバー付きで表示
    clc rate --json   API の生レスポンスを JSON で表示
"""

import argparse
import json
import os
import subprocess
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone

USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
KEYCHAIN_SERVICE = "Claude Code-credentials"
CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_DEFAULTS = {
    "bar_width": 13,
    "label_width": 7,
    "monthly_limit_usd": 10.0,
    "color_warn_threshold": 50,
    "color_danger_threshold": 80,
    "window_labels": {
        "five_hour": "5Hours",
        "seven_day": "Weekly",
        "seven_day_opus": "Weekly(Opus)",
        "seven_day_sonnet": "Weekly(Sonnet)",
        "seven_day_oauth_apps": "Weekly(OAuth Apps)",
        "extra_usage": "Extra",
    },
    "window_order": [
        "five_hour",
        "seven_day",
        "seven_day_opus",
        "seven_day_sonnet",
        "seven_day_oauth_apps",
        "extra_usage",
    ],
}


def _load_config():
    cfg = dict(_DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, encoding="utf-8") as f:
            overrides = json.load(f)
        cfg.update(overrides)
    return cfg


_CFG = _load_config()


class ClcError(Exception):
    """ユーザー向けエラーメッセージを持つ例外。"""


def load_credentials():
    """Keychain またはファイルから OAuth 認証情報(JSON)を読み込む。"""
    raw = None
    if sys.platform == "darwin":
        try:
            result = subprocess.run(
                ["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                raw = result.stdout.strip()
        except FileNotFoundError:
            pass

    if raw is None and os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, encoding="utf-8") as f:
            raw = f.read()

    if raw is None:
        raise ClcError(
            "Claude Code の認証情報が見つかりません。\n"
            f"  Keychain (サービス名: {KEYCHAIN_SERVICE}) と "
            f"{CREDENTIALS_PATH} の両方を確認しました。\n"
            "  Claude Code を一度起動してログインしてください。"
        )

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ClcError(f"認証情報の JSON を解析できません: {e}") from e


def get_access_token():
    creds = load_credentials()
    oauth = creds.get("claudeAiOauth") or {}
    token = oauth.get("accessToken")
    if not token:
        raise ClcError(
            "認証情報に accessToken が含まれていません。Claude Code で再ログインしてください。"
        )

    expires_at = oauth.get("expiresAt")  # epoch ミリ秒
    if expires_at and expires_at / 1000 < datetime.now(timezone.utc).timestamp():
        raise ClcError(
            "OAuth トークンの有効期限が切れています。\n"
            "  Claude Code を一度起動するとトークンが自動更新されます。"
        )
    return token


def fetch_usage(token):
    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
            "User-Agent": "clc-rate/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            return json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 401:
            raise ClcError(
                "認証エラー (401): トークンが無効です。\n"
                "  Claude Code を一度起動してトークンを更新してください。"
            ) from e
        raise ClcError(f"API エラー (HTTP {e.code}): {e.read().decode('utf-8', 'replace')[:300]}") from e
    except urllib.error.URLError as e:
        raise ClcError(f"ネットワークエラー: {e.reason}") from e


def parse_resets_at(value):
    """resets_at (ISO 文字列または epoch 秒) をローカル時刻の datetime に変換する。"""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float)):
            dt = datetime.fromtimestamp(value, tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(value))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone()
    except (ValueError, OSError):
        return None


def format_remaining(dt):
    """リセットまでの残り時間を「あとN時間M分」形式で返す。"""
    delta = dt - datetime.now(dt.tzinfo)
    total_min = max(0, int(delta.total_seconds() // 60))
    days, rem = divmod(total_min, 1440)
    hours, minutes = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d,")
    if hours:
        parts.append(f"{hours:02d}h")
    parts.append(f"{minutes:02d}m")
    return "".join(parts)


def pad_display(text, width):
    """全角文字を幅2として、表示幅 width まで右に空白を詰める。"""
    w = sum(2 if unicodedata.east_asian_width(c) in "FW" else 1 for c in text)
    return text + " " * max(0, width - w)


def colorize(text, utilization, use_color):
    if not use_color:
        return text
    if utilization >= _CFG["color_danger_threshold"]:
        code = "31"  # 赤
    elif utilization >= _CFG["color_warn_threshold"]:
        code = "33"  # 黄
    else:
        code = "32"  # 緑
    return f"\033[{code}m{text}\033[0m"


def render_window(key, data, use_color):
    label = _CFG["window_labels"].get(key, key)
    utilization = data.get("utilization")
    if utilization is None:
        return None

    utilization = float(utilization)
    bar_width = _CFG["bar_width"]
    filled = round(bar_width * min(utilization, 100) / 100)
    bar = "█" * filled + "░" * (bar_width - filled)
    bar = colorize(bar, utilization, use_color)

    label_width = _CFG["label_width"]
    lines = [f"{pad_display(label, label_width)}[{bar}] {utilization:5.1f}% used"]
    resets = parse_resets_at(data.get("resets_at"))

    if resets:
        lines.append(f"{' ' * label_width}resets in {format_remaining(resets)}")
    elif key == "extra_usage":
        monthly_limit = _CFG["monthly_limit_usd"]
        used_amount = (utilization / 100.0) * monthly_limit
        lines.append(f"{' ' * label_width}used ${used_amount:.2f}")

    return "\n".join(lines)


def cmd_rate(args):
    token = get_access_token()
    usage = fetch_usage(token)

    if args.json:
        print(json.dumps(usage, ensure_ascii=False, indent=2))
        return 0

    use_color = sys.stdout.isatty()
    windows = {k: v for k, v in usage.items() if isinstance(v, dict) and "utilization" in v}
    window_order = _CFG["window_order"]
    ordered = [k for k in window_order if k in windows]
    ordered += sorted(k for k in windows if k not in window_order)

    # print(f"Claude Code rate remaining:")
    if not ordered:
        print("レート情報が取得できませんでした。--json で生レスポンスを確認してください。")
        return 1
    for i, key in enumerate(ordered):
        block = render_window(key, windows[key], use_color)
        if block:
            print(block, end=("\n\n" if i < len(ordered) - 1 else "\n"))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="clc", description="Claude Code ユーティリティ CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    rate_parser = subparsers.add_parser("rate", help="レート残量を表示する")
    rate_parser.add_argument("--json", action="store_true", help="API の生レスポンスを JSON で表示")
    rate_parser.set_defaults(func=cmd_rate)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ClcError as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
