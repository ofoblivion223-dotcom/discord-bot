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
TARGET_CHANNEL_NAME = "零式消化日程" # 指定の名前に変更
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
        
        # 1. 投稿先のチャンネルを特定（なければ "#{TARGET_CHANNEL_NAME}" を作成）
        channel = self.get_channel(CHANNEL_ID)
        if not channel:
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name=TARGET_CHANNEL_NAME)
                if channel:
                    break
                else:
                    try:
                        channel = await guild.create_text_channel(TARGET_CHANNEL_NAME, reason="零式日程調整用")
                        print(f"Created new channel: #{TARGET_CHANNEL_NAME}")
                        break
                    except Exception as e:
                        print(f"Channel create Error: {e}")

        if not channel:
            print("Channel not found/could not be created.")
            await self.close()
            return

        # 2. 状態の読み込み
        if not os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({"status": "idle", "current_post_id": None, "welcomed": False}, f)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # 3. 使い方ガイドの自動投稿（初回のみ）
        if not state.get('welcomed', False):
            welcome_msg = f"## 🤖 零式消化日程ボット 起動完了！\n"
            welcome_msg += f"このチャンネル「#{channel.name}」で日程調整をサポートします。\n\n"
            welcome_msg += "- **自動投稿**: 毎週金曜日 21:00\n"
            welcome_msg += "- **自動決定**: 8人の反応が揃った瞬間に確定\n"
            welcome_msg += "- **催促投稿**: 土曜日・日曜日の 21:00（入力済みメンバーと有力候補を表示）\n\n"
            welcome_msg += "### 🛠 管理者用テストコマンド（入力してRun workflowを実行）\n"
            welcome_msg += "- `!post` : 直ちに新規募集を強制開始します。\n"
            welcome_msg += "- `!remind` : 週末専用の「催促メッセージ」を今すぐテスト投稿します。\n"
            welcome_msg += "- `!reset` : ボットを初期状態に戻します。"
            await channel.send(welcome_msg)
            state['welcomed'] = True

        # 4. コマンド確認ロジック
        force_post = False
        force_remind = False
        async for msg in channel.history(limit=5):
            if msg.content == "!reset":
                state['status'] = 'idle'
                state['current_post_id'] = None
                print("Command: !reset")
            elif msg.content == "!post":
                state['status'] = 'idle'
                force_post = True
                print("Command: !post")
            elif msg.content == "!remind":
                force_remind = True
                print("Command: !remind")

        # JST時間の取得
        now_jst = datetime.utcnow() + timedelta(hours=9)
        weekday = now_jst.weekday()
        hour = now_jst.hour

        # 5. 投稿ロジック (金曜21時 or !post)
        if (state['status'] == 'idle' and weekday == 4 and hour >= 21) or (force_post):
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

        # 6. 集計・催促ロジック
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
                            if user.id != self.user.id:
                                responded_users.add(user.display_name)
                    scores.append({"date": state['dates'][i], "count": count})

                # A. 自動判定 (8人)
                winner = next((s for s in scores if s['count'] >= 8), None)
                if winner:
                    await channel.send(f"@everyone\n**【日程確定】**\n✅ **{winner['date']} 21:00〜** に決定しました！")
                    state['status'] = 'idle'
                    state['current_post_id'] = None
                
                # B. 催促 (土日21時 or !remind)
                should_remind = (weekday in [5, 6] and hour >= 21 and state.get('last_reminded_at') != now_jst.strftime("%Y-%m-%d"))
                if should_remind or force_remind:
                    top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                    users = "、".join(responded_users) if responded_users else "なし"
                    remind_msg = f"@everyone **【日程調整：週末確認】**\n"
                    remind_msg += f"✅ **入力済みメンバー（{len(responded_users)}人）**: {users}\n\n"
                    remind_msg += "📊 **現在の有力候補（上位3日）**\n"
                    for s in top3:
                        remind_msg += f"- {s['date']} ： 現在 {s['count']}人\n"
                    await channel.send(remind_msg)
                    if not force_remind:
                        state['last_reminded_at'] = now_jst.strftime("%Y-%m-%d")

            except discord.NotFound:
                state['status'] = 'idle'

        # 7. 保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        await self.close()

if __name__ == "__main__":
    intents = discord.Intents.all()
    client = MyBot(intents=intents)
    client.run(TOKEN)
