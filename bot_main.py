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
    # 翌火曜日（リセット日）を起点とした7日間を生成
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
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump({"status": "idle", "current_post_id": None}, f)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # 3. テスト・運用コマンド（Discordからの操作）
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

        # 4. 【金曜 21時】新規募集投稿
        if state['status'] == 'idle' and weekday == 4 and hour >= 21:
            state['dates'] = get_next_week_dates()
            content = f"@everyone\n**【零式消化】今週の予定を確認します**\n"
            content += "全員（8人）揃った日に自動決定します（21:00〜）\n\n"
            for i, d in enumerate(state['dates']):
                content += f"{EMOJIS[i]} : {d}\n"
            
            message = await channel.send(content)
            for emoji in EMOJIS:
                await message.add_reaction(emoji)
            
            state['current_post_id'] = message.id
            state['status'] = 'gathering'
            state['last_reminded_at'] = None
            print(f"Posted new gathering message: {message.id}")

        # 5. 自動判定 & 催促ロジック
        elif state['status'] == 'gathering' and state['current_post_id']:
            try:
                message = await channel.fetch_message(state['current_post_id'])
                scores = []
                responded_users = set()
                
                # リアクション情報の収集
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
                    announcement += f"✅ **{winner['date']} 21:00〜** に決定しました！\n"
                    announcement += "よろしくお願いします。"
                    await channel.send(announcement)
                    
                    state['status'] = 'idle'
                    state['current_post_id'] = None
                    print(f"Confirmed date: {winner['date']}")
                
                # B. 【土曜・日曜 21時】催促 ＆ 候補3選表示
                elif weekday in [5, 6] and hour >= 21 and state.get('last_reminded_at') != now_jst.strftime("%Y-%m-%d"):
                    # 得点順にソートして上位3つを出す
                    top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                    user_list_str = "、".join(responded_users) if responded_users else "なし"
                    
                    remind_msg = f"@everyone **【日程調整：週末確認】**\n"
                    remind_msg += f"✅ **入力済みメンバー（{len(responded_users)}人）**: {user_list_str}\n\n"
                    remind_msg += "📊 **現在の有力候補（上位3日）**\n"
                    for s in top3:
                        remind_msg += f"- {s['date']} ： 現在 {s['count']}人\n"
                    
                    await channel.send(remind_msg)
                    state['last_reminded_at'] = now_jst.strftime("%Y-%m-%d")
                    print("Sent weekend reminder.")

            except discord.NotFound:
                print("Original message not found, resetting status...")
                state['status'] = 'idle'

        # 6. 状態の保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

        await self.close()

if __name__ == "__main__":
    if not TOKEN:
        sys.exit(1)
        
    intents = discord.Intents.all()
    client = MyBot(intents=intents)
    client.run(TOKEN)
