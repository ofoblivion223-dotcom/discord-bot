import discord
import json
import os
import sys
from datetime import datetime, timedelta

# 設定の読み込み (GitHub Secrets)
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
# IDがない場合は0にする（後で名前で検索するため）
CHANNEL_ID_STR = os.getenv('DISCORD_CHANNEL_ID')
CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR and CHANNEL_ID_STR.isdigit() else 0

STATE_FILE = 'state.json'
EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬"]

def get_next_week_dates():
    # 翌火曜日（リセット日）を起点とした7日間を生成
    today = datetime.now()
    # 0=月, 1=火, ... 6=日。次の火曜日(1)までの日数を計算
    days_until_tuesday = (1 - today.weekday() + 7) % 7
    # 日曜に実行した場合、days_until_tuesday は 2 (火曜) になる
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
            # IDで見つからない場合、参加サーバーから "general" を探す
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
                json.dump({"count": 0, "status": "idle", "current_post_id": None}, f)

        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)

        # 3. テスト・運用を楽にするためのDiscordコマンド確認
        # 直近のメッセージを見て状態を操作する
        async for msg in channel.history(limit=5):
            if msg.content == "!reset":
                state['status'] = 'idle'
                state['current_post_id'] = None
                print("Force reset triggered by !reset command")
            elif msg.content == "!post":
                state['status'] = 'idle'
                print("Force post triggered by !post command")

        now = datetime.now()
        
        # 4. 募集投稿ロジック
        if state['status'] == 'idle':
            state['count'] += 1
            dates = get_next_week_dates()
            content = f"@everyone\n**【零式消化{state['count']}】今週の予定を確認します**\n"
            content += "全員（8人）揃った日に自動決定します（21:00〜）\n\n"
            for i, d in enumerate(dates):
                content += f"{EMOJIS[i]} : {d}\n"
            
            message = await channel.send(content)
            for emoji in EMOJIS:
                await message.add_reaction(emoji)
            
            state['current_post_id'] = message.id
            state['status'] = 'gathering'
            state['dates'] = dates
            print(f"Posted new gathering message: {message.id}")

        # 5. 集計ロジック
        elif state['status'] == 'gathering' and state['current_post_id']:
            try:
                message = await channel.fetch_message(state['current_post_id'])
                selected_index = -1
                
                for i, emoji in enumerate(EMOJIS):
                    reaction = discord.utils.get(message.reactions, emoji=emoji)
                    if reaction:
                        # テスト時はここを 1 に、本番は 8 にしてください
                        if reaction.count - 1 >= 8:
                            selected_index = i
                            break
                
                if selected_index != -1:
                    confirmed_date = state['dates'][selected_index]
                    announcement = f"@everyone\n**【日程確定】零式消化{state['count']}**\n"
                    announcement += f"✅ **{confirmed_date} 21:00〜** に決定しました！\n"
                    announcement += "よろしくお願いします。"
                    await channel.send(announcement)
                    
                    state['status'] = 'idle'
                    state['confirmed_date'] = confirmed_date
                    state['current_post_id'] = None
                    print(f"Confirmed date: {confirmed_date}")
                else:
                    print("Still gathering reactions...")
                    
            except discord.NotFound:
                print("Original message not found, resetting status...")
                state['status'] = 'idle'

        # 6. 状態の保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)

        await self.close()

if __name__ == "__main__":
    if not TOKEN:
        print("BOT_TOKEN is missing.")
        sys.exit(1)
        
    intents = discord.Intents.default()
    intents.message_content = True
    intents.reactions = True
    intents.guilds = True
    
    client = MyBot(intents=intents)
    client.run(TOKEN)
