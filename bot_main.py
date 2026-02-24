import discord
import os
import json
import random
from datetime import datetime, timedelta, timezone

# 設定
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
CHANNEL_ID_STR = os.getenv('DISCORD_CHANNEL_ID')
CHANNEL_ID = int(CHANNEL_ID_STR) if CHANNEL_ID_STR and CHANNEL_ID_STR.isdigit() else 0
STATE_FILE = 'state.json'
TARGET_CHANNEL_NAME = "零式消化日程"
EMOJIS = ["🇦", "🇧", "🇨", "🇩", "🇪", "🇫", "🇬"]
JST = timezone(timedelta(hours=9))

# リマインドメッセージのバリエーション
MESSAGES_DAY_BEFORE = [
    "**【準備推奨】** 明日 **{date} 21:00〜** 消化です！最新のご飯と薬の在庫チェックを忘れずに。鞄の空きも確保しておきましょう！",
    "**【マクロ確認】** 明日 **{date}** はレイド日です。散開図、脳内シミュレーションできていますか？イメトレを制する者が消化を制します。",
    "**【装備点検】** 冒険者ギルドからのお知らせ：明日 **{date} 21:00** より作戦開始。ダークマターの用意は十分ですか？壊れた装備で挑むのは禁物です。",
    "**【体調管理】** 明日は **{date} 21:00** から本番。今日は早めにログアウトして「休息（レストボーナス）」をしっかり取ってくださいね。",
    "**【生存戦略】** 予習復習はお済みですか？明日 **{date}**、死なないことが最大のDPS貢献です。ギミック確認をもう一度！",
    "**【気合注入】** 輝ける勝利のために。明日 **{date} 21:00**、戦いの火蓋が切られます。全力で振り抜く準備をしておいてください。",
    "**【最終通告】** 明日は **{date}**。予定の重複はありませんか？エオルゼアの平和（と装備の獲得）のために集結をお願いします。",
    "**【ロット運祈願】** 明日 **{date} 21:00〜**！ロットで「99」を出す準備はできていますか？徳を積んで待ちましょう。",
    "**【忘れ物チェック】** 飯？ヨシ。薬？ヨシ。マクロ？ヨシ。明日 **{date} 21:00**、現地（またはVC）でお会いしましょう。",
    "**【予兆検知】** 私のセンサーが明日の勝利を予兆しています。**{date} 21:00**、最高のチームワークで駆け抜けましょう！"
]

MESSAGES_DAY_OF = [
    "**【今夜 21:00〜】** コンテンツ開始まであと少し！ログインと修理、エモートの準備も万全に！",
    "**【シャキ待ち準備】** 本日の消化は **21:00** 開始です。「シャキーン！」と開始できるよう、早めのログインとお風呂を！",
    "**【食事効果】** 今夜は本番！メニュー（食事）は決めましたか？HQ品を食べてステータスを底上げしておきましょう。",
    "**【最終チェック】** 21:00に向けてカウントダウン。ジョブチェンジ、アクション配置、心構え、すべて整っていますか？",
    "**【戦士の休息】** 今夜 21:00 から戦闘開始。今のうちにリアルでの用事を済ませて、集中モードへ！",
    "**【ロット神の加護】** 今夜 **21:00〜**！箱の中身はあなたのもの（かもしれません）。戦場でお会いしましょう。",
    "**【接続確認】** ネット回線の調子はどうですか？ラグは最大の敵です。環境を整えてお待ちください。",
    "**【マクロ流します】** 今夜 21:00 開始です！「あ、あのギミックなんだっけ？」と思ったら今のうちに動画をチラ見！",
    "**【勝利の予感】** さあ、消化の時間まであと数時間。最高のパフォーマンスを期待しています！",
    "**【全集中】** 今夜の消化はサクッと終わらせて、みんなで勝利の余韻に浸りましょう。21:00集合です！"
]

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
        force_cancel = False
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
            elif content == "!cancel":
                if state['status'] == 'confirmed':
                    force_cancel = True
                try: await msg.delete()
                except: pass

        # --- 5. メインロジック ---
        weekday = now_jst.weekday()
        hour = now_jst.hour
        current_week = now_jst.isocalendar()[1]

        # A. 募集開始
        # 条件: 金曜21時以降かつ今週まだ募集していない場合（gathering残存時も上書き）、または !post 強制実行
        is_scheduled_start = (weekday == 4 and hour >= 21 and state.get('last_recruited_week') != current_week)
        
        if is_scheduled_start or force_post or force_cancel:
            if force_cancel:
                state['dates'] = get_next_week_dates()
                await channel.send("@everyone\n**【日程再調整】** 急用等により日程をキャンセルしました。再度候補日を選択してください。")
            else:
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
            state['confirmed_date'] = None
            if not force_cancel:
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

                # 8人揃ったら確定
                winner = next((s for s in scores if s['count'] >= 8), None)
                if winner:
                    top3 = sorted(scores, key=lambda x: x['count'], reverse=True)[:3]
                    msg = f"@everyone\n**【日程確定】**\n✅ **{winner['date']} 21:00～** に決定しました！\n\n"
                    msg += "📊 **上位3候補:**\n"
                    rank_labels = ["🥇", "🥈", "🥉"]
                    for i, s in enumerate(top3[:3]):
                        label = "← 確定" if s['date'] == winner['date'] else ""
                        msg += f"{rank_labels[i]} {s['date']} ({s['count']}人) {label}\n"
                    msg += "\n急用等で不可になった場合は `!cancel` と打てば再調整します。"
                    
                    await channel.send(msg)
                    state['status'] = 'confirmed'
                    state['current_post_id'] = None
                    state['confirmed_date'] = winner['date']  # 例: "02/24(火)"
                    state['reminded_day_before'] = False
                    state['reminded_day_of'] = False
                
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

        # C. 構成入り楽曲 確定日のリマインド
        elif state['status'] == 'confirmed' and state.get('confirmed_date'):
            try:
                # "02/24(火)" → 日付オブジェクトに変換
                date_str = state['confirmed_date'].split('(')[0]  # "02/24"
                current_year = now_jst.year
                confirmed_dt = datetime.strptime(f"{current_year}/{date_str}", "%Y/%m/%d").replace(tzinfo=JST)

                # 【業務終了】本番翻日の翻日以降 → idleへ戻す
                if now_jst >= confirmed_dt + timedelta(days=1):
                    state['status'] = 'idle'
                    state['confirmed_date'] = None

                # 【前日リマインド】前日 21時以降
                elif now_jst.date() == (confirmed_dt - timedelta(days=1)).date() and (hour >= 21 or force_remind) and not state.get('reminded_day_before'):
                    msg_template = random.choice(MESSAGES_DAY_BEFORE)
                    await channel.send(f"@everyone {msg_template.format(date=state['confirmed_date'])}")
                    state['reminded_day_before'] = True

                # 【当日リマインド】当日 18時以降
                elif now_jst.date() == confirmed_dt.date() and (hour >= 18 or force_remind) and not state.get('reminded_day_of'):
                    msg_template = random.choice(MESSAGES_DAY_OF)
                    await channel.send(f"@everyone {msg_template}")
                    state['reminded_day_of'] = True

            except Exception as e:
                print(f"Reminder error: {e}")

        # 状態保存
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
        
        await self.close()

if __name__ == "__main__":
    intents = discord.Intents.default()
    intents.message_content = True
    client = MyBot(intents=intents)
    client.run(TOKEN)
