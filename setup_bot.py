"""Interactive helper: asks for the bot token and channel, checks them with Telegram, writes .env."""
import getpass
import json
import re
import urllib.request
from pathlib import Path

ENV = Path(__file__).resolve().parent / ".env"


def tg(token: str, method: str, **params) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"https://api.telegram.org/bot{token}/{method}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def ask_token() -> tuple[str, dict]:
    while True:
        print("\n1) Встав токен від @BotFather (символи не відображатимуться, це нормально) і натисни Enter:")
        token = getpass.getpass("   Токен: ").strip()
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]{30,}", token):
            print("   ❌ Не схоже на токен. Він виглядає так: 7123456789:AAH... Спробуй ще раз.")
            continue
        me = tg(token, "getMe")
        if me.get("ok"):
            print(f"   ✅ Бот знайдений: @{me['result']['username']}")
            return token, me["result"]
        print("   ❌ Telegram не прийняв токен. Скопіюй його з @BotFather ще раз.")


def ask_channel(token: str, bot_id: int) -> str:
    while True:
        print("\n2) Введи посилання на канал, наприклад @steam_znyzhky_ua або https://t.me/steam_znyzhky_ua:")
        raw = input("   Канал: ").strip()
        name = raw.replace("https://", "").replace("http://", "").replace("t.me/", "").lstrip("@").strip("/")
        if not name:
            continue
        channel = f"@{name}"
        member = tg(token, "getChatMember", chat_id=channel, user_id=bot_id)
        if not member.get("ok"):
            print(f"   ❌ Канал {channel} не знайдено або бот не доданий туди.")
            print("      Перевір: канал публічний, посилання правильне, бот доданий в адміністратори.")
            continue
        res = member["result"]
        if res.get("status") == "administrator" and res.get("can_post_messages", True):
            print(f"   ✅ Бот є адміністратором у {channel} і може публікувати")
            return channel
        print("   ❌ Бот у каналі, але не адміністратор з правом публікувати.")
        print("      Канал → Адміністратори → бот → увімкни «Публікація повідомлень». Потім введи канал ще раз.")


def main() -> None:
    print("=== Налаштування Steam Deals Bot ===")
    token, me = ask_token()
    channel = ask_channel(token, me["id"])

    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    values = {"BOT_TOKEN": token, "CHANNEL_ID": channel}
    out, seen = [], set()
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in seen]
    ENV.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n🎉 Готово! Налаштування збережені. Повернись у чат з Claude і напиши «готово».")


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (used in tg)
    main()
