import discord
import os
import json
from datetime import datetime, timedelta, timezone

# 設定
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID_STR = os.getenv('DISCORD_CHANNEL_ID')
CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR and CHANNEL_ID_STR.isdigit() else 0
STATE_FILE = 'state.json'
TARGET_CHANNEL_NAME = "零式消化日程"
EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬"]
JST = timezone(timedelta(hours=9))

def get_now_jst():
    return datetime.now(timezone.utc).astimezone(JST)

def get_next_week_dates():
    now = get_now_jst()
    # 次の火曜日を探す
    days_until_tuesday = (1 - now.weekday() + 7) % 7
    if days_until_tuesday == 0: days_until_tuesday = 7
    next_tuesday = now + timedelta(days=days_until_tuesday)
    dates = []
    for i in range(7):
        current = next_tuesday + timedelta(days=i)
        dates.append(current.strftime("%m/%d") + "(" + ["月","火","水","木","金","土","日"][current.weekday()] + ")")
    return dates

class MyBot(discord.Client):
    async def on_ready(self):
        print(f'Logged in as {self.user}')
        now_jst = get_now_jst()

        # --- 1. チャンネルの特定/作成 ---
        channel = self.get_channel(CHANNEL_ID) if CHANNEL_ID > 0 else None
        if not channel:
            for guild in self.guilds:
                channel = discord.utils.get(guild.text_channels, name=TARGET_CHANNEL_NAME)
                if channel: break
        if not channel:
            for guild in self.guilds:
                try:
                    channel = await guild.create_text_channel(TARGET_CHANNEL_NAME)
                    break
                except: continue

        if not channel:
            await self.close()
            return

        # --- 2. 状態の読み込みと自動メンテナンス ---
        if not os.path.exists(STATE_FILE):
            state = {"status": "idle", "current_post_id": None, "welcomed": False, "last_recruited_week": -1}
        else:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                state = json.load(f)

        # 【ロジック修正】期限切れの募集を自動終了させる
        if state['status'] == 'gathering' and state.get('dates'):
            try:
                # 募集期間の最終日（月曜日）の翌日火曜0時を過ぎていたら終了
                last_date_str = state['dates'][-1].split('(')[0] # "02/23"
                current_year = now_jst.year
                expire_date = datetime.strptime(f"{current_year}/{last_date_str}", "%Y/%m/%d").replace(tzinfo=JST) + timedelta(days=1)
                
                if now_jst >= expire_date:
                    print(f"Closing expired recruitment from {last_date_str}")
                    state['status'] = 'idle'
                    state['current_post_id'] = None
            except Exception as e:
                print(f"Failed to check expiration: {e}")

        # --- 3. 挨拶投稿 ---
        if not state.get('welcomed', False):
            welcome_msg = f"## 🤖 零式消化日程ボット 稼働中\n"
            welcome_msg += "スケジュール管理と募集を自動化します。コマンドは読み取り後に削除されます。"
            await channel.send(welcome_msg)
            state['welcomed'] = True

        # --- 4. コマンド確認 (精度の向上) ---
        force_post = False
        force_remind = False
        async for msg in channel.history(limit=30):
            if msg.author.bot: continue
            
            content = msg.content.strip()
            if content == "!reset":
                state['status'] = 'idle'
                state['current_post_id'] = None
                try: await msg.delete()
                except: pass
            elif content == "!post":
                if state['status'] == 'idle':
                    force_post = True
                try: await msg.delete()
                except: pass
            elif content == "!remind":
                force_remind = True
                try: await msg.delete()
                except: pass

        # --- 5. メインロジック ---
        weekday = now_jst.weekday()
        hour = now_jst.hour
        current_week = now_jst.isocalendar()[1]

        # A. 募集開始 (金曜21時以降 かつ 今週まだ募集していない場合)
        is_scheduled_start = (weekday == 4 and hour >= 21 and state.get('last_recruited_week') != current_week)
        
        if (state['status'] == 'idle' and is_scheduled_start) or force_post:
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
            state['last_recruited_week'] = current_week

        # B. 集計・催促
        elif state['status'] == 'gathering' and state['current_post_id']:
            try:
                message = await channel.fetch_message(state['current_post_id'])
                scores = []
                responded_users = set()
                
                for i, emoji in enumerate(EMOJIS):
                    reaction = discord.utils.get(message.reactions, emoji=emoji)
                    
                    # 【精度向上】ユーザーIDを直接取得してボットを除外してカウント
                    u_list = []
                    if reaction:
                        async for u in reaction.users():
                            if not u.bot: 
                                u_list.append(u.display_name)
                                responded_users.add(u.display_name)
                    
                    scores.append({"date": state['dates'][i], "count": len(u_list)})

                # 8人揃ったら決定
                winner = next((s for s in scores if s['count'] >= 8), None)
                if winner:
                    await channel.send(f"@everyone\n**【日程確定】**\n✅ **{winner['date']} 21:00〜** に決定しました！")
                    state['status'] = 'idle'
                    state['current_post_id'] = None
                
                # 催促判定 (月曜19時 または 強制実行)
                else:
                    is_remind_time = (weekday == 0 and 19 <= hour < 20 and state.get('last_reminded_at') != now_jst.strftime("%Y-%m-%d"))
                    if is_remind_time or force_remind:
                        top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                        u_names = "、".join(responded_users) if responded_users else "なし"
                        rem_msg = f"@everyone **【日程回答状況】**\n✅ **入力済み**: {u_names}\n📊 **有力候補**:\n"
                        for s in top3: rem_msg += f"- {s['date']} ({s['count']}人)\n"
                        await channel.send(rem_msg)
                        state['last_reminded_at'] = now_jst.strftime("%Y-%m-%d")
            except Exception as e:
                print(f"Error: {e}")
                if "404" in str(e): state['status'] = 'idle' # メッセージ削除済み時

        # 状態保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        
        await self.close()

if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    client = MyBot(intents=intents)
    client.run(TOKEN)
