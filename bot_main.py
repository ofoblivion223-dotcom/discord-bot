import discord
import json
import os
import sys
from datetime import datetime, timedelta
# 設定の読み込み (GitHub Secrets から環境変数として渡される想定)
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID')) if os.getenv('DISCORD_CHANNEL_ID') else 0
STATE_FILE = 'state.json'
EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬"]
def get_next_week_dates():
    # 今日（実行日）を基準に、一番近い「次の火曜日」を計算する
    today = datetime.now()
    # 0=月, 1=火, 2=水, ... 6=日
    # 次の火曜日までの日数を計算
    days_until_tuesday = (1 - today.weekday() + 7) % 7
    
    # もし今日が火曜日なら、来週の火曜日にしたい場合は timedelta(days=7) を足す
    # 基本的には日曜に動く想定なので、そのまま足せば火曜になります
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
            # IDで見つからない場合、参加しているサーバーから "general" という名前を探す
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name="general")
                if channel:
                    break
        if not channel:
            print("Channel not found. (#generalも見つかりませんでした)")
            await self.close()
            return
            
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            state = json.load(f)
        now = datetime.now()
        
        # 1. 募集投稿 (日曜日 12:00〜13:00 に実行された場合、かつステータスが idle の場合)
        if state['status'] == 'idle':
            state['count'] += 1
            dates = get_next_week_dates()
            content = f"**【零式消化{state['count']}】今週の予定を確認します**\n"
            content += "全員（8人）揃った日に自動決定します（21:00〜）\n\n"
            for i, d in enumerate(dates):
                content += f"{EMOJIS[i]} : {d}\n"
            
            message = await channel.send(content)
            for emoji in EMOJIS:
                await message.add_reaction(emoji)
            
            state['current_post_id'] = message.id
            state['status'] = 'gathering'
            state['dates'] = dates
            print("Posted new gathering message.")
        # 2. 自動集計と判定
        elif state['status'] == 'gathering' and state['current_post_id']:
            try:
                message = await channel.fetch_message(state['current_post_id'])
                selected_index = -1
                
                for i, emoji in enumerate(EMOJIS):
                    reaction = discord.utils.get(message.reactions, emoji=emoji)
                    if reaction:
                        # Bot自身のリアクションを除いて 8人以上
                        if reaction.count - 1 >= 8:
                            selected_index = i
                            break # 最初に見つかった（早い日程）で決定
                
                if selected_index != -1:
                    confirmed_date = state['dates'][selected_index]
                    announcement = f"**【日程確定】零式消化{state['count']}**\n"
                    announcement += f"✅ **{confirmed_date} 21:00〜** に決定しました！\n"
                    announcement += "よろしくお願いします。"
                    await channel.send(announcement)
                    
                    state['status'] = 'idle' # 確定したので次の日曜まで待機
                    state['confirmed_date'] = confirmed_date
                    state['current_post_id'] = None
                    print(f"Confirmed date: {confirmed_date}")
                else:
                    print("Still gathering... No date has 8 reactions yet.")
                    
            except discord.NotFound:
                print("Gathering message was deleted.")
                state['status'] = 'idle'
        # 状態の保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        await self.close()
if __name__ == "__main__":
    if not TOKEN or not CHANNEL_ID:
        print("Missing environment variables.")
        sys.exit(1)
        
    intents = discord.Intents.default()
    intents.members = True # リアクションカウントのため
    intents.reactions = True
    intents.message_content = True
    
    client = MyBot(intents=intents)
    client.run(TOKEN)
