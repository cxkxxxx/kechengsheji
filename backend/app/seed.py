# -*- coding: utf-8 -*-
"""
Mock 数据种子脚本
生成：攻略文章、社区帖子、评论、羊毛活动、价格历史、账单、测试用户
运行：python -m app.seed  （在 backend 目录下）
"""
import random
import datetime
import calendar
from app.core.database import SessionLocal
from app.models.article import Article
from app.models.post import Post
from app.models.comment import Comment
from app.models.coupon_activity import CouponActivity
from app.models.price_history import PriceHistory
from app.models.bill import Bill
from app.models.user import User

# ---------- 标题/内容素材 ----------
article_data = [
    ("上班族一周省钱午餐计划，同事都以为我在瘦身", "餐饮", [
        "早上在家做三明治，成本不到3块，比外面10块的干净又省钱。",
        "周末集中采购一周食材，规划好每天的菜谱，避免晚上冲动点外卖。",
        "带上保温饭盒，把昨晚的剩菜热一热就是一顿健康午餐。",
        "记住这个公式：晚上做饭多做一份，第二天午餐 = 额外成本几乎为0。",
        "小技巧：周末炖一锅汤，分装冷冻，工作日随时热一碗配饭。",
    ]),
    ("超市打折日记：我总结的『周三定律』", "羊毛", [
        "大超市的生鲜通常在周三上午补货，临期品打折力度最大。",
        "晚8点后去超市买烘焙、熟食，经常能捡到半价。",
        "关注会员日：很多超市会员日全场85折，叠加优惠券更划算。",
        "不要在家饿着逛超市，饿的时候买的东西最贵。",
        "结账前再清一遍购物车，去掉那些'好像用得到'的东西。",
    ]),
    ("学生党200元过一周，三餐怎么安排", "餐饮", [
        "早餐：燕麦+牛奶，2元搞定，比食堂包子还省。",
        "午餐：食堂打一荤两素，控制在8元内，别加烤肉。",
        "晚餐：一荤一蔬菜汤，批发市场买鸡蛋西红柿，划算。",
        "零食：水果买当季的丑苹果、香蕉，比进口果便宜一半。",
        "宿舍备一个小电锅，煮面煮蛋成本极低，还能控糖控油。",
    ]),
    ("网购比价诀窍：同一件商品省钱30%的手法", "购物", [
        "先搜再买：把商品名后面加'旗舰店''官方店'对比。",
        "用比价工具看历史价格曲线，别在发条节假日前夕剁手。",
        "跨平台比价：同款在天猫、京东、拼多多价格可能差很多。",
        "关注返利，下单前领隐藏优惠券，通常能再省5-15%。",
        "不急用的东西加入购物车放3天，80%的冲动消费会自己消失。",
    ]),
    ("衣柜断舍离后，我一个月只花了300买衣服", "生活", [
        "给每件衣服标成本价核算，穿一次多少钱，一眼看出性价比。",
        "基础款买优衣库打折季，一次囤齐，避免日常冲动买。",
        "衣柜每季度整理一次，把'想穿但不敢穿'的捐掉。",
        "网购前想清楚：它能不能搭我现有的3套衣服？",
        "颜色统一黑白灰咖，搭配零成本，省下搭配纠结的时间。",
    ]),
    ("手机话费套餐怎么选最省，三大运营商套路拆解", "羊毛", [
        "先查自己的实际用量：流量、通话各用多少，再对号入座。",
        "携号转网可以谈：老用户转网经常能拿到更大折扣。",
        "流量大户别买天价流量包，看看宽带融合套餐更划算。",
        "家人合办家庭套餐，人均成本能降一半以上。",
        "每个月月底查剩余流量，养成不浪费的习惯。",
    ]),
    ("家电『功耗刺客』排查，每个月电费省一半", "生活", [
        "待机功耗是隐形杀手：电视、路由器、充电器不拔一年也费不少。",
        "热水器别常开，用前1小时再开，节能又安全。",
        "空调温度26度，配合风扇使用，体感一样凉快。",
        "冰箱别塞太满，七成满最省电，食物也更新鲜。",
        "洗衣机选节能模式，太阳能热水普及的地区更省。",
    ]),
    ("奶茶自由怎么实现：一个月喝25杯只花80块", "餐饮", [
        "自己做：买茶叶+纯奶+糖浆，一杯成本不到3块。",
        "薅新客券：各平台首单券，7天一个号轮着用。",
        "周三五折日：很多品牌周三有半价活动，攒着这天喝。",
        "别加料：珍珠、奶盖、鲜奶都是溢价，纯茶最划算。",
        "自带杯：部分连锁自带杯减2-3元，一年能省不少。",
    ]),
    ("旅行省钱攻略：穷游也能玩得高质量", "生活", [
        "淡季出行：避开节假日，机票酒店能便宜一半。",
        "机票提前2-3周订，周二周三往往最便宜。",
        "住青旅或民宿比酒店省一半，还能认识朋友。",
        "当地公共交通+步行，比打车更能体会城市。",
        "景区联票比单买划算，提前网上订有折扣。",
    ]),
    ("薅羊毛注意：这些『免费』其实是陷阱", "羊毛", [
        "免费试用要填银行信息的一律拒绝，可能是诈骗。",
        "关注来源真实的大平台活动，别点陌生人发的小程序链接。",
        "拼团砍价大多耗时间换小利，算算时间成本。",
        "个人信息不能白给：下载APP前看看要什么权限。",
        "真正的羊毛：大平台会员日、银行立减金，别碰灰产。",
    ]),
    ("外卖控重生记：告别月月超支的4个方法", "餐饮", [
        "设置每日外卖预算上限，超了就自己做。",
        "用优惠券平台先领券再下单，别直接打开外卖APP。",
        "拼单凑满减：和同事拼一单，人均更便宜。",
        "会员外卖月卡：经常点就买，不常点别买。",
        "把'点外卖'延迟20分钟决策，很大概率会取消。",
    ]),
    ("二手平台的省钱学：捡漏高手的5个判断", "购物", [
        "大宗家具、体育器材、刚需小家电，二手性价比最高。",
        "看卖家的信用和评价，警惕价格低得离谱的。",
        "同城自提最稳妥，还能线下验货。",
        "关键词搜'全新未拆''卖家闲置'，能捡到好物。",
        "电子产品认准官方保修期内的，出问题能维权。",
    ]),
    ("水电煤合并缴费，一次操作锁全年优惠", "生活", [
        "支付宝/微信生活缴费常有立减活动，先领券再缴。",
        "银行APP缴纳水电煤，经常有随机立减金。",
        "开通自动缴费免单笔手续费，还能提醒余额不足。",
        "年底错峰缴费，避免缴费高峰排长队。",
        "单位缴公积金/社保的，留意单位周边的补贴政策。",
    ]),
    ("健身房卡别冲动了！去健身房前先算笔账", "生活", [
        "先试课一周，确定真能坚持再办卡。",
        "买次卡/月卡别买年卡，避免跑路和浪费。",
        "离家近是硬道理：超过15分钟路程基本坚持不了。",
        "尊巴/瑜伽/Keep 在家也能练，年卡钱能省一大笔。",
        "关注新店开业优惠，比老店续费便宜。",
    ]),
]

post_data = [
    ("我靠带饭一年省了8000", "预算就500/月，坚持带饭一年，真香。每天省25，一年就是9000多。关键是学会做大份菜分装。", "带饭,省钱"),
    ("薅到一个0元洗车", "新用户活动，终于用到一次免费洗车，记录一下，大家别错过平台首单券。", "羊毛,洗车"),
    ("拼多多的3元纸巾到手，质量竟然不错", "抱着试试的心态，结果真香，蹲活动买日用品很划算。", "拼多多,日用品"),
    ("记账半年，我发现我花得最多的是奶茶", "认真记账之后被自己吓到了，一个月奶茶400+。现在戒了，改用自制。", "记账,奶茶"),
    ("毕业租房攻略分享", "别租太贵新盘，老实看老小区步梯，房子可能旧点但租金差一半。关键看位置和安全性。", "租房,应届生"),
    ("周三超市买水果真香", "验证了网上的说法，周三晚去大超市，水果临期折扣能省不少。", "超市,水果"),
    ("养宠物的省钱小技巧", "猫粮用好一点的但量控制好，猫砂买大包装回回样。别买一堆玩具，猫更爱纸箱。", "宠物,养猫"),
    ("我戒掉了外卖，体重和钱都降了", "自制三餐两个月，体重轻了5斤，花销省了一半。真是三赢了。", "健康,外卖"),
    ("淘宝大促怎么买最划算", "先加购物车不急着买，等大促前找客服领券，再叠加跨店满减。", "淘宝,大促"),
    ("话费每月控制在30块的办法", "关掉不用的套餐，用流量包叠加，选个便宜的流量卡。", "话费,通讯"),
    ("闲置出二手回血了800", "把不用的相机、耳机挂闲鱼，一周回血800，家里清爽多了。", "闲鱼,回血"),
    ("冬天取暖省钱", "电热毯+厚被子比开空调省电多，还暖和。", "居家,取暖"),
]

comment_data = [
    "这也太实用了吧，收藏了！",
    "亲测有效，谢谢楼主分享~",
    "学到了，这就去试",
    "说的太对了，我之前也是乱买",
    "楼主好会过日子！",
    "支持下，干货满满",
    "这个思路不错，回头也试试",
    "哈哈哈我也是这样做的",
    "求更新，想看更多合集",
    "太真实了，我踩过同样的坑",
]

coupon_data = [
    ("XX银行周三满100减20", "本月每周三使用XX银行卡支付满100立减20，上限20元", "银行"),
    ("美团外卖新客立减15", "首次下单立减15元，限商家满30可用", "外卖"),
    ("支付宝话费充值95折", "充值话费满50元享95折，每月限一次", "话费"),
    ("京东PLUS新人礼", "新会员领20元无门槛券，全场可用", "电商"),
    ("瑞幸咖啡买一送一券", "周一到店自取享买一送一，限本周", "咖啡"),
    ("拼多多百亿补贴_数码", "数码家电专场，部分商品直降50%", "电商"),
    ("电信青年卡29元起", "29元含65G流量+100分钟通话，新办用户专享", "话费"),
    ("屈臣氏会员日8折", "每月10号会员日，任意商品8折（特价除外）", "零售"),
]

price_hist = [
    ("石头扫地机器人T8", 1299, "京东"), ("云鲸扫拖一体机J3", 2799, "天猫"),
    ("iPhone 15 128G", 5999, "京东"), ("小米手环8 Pro", 369, "拼多多"),
    ("AirPods Pro 2", 1499, "京东"), ("美的空调1.5匹", 2199, "天猫"),
    ("戴森吹风机", 2590, "得物"), ("九阳破壁机", 349, "淘宝"),
]


def seed():
    db = SessionLocal()
    try:
        # 清空已有数据（可选，首次直接跳过）
        # 1. 测试用户
        users = []
        for i in range(5):
            u = db.query(User).filter(User.nickname == f"省钱达人{i+1}").first()
            if not u:
                u = User(
                    nickname=f"省钱达人{i+1}",
                    total_saved=random.randint(200, 3000),
                    budget_goal=random.choice([500, 600, 800, 1000]),
                )
                db.add(u)
            users.append(u)
        db.commit()
        for u in users:
            db.refresh(u)

        # 2. 攻略文章
        if db.query(Article).count() == 0:
            for title, cat, paras in article_data:
                content = "\n\n".join(paras)
                db.add(Article(
                    title=title, category=cat, content=content,
                    author=random.choice(["抠门达人", "省钱小王", "会过日子的莉莉", "理性消费君"]),
                    likes=random.randint(0, 500), views=random.randint(100, 5000),
                ))
            db.commit()
            print(f"文章: 写入 {len(article_data)} 篇")

        # 3. 社区帖子
        if db.query(Post).count() == 0:
            for title, content, tags in post_data:
                db.add(Post(
                    user_id=random.choice(users).id, title=title, content=content,
                    tags=tags, status="approved",
                    likes=random.randint(0, 120), comments_count=random.randint(0, 30),
                ))
            db.commit()
            print(f"帖子: 写入 {len(post_data)} 条")

        # 4. 评论（随机挂到文章和帖子上）
        if db.query(Comment).count() == 0:
            articles = db.query(Article.id).all()
            posts = db.query(Post.id).all()
            targets = [("article", a[0]) for a in articles] + [("post", p[0]) for p in posts]
            for _ in range(50):
                tt, tid = random.choice(targets)
                db.add(Comment(
                    user_id=random.choice(users).id,
                    target_type=tt, target_id=tid,
                    content=random.choice(comment_data),
                ))
            db.commit()
            print(f"评论: 写入 50 条")

        # 5. 羊毛活动
        if db.query(CouponActivity).count() == 0:
            now = datetime.datetime.now()
            for title, content, platform in coupon_data:
                db.add(CouponActivity(
                    title=title, content=content, platform=platform,
                    deadline=now + datetime.timedelta(days=random.randint(5, 60)),
                    verified=random.choice([0, 1]),
                ))
            db.commit()
            print(f"羊毛活动: 写入 {len(coupon_data)} 条")

        # 6. 价格历史
        if db.query(PriceHistory).count() == 0:
            now = datetime.datetime.now()
            for name, price, platform in price_hist:
                db.add(PriceHistory(product_name=name, price=price, platform=platform,
                                    recorded_at=now - datetime.timedelta(days=random.randint(1, 60))))
            db.commit()
            print(f"价格历史: 写入 {len(price_hist)} 条")

        # 7. 测试用户账单：锚定「本月」往前 4 个月，环比和趋势才有数据可比。
        #    以前写死 datetime.date(2026, 9, day)，时间一走到 10 月，
        #    账单页默认视图和「分析我这个月账单」就全是空的。
        #    条目直接复用账单接口里那份 _DEMO_ITEMS，两处各写一套迟早会对不上。
        if db.query(Bill).count() == 0:
            from app.api.routes.bills import _DEMO_ITEMS, _make_order_no
            today = datetime.date.today()
            months = []
            y, mo = today.year, today.month
            for _ in range(4):
                months.append((y, mo))
                mo -= 1
                if mo < 1:
                    mo = 12
                    y -= 1
            months.reverse()
            n = 0
            for u in users:
                for (yy, mm) in months:
                    last = calendar.monthrange(yy, mm)[1]
                    if (yy, mm) == (today.year, today.month):
                        last = min(last, today.day)     # 别生成未来的消费
                    if last < 1:
                        continue
                    for _ in range(random.randint(8, 12)):
                        label, cat, (lo, hi), chans = random.choice(_DEMO_ITEMS)
                        d = datetime.date(yy, mm, random.randint(1, last))
                        ch = random.choice(chans)
                        db.add(Bill(
                            user_id=u.id, amount=round(random.uniform(lo, hi), 2),
                            category=cat, source=label, pay_channel=ch,
                            order_no=_make_order_no(ch, d) if random.random() < 0.6 else "",
                            bill_date=d,
                        ))
                        n += 1
            db.commit()
            print(f"账单: 写入 {n} 条（覆盖 {months[0][0]}-{months[0][1]:02d} 起 4 个月）")

        print("\n✅ Mock 数据写入完成！")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
