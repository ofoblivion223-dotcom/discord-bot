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
TARGET_CHANNEL_NAME = "零式消化日程"
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
        
        # --- 1. チャンネルの特定/作成 (最優先) ---
        channel = None
        is_new_channel = False
        
        # CHANNEL_ID が設定されていれば、まずそれで探す
        if CHANNEL_ID > 0:
            channel = self.get_channel(CHANNEL_ID)
            if channel:
                print(f"Found channel by ID: #{channel.name}")
        
        # CHANNEL_ID が未設定または見つからない場合、チャンネル名で探す
        if not channel:
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name=TARGET_CHANNEL_NAME)
                if channel:
                    print(f"Found channel by name in guild '{guild.name}': #{channel.name}")
                    break
        
        # まだ見つからない場合、チャンネルを作成
        if not channel:
            for guild in self.guilds:
                try:
                    channel = await guild.create_text_channel(TARGET_CHANNEL_NAME)
                    print(f"Created new channel in guild '{guild.name}': #{TARGET_CHANNEL_NAME}")
                    is_new_channel = True
                    break
                except Exception as e:
                    print(f"Failed to create channel in guild '{guild.name}': {e}")
        
        if not channel:
            print("Channel not found and could not be created.")
            await self.close()
            return

        # --- 2. 状態の読み込み ---
        if not os.path.exists(STATE_FILE):
            state = {"status": "idle", "current_post_id": None, "welcomed": False}
        else:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

        # --- 3. 挨拶投稿 (チャンネルが新しければ強制投稿) ---
        if not state.get('welcomed', False) or is_new_channel:
            welcome_msg = f"## 🤖 零式消化日程ボット 起動成功！\n"
            welcome_msg += f"このチャンネル「#{channel.name}」で動作します。\n\n"
            welcome_msg += "### 🛠 管理者用コマンド\n"
            welcome_msg += "- `!post` : 直ちに新規募集を強制開始。\n"
            welcome_msg += "- `!remind` : 催促メッセージをテスト投稿。\n"
            welcome_msg += "- `!reset` : ステータスをリセット(idleへ)。\n\n"
            welcome_msg += "※コマンド送信後、GitHub Actionsの **「Run workflow」** を実行してください。"
            await channel.send(welcome_msg)
            state['welcomed'] = True
            # 新しいチャンネルなら一旦idleにする（テストしやすくするため）
            if is_new_channel: state['status'] = 'idle'

        # --- 4. コマンド確認 ---
        force_post = False
        force_remind = False
        async for msg in channel.history(limit=5):
            if msg.content == "!reset":
                state['status'] = 'idle'
                state['current_post_id'] = None
            elif msg.content == "!post":
                state['status'] = 'idle'
                force_post = True
            elif msg.content == "!remind":
                force_remind = True

        # --- 5. メインロジック ---
        now_jst = datetime.utcnow() + timedelta(hours=9)
        weekday = now_jst.weekday()
        hour = now_jst.hour

        # A. 募集 (金曜21時 or !post)
        if (state['status'] == 'idle' and weekday == 4 and hour >= 21) or force_post:
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

        # B. 集計・催促 (月曜19時に1回だけ)
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
                    await channel.send(f"@everyone\n**【日程確定】**\n✅ **{winner['date']} 21:00〜** に決定しました！")
                    state['status'] = 'idle'
                    state['current_post_id'] = None
                
                # 月曜日の19時に1回だけ催促を送信
                elif weekday == 0 and 19 <= hour < 20 and (state.get('last_reminded_at') != now_jst.strftime("%Y-%m-%d") or force_remind):
                    top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                    users = "、".join(responded_users) if responded_users else "なし"
                    remind = f"@everyone **【週末確認】**\n✅ **入力済み**: {users}\n📊 **有力候補**:\n"
                    for s in top3: remind += f"- {s['date']} ({s['count']}人)\n"
                    await channel.send(remind)
                    state['last_reminded_at'] = now_jst.strftime("%Y-%m-%d")
            except:
                state['status'] = 'idle'

        # 保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        await self.close()

if __name__ == "__main__":
    client = MyBot(intents=discord.Intents.default())
    client.run(TOKEN)
