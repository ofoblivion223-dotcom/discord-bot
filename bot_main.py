import discord
import json
import os
import sys
from datetime import datetime, timedelta

# 設定
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID_STR = os.getenv('DISCORD_CHANNEL_ID')
CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR and CHANNEL_ID_STR.isdigit() else 0
STATE_FILE = 'state.json'
TARGET_CHANNEL_NAME = "零式日程調整"
EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬"]

def get_next_week_dates():
    today = datetime.now()
    days_until_tuesday = (1 - today.weekday() + 7) % 7
    if days_until_tuesday == 0: days_until_tuesday = 7
    next_tuesday = today + timedelta(days=days_until_tuesday)
    dates = []
    for i in range(7):
        current = next_tuesday + timedelta(days=i)
        dates.append(current.strftime("%m/%d") + "(" + ["月","火","水","木","金","土","日"][current.weekday()] + ")")
    return dates

class MyBot(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        
        # 1. 投稿先のチャンネルを特定
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name=TARGET_CHANNEL_NAME)
                if channel: break
                else:
                    try:
                        channel = await guild.create_text_channel(TARGET_CHANNEL_NAME)
                        break
                    except: pass

        if not channel:
            print("Channel not found.")
            await self.close()
            return
        
        print(f"Target Channel: #{channel.name} ({channel.id})") # どこを見ているか表示

        # 2. 状態の読み込み
        if not os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({"status": "idle", "current_post_id": None, "welcomed": False}, f)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # 3. コマンド確認
        force_post = False
        async for msg in channel.history(limit=5):
            if msg.content == "!reset":
                state['status'] = 'idle'
                state['current_post_id'] = None
                print("Command detected: !reset")
            elif msg.content == "!post":
                state['status'] = 'idle'
                force_post = True  # ここが重要！
                print("Command detected: !post")

        # JST時間の取得
        now_jst = datetime.utcnow() + timedelta(hours=9)
        weekday = now_jst.weekday()
        hour = now_jst.hour

        # 4. 投稿判定 (金曜21時 OR 強制投稿)
        if state['status'] == 'idle':
            if (weekday == 4 and hour >= 21) or force_post:
                state['dates'] = get_next_week_dates()
                content = f"@everyone\n**【零式消化】今週の予定を確認します**\n"
                content += "全員（8人）揃った日に自動決定します（21:00〜）\n\n"
                for i, d in enumerate(state['dates']):
                    content += f"{EMOJIS[i]} : {d}\n"
                
                message = await channel.send(content)
                for emoji in EMOJIS: await message.add_reaction(emoji)
                state['current_post_id'] = message.id
                state['status'] = 'gathering'
                state['last_reminded_at'] = None
                print("Gathering message posted.")
                
                # 最初だけ説明も出す
                if not state.get('welcomed', False):
                    welcome = "## 🤖 導入完了！\n金曜21時自動投稿、土日催促、8人確定モードで動作します。"
                    await channel.send(welcome)
                    state['welcomed'] = True

        # 5. 集計ロジック (既存と同じ)
        elif state['status'] == 'gathering' and state['current_post_id']:
            try:
                message = await channel.fetch_message(state['current_post_id'])
                scores = []
                responded_users = set()
                for i, emoji in enumerate(EMOJIS):
                    reaction = discord.utils.get(message.reactions, emoji=emoji)
                    count = reaction.count - 1 if reaction else 0
                    if reaction:
                        async for user in reaction.users():
                            if user.id != self.user.id: responded_users.add(user.display_name)
                    scores.append({"date": state['dates'][i], "count": count})

                winner = next((s for s in scores if s['count'] >= 8), None)
                if winner:
                    await channel.send(f"@everyone\n**【日程確定】**\n✅ **{winner['date']} 21:00〜** に決定！")
                    state['status'] = 'idle'
                    state['current_post_id'] = None
                elif weekday in [5, 6] and hour >= 21 and state.get('last_reminded_at') != now_jst.strftime("%Y-%m-%d"):
                    top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                    users = "、".join(responded_users) if responded_users else "なし"
                    remind = f"@everyone **【週末確認】**\n✅ **入力済み**: {users}\n📊 **有力候補**:\n"
                    for s in top3: remind += f"- {s['date']} ({s['count']}人)\n"
                    await channel.send(remind)
                    state['last_reminded_at'] = now_jst.strftime("%Y-%m-%d")
            except:
                state['status'] = 'idle'

        # 6. 保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        await self.close()

if __name__ == "__main__":
    client = MyBot(intents=discord.Intents.all())
    client.run(TOKEN)
