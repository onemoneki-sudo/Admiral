"""A demo fleet: the sessions, commanders, PRs and CI of a made-up shop, built by the real board code, so Admiral can
be seen (and pictured) without running dozens of sessions.

    admiral demo [--lang en|zh] [--tty NAME=ttysNNN ...] [--once]

Everything lives under <state_dir>/demo: its own sessions, transcripts, registrations, plans, locks, config and
board. It rebuilds the board every 20 seconds until stopped (`--once`: build it once and exit). Start Claude Code with
ADMIRAL_CONFIG set to the config it prints, and that session's status line and sidebar show the demo. `--tty` ties a
demo session to a real terminal tab, so a click on its name in the sidebar brings that tab to the front.
"""

import json
import os
import shutil
import time

from . import board, config, registry, sessions

START = "Mon Oct 12 09:00:00 2026"


GREEN = (("lint", "SUCCESS"), ("tests (1)", "SUCCESS"), ("tests (2)", "SUCCESS"), ("browser", "SUCCESS"))
RUNNING = (("lint", "SUCCESS"), ("tests (1)", "SUCCESS"), ("tests (2)", ""), ("browser", ""))


def failing(job):
    return tuple((n, "FAILURE" if n == job else c) for n, c in GREEN)


# One row per session: name, commander, Claude Code status, minutes in it, branch, reported phase (None: registered
# with none; "": not registered), its note, PR (state, review, checks) or None, and the last field: what its last turn
# asks the person, what Claude Code blocks it on (status "waiting"), or WRAPPED when it wrapped up after its PR merged
# (its worktree is gone). Seven commanders (one still planning) run forty sessions; seven more work on their own.
WRAPPED = "wrapped up"
FLEET = [
    ("Commander-Checkout", "", "busy", 1, "", "working", "", None, ""),
    ("Commander-Search", "", "idle", 6, "", "working", "", None, ""),
    ("Commander-Mobile", "", "busy", 0, "", "working", "", None, ""),
    ("Commander-Platform", "", "idle", 3, "", "working", "", None, ""),
    ("Commander-Growth", "", "shell", 2, "", "working", "", None, ""),
    ("Commander-Support", "", "idle", 2, "", "working", "", None, ""),
    ("Commander-Onboarding", "", "idle", 40, "", None, "", None, ""),

    ("Checkout-API", "Commander-Checkout", "busy", 0, "feat/checkout-api", "review", "", ("OPEN", "", RUNNING), ""),
    ("Checkout-UI", "Commander-Checkout", "idle", 3, "feat/checkout-ui", "needs_you",
     "approve the payment provider's sandbox key before the browser re-test", None, ""),
    ("Payments-Gateway", "Commander-Checkout", "busy", 0, "feat/payments-gateway", "working", "", None, ""),
    ("Tax-Rules", "Commander-Checkout", "idle", 20, "feat/tax-rules", "review", "", None, ""),
    ("Refunds", "Commander-Checkout", "idle", 50, "feat/refunds", "done", "", ("MERGED", "APPROVED", GREEN), WRAPPED),
    ("Order-Emails", "Commander-Checkout", "idle", 15, "feat/order-emails", "accepting", "", None, ""),
    ("Checkout-Acceptance", "Commander-Checkout", "shell", 2, "accept/checkout", "accepting", "", None, ""),
    ("Fraud-Signals", "Commander-Checkout", "idle", 8, "feat/fraud-signals", "working", "",
     ("OPEN", "", failing("tests (1)")), ""),

    ("Search-Index", "Commander-Search", "idle", 12, "feat/search-index", "working", "",
     ("OPEN", "CHANGES_REQUESTED", failing("tests (2)")), ""),
    ("Search-Ranking", "Commander-Search", "idle", 4, "feat/search-ranking", "working", "", None,
     "The new scorer ranks 3 of the 20 sample queries worse than the old one. Do you want me to switch to it anyway, "
     "or keep both behind a flag?"),
    ("Search-Suggest", "Commander-Search", "busy", 0, "feat/search-suggest", "working", "", None, ""),
    ("Search-Facets", "Commander-Search", "idle", 30, "feat/search-facets", "review", "", None, ""),
    ("Search-Synonyms", "Commander-Search", "busy", 1, "feat/search-synonyms", "working", "", ("OPEN", "", GREEN), ""),
    ("Search-Docs", "Commander-Search", "idle", 90, "docs/search", "done", "", ("MERGED", "APPROVED", GREEN), ""),
    ("Search-Acceptance", "Commander-Search", "idle", 10, "accept/search", "accepting", "", None, ""),

    ("Mobile-Login", "Commander-Mobile", "busy", 0, "feat/mobile-login", "working", "", ("OPEN", "", RUNNING), ""),
    ("Mobile-Cart", "Commander-Mobile", "idle", 5, "feat/mobile-cart", "needs_you",
     "tap through the new cart on a real phone: the simulator cannot show the payment sheet", None, ""),
    ("Mobile-Push", "Commander-Mobile", "idle", 18, "feat/mobile-push", "review", "", None, ""),
    ("Mobile-Offline", "Commander-Mobile", "busy", 0, "feat/mobile-offline", "working", "", None, ""),
    ("Mobile-Deeplinks", "Commander-Mobile", "idle", 60, "feat/mobile-deeplinks", "done", "",
     ("MERGED", "APPROVED", GREEN), WRAPPED),
    ("Mobile-Accessibility", "Commander-Mobile", "idle", 9, "feat/mobile-a11y", "working", "", None, ""),
    ("Mobile-Release", "Commander-Mobile", "shell", 1, "accept/mobile", "accepting", "", None, ""),

    ("Infra-Queues", "Commander-Platform", "busy", 0, "feat/infra-queues", "working", "", None, ""),
    ("Infra-Cache", "Commander-Platform", "idle", 14, "feat/infra-cache", "working", "", ("OPEN", "APPROVED", GREEN), ""),
    ("Observability", "Commander-Platform", "idle", 22, "feat/observability", "review", "", None, ""),
    ("Rate-Limits", "Commander-Platform", "waiting", 0, "feat/rate-limits", "working", "", None,
     "permission to run: terraform plan -target=module.rate_limits"),
    ("DB-Migrations", "Commander-Platform", "idle", 35, "feat/db-migrations", "done", "",
     ("MERGED", "APPROVED", GREEN), ""),
    ("CI-Speedup", "Commander-Platform", "busy", 1, "chore/ci-speedup", "working", "", ("OPEN", "", RUNNING), ""),
    ("Secrets-Rotation", "Commander-Platform", "idle", 45, "feat/secrets-rotation", "paused",
     "until the new secrets store lands", None, ""),

    ("Referrals", "Commander-Growth", "busy", 0, "feat/referrals", "working", "", None, ""),
    ("Coupons", "Commander-Growth", "idle", 7, "feat/coupons", "working", "", None,
     "Both rules pass the tests. Should a coupon stack with member discounts, or apply only the larger of the two?"),
    ("AB-Testing", "Commander-Growth", "idle", 26, "feat/ab-testing", "working", "", ("OPEN", "", failing("browser")), ""),
    ("Landing-Pages", "Commander-Growth", "idle", 70, "feat/landing-pages", "done", "",
     ("MERGED", "APPROVED", GREEN), WRAPPED),
    ("Email-Campaigns", "Commander-Growth", "shell", 3, "feat/email-campaigns", "working", "", None, ""),
    ("Analytics-Events", "Commander-Growth", "idle", 16, "feat/analytics-events", "review", "", None, ""),

    ("Help-Center", "Commander-Support", "busy", 0, "feat/help-center", "working", "", None, ""),
    ("Live-Chat", "Commander-Support", "idle", 11, "feat/live-chat", "working", "", ("OPEN", "", GREEN), ""),
    ("Returns-Portal", "Commander-Support", "shell", 2, "accept/returns", "accepting", "", None, ""),
    ("Ticket-Routing", "Commander-Support", "busy", 1, "feat/ticket-routing", "working", "", None, ""),
    ("Support-Macros", "Commander-Support", "idle", 19, "feat/support-macros", "review", "", None, ""),

    ("fix-login-timeout", "", "waiting", 1, "fix/login-timeout", "working", "", None,
     "permission to run: npm run migrate -- --env staging"),
    ("bump-dependencies", "", "busy", 0, "chore/bump-deps", "working", "", ("OPEN", "", GREEN), ""),
    ("flaky-test-hunt", "", "idle", 25, "fix/flaky-cart-test", "waiting", "on the CI rerun of its PR",
     ("OPEN", "APPROVED", failing("tests (1)")), ""),
    ("perf-profiling", "", "busy", 0, "chore/perf-profiling", "working", "", None, ""),
    ("docs-refresh", "", "idle", 40, "docs/refresh", "done", "", ("MERGED", "APPROVED", GREEN), WRAPPED),
    ("release-notes", "", "idle", 300, "", "", "", None, ""),
    ("typo-sweep", "", "idle", 26 * 60, "", "", "", None, ""),
]

PLANS = {
    "Commander-Checkout": [("feat/checkout-api", "Checkout API: one call from cart to paid order", "Checkout-API"),
                           ("feat/checkout-ui", "Checkout page with the new payment form", "Checkout-UI"),
                           ("feat/payments-gateway", "A second payment provider", "Payments-Gateway"),
                           ("feat/tax-rules", "Tax by delivery address", "Tax-Rules"),
                           ("feat/refunds", "Refunds from the order page", "Refunds"),
                           ("feat/order-emails", "Order confirmation emails", "Order-Emails"),
                           ("feat/fraud-signals", "Fraud signals at checkout", "Fraud-Signals"),
                           ("feat/gift-cards", "Gift cards", "")],
    "Commander-Mobile": [("feat/mobile-login", "Sign in with the phone's passkey", "Mobile-Login"),
                         ("feat/mobile-cart", "A cart that survives the app closing", "Mobile-Cart"),
                         ("feat/mobile-push", "Order updates by push", "Mobile-Push"),
                         ("feat/mobile-offline", "Browse the catalogue offline", "Mobile-Offline"),
                         ("feat/mobile-deeplinks", "Links that open the app", "Mobile-Deeplinks"),
                         ("feat/mobile-a11y", "Screen-reader pass", "Mobile-Accessibility"),
                         ("feat/mobile-widgets", "Home-screen widgets", "")],
}

LOCKS = {"heavy-gate": "Checkout-Acceptance full gate", "port-8100": "Checkout-Acceptance acceptance server",
         "port-8101": "DB-Migrations migration check"}


# The same fleet in Chinese, named the way Chinese teams name their sessions.
ZH_NAMES = {
    "Commander-Checkout": "总指挥-结账", "Commander-Search": "总指挥-搜索", "Commander-Mobile": "总指挥-移动端",
    "Commander-Platform": "总指挥-平台", "Commander-Growth": "总指挥-增长", "Commander-Support": "总指挥-客服",
    "Commander-Onboarding": "总指挥-新手引导",
    "Checkout-API": "结账-接口", "Checkout-UI": "结账-页面", "Payments-Gateway": "支付网关", "Tax-Rules": "税费规则",
    "Refunds": "退款", "Order-Emails": "订单邮件", "Checkout-Acceptance": "结账-验收", "Fraud-Signals": "风控信号",
    "Search-Index": "搜索-索引", "Search-Ranking": "搜索-排序", "Search-Suggest": "搜索-联想", "Search-Facets": "搜索-筛选",
    "Search-Synonyms": "搜索-同义词", "Search-Docs": "搜索-文档", "Search-Acceptance": "搜索-验收",
    "Mobile-Login": "移动端-登录", "Mobile-Cart": "移动端-购物车", "Mobile-Push": "移动端-推送", "Mobile-Offline": "移动端-离线",
    "Mobile-Deeplinks": "移动端-深链", "Mobile-Accessibility": "移动端-无障碍", "Mobile-Release": "移动端-发版",
    "Infra-Queues": "平台-队列", "Infra-Cache": "平台-缓存", "Observability": "可观测性", "Rate-Limits": "限流",
    "DB-Migrations": "数据库迁移", "CI-Speedup": "CI提速", "Secrets-Rotation": "密钥轮换",
    "Referrals": "推荐返利", "Coupons": "优惠券", "AB-Testing": "AB实验", "Landing-Pages": "落地页",
    "Email-Campaigns": "邮件营销", "Analytics-Events": "埋点",
    "Help-Center": "帮助中心", "Live-Chat": "在线客服", "Returns-Portal": "退货入口", "Ticket-Routing": "工单分派",
    "Support-Macros": "客服话术",
    "fix-login-timeout": "修复-登录超时", "bump-dependencies": "依赖升级", "flaky-test-hunt": "排查-不稳定测试",
    "perf-profiling": "性能分析", "docs-refresh": "文档更新", "release-notes": "发布说明", "typo-sweep": "错别字清理",
}
ZH_TEXT = {
    "approve the payment provider's sandbox key before the browser re-test": "浏览器复测前，请批准支付服务商的沙箱密钥",
    "The new scorer ranks 3 of the 20 sample queries worse than the old one. Do you want me to switch to it anyway, "
    "or keep both behind a flag?": "新的排序算法在 20 个样例查询里有 3 个比旧的差。还要切换过去，还是两个都保留、用开关控制？",
    "tap through the new cart on a real phone: the simulator cannot show the payment sheet":
        "请在真机上点一遍新购物车：模拟器显示不了支付面板",
    "until the new secrets store lands": "等新的密钥存储上线",
    "Both rules pass the tests. Should a coupon stack with member discounts, or apply only the larger of the two?":
        "两种规则都能通过测试。优惠券要和会员折扣叠加，还是只取两者中较大的那个？",
    "on the CI rerun of its PR": "等它的 PR 重跑 CI",
    "Checkout API: one call from cart to paid order": "结账接口：一次调用从购物车到付款完成",
    "Checkout page with the new payment form": "带新支付表单的结账页", "A second payment provider": "接入第二家支付服务商",
    "Tax by delivery address": "按收货地址计税", "Refunds from the order page": "在订单页直接退款",
    "Order confirmation emails": "订单确认邮件", "Fraud signals at checkout": "结账时的风控信号", "Gift cards": "礼品卡",
    "Sign in with the phone's passkey": "用手机通行密钥登录", "A cart that survives the app closing": "关掉应用也不丢的购物车",
    "Order updates by push": "订单进度推送", "Browse the catalogue offline": "离线浏览商品",
    "Links that open the app": "能直接打开应用的链接", "Screen-reader pass": "读屏适配", "Home-screen widgets": "桌面小组件",
    "full gate": "完整门禁", "acceptance server": "验收服务", "migration check": "迁移检查",
}


def localized(language):
    """(fleet, plans, locks, commander prefix) in the board's language."""
    if language != "zh":
        return FLEET, PLANS, LOCKS, "Commander"
    n = lambda x: ZH_NAMES.get(x, x)
    t = lambda x: ZH_TEXT.get(x, x)
    fleet = [(n(name), n(lead), status, mins, branch, phase, t(note), pr_, last if last == WRAPPED or status == "waiting" else t(last))
             for name, lead, status, mins, branch, phase, note, pr_, last in FLEET]
    plans = {n(lead): [(b, t(title), n(owner)) for b, title, owner in items] for lead, items in PLANS.items()}
    locks = {k: " ".join([n(v.split(" ", 1)[0]), t(v.split(" ", 1)[1])]) for k, v in LOCKS.items()}
    return fleet, plans, locks, "总指挥"


def fleet_prs():
    """branch -> PR, numbered in order."""
    out, n = {}, 231
    for row in FLEET:
        if row[7]:
            state, review, checks = row[7]
            out[row[4]] = {"number": n, "headRefName": row[4], "state": state, "isDraft": False,
                           "reviewDecision": review,
                           "statusCheckRollup": [{"name": c, "status": "COMPLETED" if r else "IN_PROGRESS",
                                                  "conclusion": r} for c, r in checks]}
            n += 1
    return out


def paths(root):
    return {k: os.path.join(root, k) for k in ("sessions", "projects", "state", "locks", "repo")}


def write_config(root, language, base, prefix="Commander"):
    p = paths(root)
    text = (f'state_dir = {json.dumps(p["state"])}\nlanguage = "{language}"\n\n[sessions]\n'
            f'dir = {json.dumps(p["sessions"])}\nprojects_dir = {json.dumps(p["projects"])}\n'
            f'project_dirs = [{json.dumps(p["repo"])}]\ncommander_prefix = {json.dumps(prefix)}\n\n'
            f'[github]\nrepo_dir = {json.dumps(p["repo"])}\n\n[locks]\ndir = {json.dumps(p["locks"])}\n\n'
            f'[statusline]\nbase = {json.dumps(base)}\n')
    with open(os.path.join(root, "config.toml"), "w", encoding="utf-8") as fh:
        fh.write(text)
    return os.path.join(root, "config.toml")


def stage(root, now, fleet=FLEET, plans=PLANS, locks=LOCKS):
    """Write the made-up machine: session files, transcripts, registrations, plans and locks."""
    p = paths(root)
    for d in p.values():
        os.makedirs(d, exist_ok=True)
    cfg = config.load(os.path.join(root, "config.toml"))
    for d in (p["sessions"], os.path.join(p["state"], "registry"), os.path.join(p["state"], "batches"), p["locks"]):
        shutil.rmtree(d, ignore_errors=True)  # a fresh fleet every run, nothing left from the last
        os.makedirs(d)
    for pid, (name, lead, status, mins, branch, phase, note, pr_, last) in enumerate(fleet, start=101):
        wrapped = last == WRAPPED
        ask = "" if wrapped or status == "waiting" else last
        waiting = last if status == "waiting" else ""
        d = {"pid": pid, "sessionId": f"demo-{pid}", "name": name, "status": status, "cwd": p["repo"],
             "procStart": START, "statusUpdatedAt": (now - mins * 60) * 1000, "waitingFor": waiting}
        with open(os.path.join(p["sessions"], f"{pid}.json"), "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        t = sessions.transcript(cfg, p["repo"], f"demo-{pid}")
        os.makedirs(os.path.dirname(t), exist_ok=True)
        with open(t, "w", encoding="utf-8") as fh:
            if ask:  # its last turn ended asking the person
                fh.write(json.dumps({"type": "assistant", "message": {
                    "role": "assistant", "content": [{"type": "text", "text": ask}]}}) + "\n")
        if phase != "":  # "" is a session that never registered
            wt = os.path.join(root, "worktrees", branch.replace("/", "-")) if branch else ""
            if wt and not wrapped:
                os.makedirs(wt, exist_ok=True)
            registry.register(cfg, name, task="", branch=branch, worktree=wt, lead=lead)
            if phase:
                registry.set_phase(cfg, name, phase, note)
    for lead, items in plans.items():
        for branch, title, owner in items:
            registry.plan_add(cfg, lead, branch, title, owner)
    for name, who in locks.items():
        os.makedirs(os.path.join(p["locks"], name), exist_ok=True)
        with open(os.path.join(p["locks"], name, "owner"), "w", encoding="utf-8") as fh:
            fh.write(f"who={who}\npid=1\nsince={int(now)}\nttl=180\n")
    return cfg


def build(root, ttys, now=None, fleet=FLEET):
    now = time.time() if now is None else now
    cfg = config.load(os.path.join(root, "config.toml"))
    prs = fleet_prs()
    pids = {pid: row[0] for pid, row in enumerate(fleet, start=101)}
    branches = {os.path.join(root, "worktrees", row[4].replace("/", "-")): row[4] for row in fleet if row[4]}
    snap = board.build(
        cfg, now=now,
        starts=lambda wanted: {pid: (START, ttys.get(pids[pid], "")) for pid in wanted if pid in pids},
        fetch=lambda cfg, wanted: {b: v for b, v in prs.items() if b in wanted},
        fetch_mine=lambda cfg, now: {
            "open": [{"number": v["number"], "headRefName": b} for b, v in prs.items() if v["state"] == "OPEN"],
            "mergedToday": [{"number": v["number"], "headRefName": b} for b, v in prs.items() if v["state"] == "MERGED"]},
        commits=lambda wt: now - 3600 if os.path.isdir(wt) else "gone",
        checked_out=lambda wt: branches.get(wt, ""),
        worktrees=lambda cfg: {})
    board.write(cfg, snap)
    return snap


def run(cfg, language, ttys, once=False):
    root = cfg.sub("demo")
    os.makedirs(root, exist_ok=True)
    fleet, plans, locks, prefix = localized(language)
    demo_cfg = write_config(root, language, cfg.statusline_base, prefix)
    cfg_demo = stage(root, time.time(), fleet, plans, locks)
    build(root, ttys, fleet=fleet)
    # Sessions that wrapped up deregister, as the playbook has them do; the board still knows they finished, from the
    # build above (registration memory).
    for row in fleet:
        if row[8] == WRAPPED:
            registry.done(cfg_demo, row[0])
    build(root, ttys, fleet=fleet)
    print(f"Demo board written. Start Claude Code with:\n\n  ADMIRAL_CONFIG='{demo_cfg}' claude\n\n"
          "and open the sidebar with /admiral." + ("" if once else " Rebuilding every 20 seconds; Ctrl-C stops."))
    while not once:
        time.sleep(20)
        build(root, ttys, fleet=fleet)
