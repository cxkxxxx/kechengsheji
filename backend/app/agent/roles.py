"""智能体身份表：只有两个专家。

抠门达人下线后，库里 agent='default'（以及加 agent 列之前的 NULL）那批历史不能变成孤儿，
统一归到优惠情报员名下，用户原来聊过的东西还在。
"""
DEFAULT_AGENT = "coupon"
AGENT_KEYS = ("coupon", "budget")


def normalize(name: str) -> str:
    return name if name in AGENT_KEYS else DEFAULT_AGENT
