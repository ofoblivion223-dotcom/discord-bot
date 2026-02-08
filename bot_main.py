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
                channel = discord.utils.get(guild.text_channels, name="general")
                if channel: break

        if not channel:
            print("Channel not found.")
            await self.close()
            return

        # 2. 状態の読み込み
        if not os.path.exists(STATE_FILE):
            default_state = {"status": "idle", "current_post_id": None, "welcomed": False}
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_state, f)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # 3. 使い方ガイドの自動投稿（初回のみ）
        if not state.get('welcomed', False):
            welcome_msg = "## 🤖 零式日程調整君 導入完了！\n"
            welcome_msg += "このボットは、金曜日21時に募集を自動開始し、8人揃った瞬間に日程を確定します。\n\n"
            welcome_msg += "### 💡 管理者用コマンド（チャットに入力してGitHub Actionを実行）\n"
            welcome_msg += "- `!post` : 直ちに新しい募集を強制開始します。\n"
            welcome_msg += "- `!reset` : ボットの状態を初期化し、募集待機状態(idle)に戻します。\n\n"
            welcome_msg += "※コマンド送信後、GitHub Actionsの **「Run workflow」** からボットを動かしてください。"
            await channel.send(welcome_msg)
            state['welcomed'] = True

        # 4. テスト・運用コマンドの確認
        async for msg in channel.history(limit=5):
            if msg.content == "!reset":
                state['status'] = 'idle'
                state['current_post_id'] = None
                print("Force reset by !reset command")
            elif msg.content == "!post":
                state['status'] = 'idle'
                print("Force post by !post command")

        # JST時間の取得 (UTC+9)
        now_jst = datetime.utcnow() + timedelta(hours=9)
        weekday = now_jst.weekday() # 4:金, 5:土, 6:日
        hour = now_jst.hour

        # 5. 【金曜 21時】新規募集投稿
        if state['status'] == 'idle' and weekday == 4 and hour >= 21:
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

        # 6. 自動判定 & 催促ロジック
        elif state['status'] == 'gathering' and state['current_post_id']:
            try:
                message = await channel.fetch_message(state['current_post_id'])
                scores = []
                responded_users = set()
                
                for i, emoji in enumerate(EMOJIS):
                    reaction = discord.utils.get(message.reactions, emoji=emoji)
                    count = 0
                    if reaction:
                        count = reaction.count - 1
                        async for user in reaction.users():
                            if user.id != self.user.id:
                                responded_users.add(user.display_name)
                    scores.append({"index": i, "date": state['dates'][i], "count": count})

                # A. 8人揃ったかチェック（時系列順）
                winner = next((s for s in scores if s['count'] >= 8), None)
                if winner:
                    announcement = f"@everyone\n**【日程確定】零式消化**\n"
                    announcement += f"✅ **{winner['date']} 21:00〜** に決定しました！\nよろしくお願いします。"
                    await channel.send(announcement)
                    state['status'] = 'idle'
                    state['current_post_id'] = None
                
                # B. 【土曜・日曜 21時】催促 ＆ 候補3選表示
                elif weekday in [5, 6] and hour >= 21 and state.get('last_reminded_at') != now_jst.strftime("%Y-%m-%d"):
                    top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                    user_list_str = "、".join(responded_users) if responded_users else "なし"
                    remind_msg = f"@everyone **【日程調整：週末確認】**\n"
                    remind_msg += f"✅ **入力済みメンバー（{len(responded_users)}人）**: {user_list_str}\n\n"
                    remind_msg += "📊 **現在の有力候補（上位3日）**\n"
                    for s in top3:
                        remind_msg += f"- {s['date']} ： 現在 {s['count']}人\n"
                    await channel.send(remind_msg)
                    state['last_reminded_at'] = now_jst.strftime("%Y-%m-%d")

            except discord.NotFound:
                state['status'] = 'idle'

        # 7. 状態の保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

        await self.close()

if __name__ == "__main__":
    if not TOKEN: sys.exit(1)
    intents = discord.Intents.all()
    client = MyBot(intents=intents)
    client.run(TOKEN)
