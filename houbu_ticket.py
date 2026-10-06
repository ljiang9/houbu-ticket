#!/usr/bin/env python3
"""houbu_ticket —— 12306 候补购票模拟器（纯娱乐）。

致敬 2026 国庆返程抢票季：直达票售罄，玩家手握 60 个候补名额，
在"日期+车次"组合之间做策略分配，看谁能顺利到家。

郑重声明：本游戏与真实 12306 无任何关联，所有成功率均为虚构数值，
仅供娱乐，不构成任何购票建议。购票请认准官方唯一渠道 12306。
"""
from __future__ import annotations

import argparse
import random
import sys

TOTAL_QUOTA = 60  # 候补名额总数

# 模拟轮次：越往后离发车越近，兑现概率越低；
# 最后一轮为"开车前 20 分钟"，之后候补兑现截止。
ROUNDS = ["10/4 晚间", "10/5 全天", "10/6 白天", "10/6 开车前20分钟·截止"]
DECAY = [1.0, 0.85, 0.6, 0.35]

KIND_WEIGHT = {"direct": 1.0, "transfer": 0.55, "slow": 0.6}


class Combo:
    """一个"日期+车次"候补组合。"""

    def __init__(self, cid, label, kind, depart_round, p, hours, leave, note):
        self.id = cid
        self.label = label
        self.kind = kind            # direct / transfer / slow
        self.depart_round = depart_round  # 该轮次起（含）不再兑现
        self.p = p                # 每名额每轮基础兑现概率（虚构）
        self.hours = hours        # 全程耗时（小时）
        self.leave = leave        # 需要请假天数
        self.note = note


def base_combos():
    return [
        Combo("d6d", "10/6 直达高铁", "direct", 4, 0.035, 4.5, 0,
              "成功率最低，但到家最早、最体面"),
        Combo("d6t", "10/6 中转（合肥换乘）", "transfer", 4, 0.115, 9.0, 0,
              "成功率高，代价是全程站着+屁股开花"),
        Combo("d7d", "10/7 直达高铁", "direct", 4, 0.070, 4.5, 0.5,
              "多请半天假，老板的眼神自己体会"),
        Combo("d5d", "10/5 提前直达", "direct", 2, 0.150, 4.5, 1,
              "成功率最高，代价是一天年假"),
    ]


def extra_train_combo():
    return Combo("d6x", "10/6 加开临客（绿皮）", "slow", 4, 0.090, 11.0, 0,
                 "铁路加开的爱：慢，但稳")


def slot_p(combo, round_idx):
    """某组合在某轮次、单个名额的兑现概率；发车后/截止后为 0。"""
    if round_idx >= combo.depart_round or round_idx >= len(ROUNDS):
        return 0.0
    return combo.p * DECAY[round_idx]


class IllegalMove(Exception):
    pass


def validate_alloc(combos, alloc):
    """校验分配：名额总数必须恰为 60，不允许负数与未知组合。"""
    ids = {c.id for c in combos}
    for cid in alloc:
        if cid not in ids:
            raise IllegalMove(f"未知组合：{cid}")
        if alloc[cid] < 0:
            raise IllegalMove(f"组合 {cid} 名额不能为负数")
    total = sum(alloc.values())
    if total != TOTAL_QUOTA:
        raise IllegalMove(f"候补名额总数必须为 {TOTAL_QUOTA}，当前为 {total}")


def ai_allocate(combos):
    """AI 按期望效用分配 60 个名额（确定性规则）。"""
    utils = []
    for c in combos:
        ev = sum(slot_p(c, r) for r in range(len(ROUNDS)))
        w = KIND_WEIGHT[c.kind]
        if c.leave:
            w *= (1 - 0.2 * c.leave)
        utils.append(ev * w)
    total = sum(utils)
    alloc = {}
    acc = 0
    for i, c in enumerate(combos):
        if i == len(combos) - 1:
            alloc[c.id] = TOTAL_QUOTA - acc
        else:
            n = int(TOTAL_QUOTA * utils[i] / total)
            alloc[c.id] = n
            acc += n
    return alloc


class Result:
    def __init__(self):
        self.won = False
        self.combo = None
        self.win_round = None
        self.flagged = False   # 点了黄牛链接
        self.log = []


def run_game(alloc, seed=None, verbose=False, auto=True, decide=None):
    """跑一局完整模拟。decide: 黄牛私信时的决策函数，返回 True=接受/False=拒绝。"""
    rng = random.Random(seed)
    combos = base_combos()
    validate_alloc(combos, alloc)
    # 每个名额是一张候补单
    orders = [{"combo": c, "done": False} for c in combos for _ in range(alloc.get(c.id, 0))]
    res = Result()

    def say(msg):
        res.log.append(msg)
        if verbose:
            print(msg)

    say(f"候补开始：共 {TOTAL_QUOTA} 个名额已分配，目标 10/6 武汉→上海返程。")
    for cid, n in alloc.items():
        if n:
            label = next(c.label for c in combos if c.id == cid)
            say(f"  {label}：{n} 个名额")

    for r, rname in enumerate(ROUNDS):
        if res.won or res.flagged:
            break
        say(f"\n【{rname}】")
        # --- 随机事件 ---
        if r == 2 and rng.random() < 0.40:
            xc = extra_train_combo()
            combos.append(xc)
            for _ in range(6):
                orders.append({"combo": xc, "done": False})
            say("🚂 铁路加开临客！新增组合「10/6 加开临客（绿皮）」，附赠 6 个名额。")
        if r in (1, 2) and rng.random() < 0.30 and not res.won:
            cand = [o for o in orders if not o["done"]]
            if cand:
                o = rng.choice(cand)
                o["done"] = True
                res.won, res.combo, res.win_round = True, o["combo"], r
                say(f"📱 凌晨 3 点短信把你吵醒：「{o['combo'].label} 候补成功！」——被吵醒也值了。")
                break
        if r in (0, 1, 2) and rng.random() < 0.25 and not res.won:
            say("⚠️ 收到黄牛私信：「内部票，微信转账，先款后票」——")
            accept = decide() if decide else False
            if auto and decide is None:
                accept = False
            if accept:
                res.flagged = True
                orders.clear()
                say("❌ 你点了黄牛链接：钱没了，票没有，账号还被风控了。")
                say("📢 普法：购票认准官方唯一渠道 12306，任何「内部票」都是骗局！")
                break
            say("✅ 果断拒绝并举报。记住：官方唯一渠道只有 12306。")
        # --- 本轮兑现掷骰 ---
        if res.won or res.flagged:
            break
        hits = 0
        for o in orders:
            if o["done"]:
                continue
            if rng.random() < slot_p(o["combo"], r):
                o["done"] = True
                hits += 1
                res.won, res.combo, res.win_round = True, o["combo"], r
                break  # 首个兑现即锁定本局结果
        if res.won:
            say(f"🎉 兑现成功！「{res.combo.label}」候补到了，全程约 {res.combo.hours} 小时。")
        elif hits == 0:
            say("本轮无事发生，候补大军继续排队……")
    return res


TITLES = {
    "king": ("候补之王", "10/6 直达一次上岸！建议去买彩票，但别上头——下次记得提前 15 天。"),
    "warrior": ("绿皮车战神", "虽然慢/虽然折腾，但你到家了。真正的战神从不抱怨座位。"),
    "leave": ("请假跑路达人", "用年假换车票，成年人不做选择题——只是老板的白眼也是成本。"),
    "late": ("晚到也是到", "10/7 才到家，工位上的绿萝替你扛了一天。"),
    "stuck": ("滞留武汉", "票没抢到，人还在武汉。热干面再来一碗，明天继续战斗。"),
    "banned": ("滞留武汉·账号风险警告", "黄牛的票是假的，教训是真的。记住：官方唯一渠道 12306！"),
}


def settle(res):
    """结算称号与评语。"""
    if res.flagged:
        key = "banned"
    elif not res.won:
        key = "stuck"
    else:
        c = res.combo
        if c.id == "d6d":
            key = "king"
        elif c.kind in ("transfer", "slow"):
            key = "warrior"
        elif c.leave >= 1:
            key = "leave"
        elif c.id == "d7d":
            key = "late"
        else:
            key = "warrior"
    title, comment = TITLES[key]
    detail = ""
    if res.won:
        detail = (f"抢到「{res.combo.label}」，{ROUNDS[res.win_round]}兑现，"
                  f"全程约 {res.combo.hours} 小时，请假 {res.combo.leave} 天。")
    return title, comment, detail


def interactive_alloc(combos):
    alloc = {}
    print(f"\n你有 {TOTAL_QUOTA} 个候补名额，请分配到以下组合（输入数字，总和须为 60）：")
    for c in combos:
        print(f"  {c.id}：{c.label}（单名额基础概率约 {c.p:.1%}，{c.note}）")
    for c in combos:
        while True:
            try:
                n = int(input(f"{c.id} 分配几个？ ").strip())
            except ValueError:
                print("请输入整数。")
                continue
            if n < 0:
                print("不能为负数。")
                continue
            alloc[c.id] = n
            break
    validate_alloc(combos, alloc)
    return alloc


def main(argv=None):
    ap = argparse.ArgumentParser(description="12306 候补购票模拟器（纯娱乐）")
    ap.add_argument("--auto", action="store_true", help="AI 自动分配并游玩")
    ap.add_argument("--games", type=int, default=1, help="自动游玩局数")
    ap.add_argument("--seed", type=int, default=None, help="随机种子")
    ap.add_argument("--verbose", action="store_true", help="打印每日兑现战报")
    args = ap.parse_args(argv)

    if args.games < 1:
        print("games 必须 >= 1", file=sys.stderr)
        return 2

    if args.auto:
        from collections import Counter
        cnt = Counter()
        for i in range(args.games):
            seed = None if args.seed is None else args.seed + i
            alloc = ai_allocate(base_combos())
            res = run_game(alloc, seed=seed, verbose=args.verbose, auto=True)
            title, comment, detail = settle(res)
            cnt[title] += 1
            if args.verbose or args.games == 1:
                print(f"\n第 {i+1} 局结算：{title}\n  {detail}\n  {comment}")
        if args.games > 1:
            print(f"\n共 {args.games} 局，称号分布：")
            for t, n in cnt.most_common():
                print(f"  {t}：{n} 局")
        return 0

    if not sys.stdin.isatty():
        print("交互模式需要终端输入；请用 --auto 自动游玩。", file=sys.stderr)
        return 2
    alloc = interactive_alloc(base_combos())

    def decide():
        while True:
            a = input("黄牛说「先款后票」，你接受吗？(y/N) ").strip().lower()
            if a in ("y", "yes"):
                return True
            if a in ("n", "no", ""):
                return False
            print("请输入 y 或 n。")

    res = run_game(alloc, verbose=True, auto=False, decide=decide)
    title, comment, detail = settle(res)
    print(f"\n结算：{title}\n  {detail}\n  {comment}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
