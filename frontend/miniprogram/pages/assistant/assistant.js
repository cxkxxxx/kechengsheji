// AI助手页逻辑：与省钱Agent对话（流式 + 图片上传 + 多智能体）
// 版面按参考图还原：标题 → AI 欢迎卡 → 模式切换 → 常用功能 → 你可以这样问 → 对话 → 输入条
const { request } = require('../../utils/request')
const md = require('../../utils/markdown')

// 卡片数据（后端下发 / 历史回显）→ 渲染用的形状，两处共用一份
function toCards(items) {
  // 后端已按到手价升序下发。「当前最低」只标给实时查到的第一家：
  // 站内记录是过去的旧价，拿它宣布「最低」等于拿过期数据替用户做决定。
  let liveMarked = false
  return (items || []).map((x, i) => {
    const live = x.source === '实时查询'
    const isLowest = live && !liveMarked
    if (isLowest) liveMarked = true
    return {
      key: (x.kind || 'link') + '-' + i,
      label: x.label || x.platform || '查看商品',
      platform: x.platform || '',
      url: x.url || '',
      priceNum: (x.price || x.price === 0) ? x.price : null,
      priceText: (x.price || x.price === 0) ? ('¥' + x.price) : '',
      product: x.product || '',
      desc: x.desc || '',
      cutText: x.cut > 0 ? '已省 ¥' + x.cut : '',
      live,
      sourceText: live ? '实时查询' : ('站内记录' + (x.recorded_at ? ' ' + x.recorded_at : '')),
      recordedAt: x.recorded_at || '',
      isLowest
    }
  }).filter(x => x.url)
}

// 比价总结条：只用实时查到的报价算结论，站内旧价不参与「最低」判断。
// 实时价不足一家时不给总结（宁缺毋假）。
function priceSummaryOf(cards) {
  const live = cards.filter(c => c.live && c.priceNum !== null)
  if (!live.length) return null
  const lowest = live[0]
  const sum = {
    product: lowest.product || lowest.desc || '',
    lowest: lowest.priceNum,
    lowestPlatform: lowest.platform || '',
    spreadText: '',
    sourceText: '来源：' + (lowest.platform || '比价服务') + ' · 实时查询'
  }
  if (live.length > 1) {
    const second = live[1]
    const diff = Math.round((second.priceNum - lowest.priceNum) * 100) / 100
    if (diff > 0) {
      // 价差对象精确到店铺：同平台不同店也说清是哪家
      const other = second.label && second.label !== second.platform ? second.label : (second.platform || '其他平台')
      sum.spreadText = '比' + other + '低 ¥' + diff
    }
  }
  return sum
}

// 从一组卡片/表格里取商品名，给「生成省钱方案」等后续动作用
function productNameOf(links, tables) {
  const withName = (links || []).filter(x => x.product)
  if (withName.length) return withName[0].product
  const t = (tables || [])[0]
  if (t && t.title && t.title.indexOf('比价：') === 0) return t.title.slice(3)
  return ''
}

// 回复下方的一步动作：聊完能直接点，而不是把结论读完就没了
// 比价结果 → 生成省钱方案；账单分析类工具 → 用户确认后出预算方案
function toActs(role, toolUsed, links, product) {
  if (role !== 'assistant') return []
  const acts = []
  if (links && links.length) {
    acts.push({
      key: 'plan', ic: 'ic-spark', name: product ? '给「' + product + '」出省钱方案' : '生成省钱方案',
      q: (product ? '我想买「' + product + '」' : '针对刚比的这个商品') +
         '，帮我出一份省钱购买方案：什么时机买最划算、怎么用券和满减、哪些配置不值得加钱。'
    })
  }
  const t = toolUsed || ''
  const isAnalysis = /detect_fixed_spend|analyze_bills|monthly_report|spending_forecast/.test(t)
  if (isAnalysis) {
    acts.push({
      key: 'budget', ic: 'ic-target', name: '按这个分析出预算方案',
      q: '好，就按你上面的分析，帮我定一份具体的预算方案：每个分类大概能花多少、重点砍哪几项、每天控制在多少。先列出来我确认。'
    })
    // 闭环最后一环：照 AI 方案做了之后，实际省的钱要记进省钱成果（账单页可见）
    acts.push({ key: 'save', ic: 'ic-check', name: '记一笔今天的省钱', action: 'save' })
  }
  return acts
}

// 表格数据（后端下发 / 历史回显）→ 渲染形状，两处共用一份
function toTables(items) {
  return (items || [])
    .filter(t => t && Array.isArray(t.head) && Array.isArray(t.rows) && t.rows.length)
    .map((t, i) => ({
      key: 'tbl-' + i,
      title: t.title || '',
      head: t.head,
      rows: t.rows,
      note: t.note || '',
      // 列数决定单元格宽度分配，4 列以上首列要收窄
      cls: 'tbl-' + t.head.length
    }))
}

// AI 正文统一过一遍 Markdown 解析：页面上只留排版结果，不出现 ### / ** 源标记。
// streaming=true 时按「还没写完」处理残缺标记。
function withMd(msg, streaming) {
  return Object.assign({}, msg, { md: md.parse(msg.content || '', !!streaming) })
}

// 能力入口条（专家切换下面那一行）。每个 chip 都对应后端一个真实注册的工具，
// 点一下就是把对应的问法发出去——不挂只做样子的空按钮。
// 图标一律用 app.wxss 里已有的 ic-* 类，写错类名会渲染成空白方块。
const CAPS = {
  coupon: [
    { ic: 'ic-search',  name: '商品比价', q: '小米15 手机哪个平台便宜？' },
    { ic: 'ic-gift',    name: '优惠查询', q: '最近有什么优惠活动？' },
    { ic: 'ic-refresh', name: '平替建议', q: '我打车花得有点多，有什么更省的办法？' },
    { ic: 'ic-doc',     name: '省钱菜谱', q: '冰箱有土豆青椒鸡蛋，怎么做最省？' },
    { ic: 'ic-spark',   name: '省钱攻略', q: '超市几点去打折最划算？' }
  ],
  budget: [
    { ic: 'ic-camera',  name: '拍照记账', action: 'image' },
    { ic: 'ic-chart',   name: '账单分析', q: '分析一下我这月账单' },
    { ic: 'ic-spark',   name: '月度消费解读', q: '帮我解读一下这个月的消费情况：钱主要花在哪、哪几项最容易省' },
    { ic: 'ic-target',  name: '省钱目标', q: '我的省钱目标达成了吗？' },
    { ic: 'ic-wallet',  name: '月末预测', q: '照现在这个速度，这个月底会花多少？会不会超支？' },
    { ic: 'ic-clock',   name: '固定扣费', q: '有没有我忘掉的每月固定扣费？' }
  ]
}
const DEFAULT_AGENT = 'coupon'

// 推荐问题池：「换一批」从这里轮换出 3 条，不能是写死的一组假按钮
const ASK_POOL = {
  coupon: [
    '小米15 手机哪个平台便宜？',
    '最近有什么优惠活动？',
    '冰箱有土豆青椒鸡蛋，怎么做最省？',
    '超市几点去打折最划算？',
    '洗衣液买大桶还是小桶更划算？',
    '买羽绒服怎么找到更低价？',
    '奶茶想少花钱，有什么平替？',
    '一周的菜怎么买最省钱？'
  ],
  budget: [
    '帮我分析这个月的钱花在哪里了。',
    '我怎样调整下个月的预算？',
    '最近哪类支出增加最多？',
    '这个月外卖花了多少，能省下来吗？',
    '照现在的花法，月底会不会超支？',
    '有没有我忘掉的每月固定扣费？',
    '我的省钱目标进展如何？',
    '账单里哪几笔最容易省？'
  ]
}
const ASK_COUNT = 3

// 欢迎卡 + 2×2 功能卡：功能卡对应 caps 里的真实入口（capIndex），
// 点卡片和点常用功能是同一个处理函数，不另挂一套假事件
const WELCOME = {
  coupon: {
    hi: '你好！今天想怎么省钱？',
    role: '我是你的省钱助手',
    desc: '比价、找优惠、做预算，让省钱更有方向。',
    cards: [
      { capIndex: 0, ic: 'ic-search',  name: '商品比价', desc: '多平台价格对比' },
      { capIndex: 1, ic: 'ic-gift',    name: '优惠查询', desc: '领取或查询优惠券' },
      { capIndex: 2, ic: 'ic-refresh', name: '平替建议', desc: '找到更优替代品' },
      { capIndex: 3, ic: 'ic-doc',     name: '省钱菜谱', desc: '低成本美食推荐' }
    ]
  },
  budget: {
    hi: '你好！今天想怎么省钱？',
    role: '我是你的省钱助手',
    desc: '记账、做分析、定预算，让花钱更有方向。',
    cards: [
      { capIndex: 0, ic: 'ic-camera', name: '拍照记账', desc: '拍小票截图自动入账' },
      { capIndex: 1, ic: 'ic-chart',  name: '账单分析', desc: '总额、占比、大额' },
      { capIndex: 2, ic: 'ic-spark',  name: '月度消费解读', desc: '本月钱花在哪了' },
      { capIndex: 3, ic: 'ic-target', name: '省钱目标', desc: '进度和达成建议' }
    ]
  }
}

const PLACEHOLDER = {
  coupon: '问比价、问优惠活动，或描述你的需求……',
  budget: '问账单分析、预算规划，或描述你的需求……'
}
// 只发图不打字时替用户补的那句指令。必须按专家分开，否则「看图片」这种含糊说法
// 会让模型照着图片复述一遍，而不是去记账/比价。
const IMAGE_ASK = {
  budget: '把这张支付截图/小票里的消费记入账本，逐笔列出金额、分类和日期后写入，不要只描述图片内容。',
  coupon: '识别这张图里的商品名称、品牌和型号，复制成可搜索的商品标题发给我，然后帮我比价。'
}

// 自定义导航栏的高度：标题要自己画（参考图是左对齐大标题），
// 但右上角胶囊按钮必须避开，所以先量胶囊的位置再算高度和右侧留白
function headerMetrics() {
  let statusBarHeight = 20
  let headHeight = 44
  let headRight = 96
  try {
    const win = (wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync()) || {}
    statusBarHeight = win.statusBarHeight || statusBarHeight
    const cap = wx.getMenuButtonBoundingClientRect ? wx.getMenuButtonBoundingClientRect() : null
    if (cap && cap.height && cap.top >= statusBarHeight) {
      headHeight = (cap.top - statusBarHeight) * 2 + cap.height
      if (win.windowWidth && cap.left) headRight = Math.round(win.windowWidth - cap.left) + 8
    }
  } catch (e) {
    console.error(e)
  }
  return {
    statusBarHeight: statusBarHeight,
    headTotal: statusBarHeight + headHeight,
    headRight: headRight
  }
}

Page({
  data: {
    agents: [
      { key: 'coupon', mode: '购物省钱', icon: 'ic-bag', name: '优惠情报员',
        tag: '比价 · 优惠 · 平替 · 菜谱' },
      { key: 'budget', mode: '记账理财', icon: 'ic-wallet', name: '理财管家',
        tag: '记账 · 分析 · 预测 · 预算' }
    ],
    currentAgent: DEFAULT_AGENT,
    placeholder: PLACEHOLDER[DEFAULT_AGENT],
    caps: CAPS[DEFAULT_AGENT],
    welcomeHi: WELCOME[DEFAULT_AGENT].hi,
    welcomeRole: WELCOME[DEFAULT_AGENT].role,
    welcomeDesc: WELCOME[DEFAULT_AGENT].desc,
    welcomeCards: WELCOME[DEFAULT_AGENT].cards,
    welcomeQuestions: ASK_POOL[DEFAULT_AGENT].slice(0, ASK_COUNT),
    messages: [],
    inputValue: '',
    image: null,        // 当前待发送的图片 { url, filename }
    uploading: false,
    sending: false,
    scrollToId: '',
    statusBarHeight: 20,
    headTotal: 64,
    headRight: 96
  },

  onLoad() {
    this.setData(headerMetrics())
    this._offsets = { coupon: 0, budget: 0 }
    this.loadHistory(this.data.currentAgent)
  },

  onPullDownRefresh() {
    wx.stopPullDownRefresh()
    wx.showToast({ title: '对话已保持', icon: 'none' })
  },

  // 拉回该智能体的历史对话：小程序重进后界面能接着上次看
  // 记忆本来就存着，只是界面上看不见，会让人觉得「它怎么突然知道我在说什么」
  async loadHistory(agent) {
    const key = agent || this.data.currentAgent
    try {
      const data = await request('/agent/history?agent=' + key + '&limit=40')
      if (this.data.sending || this._skipRestore || key !== this.data.currentAgent) return
      const msgs = ((data && data.messages) || []).map(m => {
        const links = m.role === 'assistant' ? toCards(m.links) : []
        const tables = m.role === 'assistant' ? toTables(m.tables) : []
        return withMd({
          id: m.id, role: m.role, content: m.content, toolUsed: m.tool_used, links, tables,
          summary: m.role === 'assistant' ? priceSummaryOf(links) : null,
          status: m.role === 'assistant' && !m.content && !links.length && !tables.length
            ? 'empty' : 'done',
          acts: toActs(m.role, m.tool_used, links, productNameOf(m.links, m.tables))
        }, false)
      })
      this.setData({ messages: msgs, scrollToId: msgs.length ? 'msg-' + msgs[msgs.length - 1].id : '' })
    } catch (e) { console.error(e) }
  },

  // 清空当前智能体的记忆与界面（不影响其它两个专家）
  clearChat() {
    const that = this
    wx.showModal({
      title: '清空对话',
      content: '会同时清掉「' + this._agentName() + '」的上下文记忆，确认？',
      confirmText: '清空', confirmColor: '#FF6B6B',
      success(res) {
        if (!res.confirm) return
        request('/agent/history?agent=' + that.data.currentAgent, 'DELETE').then(() => {
          that._skipRestore = true
          // scrollToId 指向欢迎区顶部：对话很长时滚动条停在底部，
          // 直接清空会出现「界面一片空白、欢迎卡却没显示」
          that.setData({ messages: [], scrollToId: 'home-top' })
          wx.showToast({ title: '已清空', icon: 'success' })
          setTimeout(() => { that._skipRestore = false }, 1000)
        }).catch(err => console.error(err))
      }
    })
  },

  _agentName() {
    const a = this.data.agents.filter(x => x.key === this.data.currentAgent)[0]
    return a ? a.name : 'AI 助手'
  },

  // 从账单页「让 AI 分析」跳过来时，自动切到对应专家并把问题发出去
  onShow() {
    const app = getApp()
    const pending = app && app.globalData && app.globalData.pendingAsk
    if (!pending || !pending.question) return
    app.globalData.pendingAsk = null
    const key = pending.agent && ASK_POOL[pending.agent] ? pending.agent : DEFAULT_AGENT
    this.setData(Object.assign({ messages: [] }, this._modeData(key)))
    this.sendMessage(pending.question)
  },

  // 切换智能体（专家）：模式、功能卡、推荐问题、输入提示一起跟着换
  _modeData(key) {
    const w = WELCOME[key] || WELCOME[DEFAULT_AGENT]
    return {
      currentAgent: key,
      caps: CAPS[key] || CAPS[DEFAULT_AGENT],
      welcomeHi: w.hi,
      welcomeRole: w.role,
      welcomeDesc: w.desc,
      welcomeCards: w.cards,
      welcomeQuestions: this._askList(key),
      placeholder: PLACEHOLDER[key] || PLACEHOLDER[DEFAULT_AGENT]
    }
  },

  // 当前模式下要展示的 3 条推荐问题（带轮换偏移）
  _askList(agent) {
    const pool = ASK_POOL[agent] || ASK_POOL[DEFAULT_AGENT]
    const off = (this._offsets && this._offsets[agent]) || 0
    const out = []
    for (let i = 0; i < ASK_COUNT; i++) out.push(pool[(off + i) % pool.length])
    return out
  },

  // 「换一批」：真的从问题池里换一组，不是把同一组再画一遍
  rotateQuestions() {
    const agent = this.data.currentAgent
    const pool = ASK_POOL[agent] || ASK_POOL[DEFAULT_AGENT]
    this._offsets = this._offsets || {}
    const cur = this._offsets[agent] || 0
    this._offsets[agent] = (cur + ASK_COUNT) % pool.length
    this.setData({ welcomeQuestions: this._askList(agent) })
  },

  // 切换智能体（专家）
  switchAgent(e) {
    const key = e.currentTarget.dataset.key
    if (key === this.data.currentAgent) return
    this.setData(Object.assign({ messages: [], scrollToId: 'home-top' }, this._modeData(key)))
    this.loadHistory(key)
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value })
  },

  // 选择并上传图片
  onChooseImage() {
    const that = this
    wx.chooseMedia({
      count: 1,
      mediaType: ['image'],
      sourceType: ['album', 'camera'],
      success(res) {
        that.uploadImage(res.tempFiles[0].tempFilePath)
      }
    })
  },

  uploadImage(filePath) {
    const app = getApp()
    const that = this
    const baseUrl = (app && app.globalData && app.globalData.baseUrl) || 'http://localhost:8000'
    const token = (app && app.globalData && app.globalData.token) || ''
    this.setData({ uploading: true })
    wx.uploadFile({
      url: baseUrl + '/upload/image',
      filePath: filePath,
      name: 'file',
      header: { 'Authorization': token ? 'Bearer ' + token : '' },
      success(res) {
        let data = {}
        try { data = JSON.parse(res.data) } catch (e) {}
        if (data && data.code === 200 && data.data) {
          that.setData({ image: { url: baseUrl + data.data.url, filename: data.data.filename } })
          wx.showToast({ title: '图片已添加', icon: 'none' })
        } else {
          // 后端大小/格式校验走 HTTPException，文案在 detail 而不是 message
          wx.showToast({ title: (data && (data.detail || data.message)) || '上传失败', icon: 'none' })
        }
      },
      fail() {
        wx.showToast({ title: '上传失败', icon: 'none' })
      },
      complete() {
        that.setData({ uploading: false })
      }
    })
  },

  removeImage() {
    this.setData({ image: null })
  },

  // 发送消息（bindtap 调用时 e 是事件对象，askQuick 传字符串）
  async sendMessage(e) {
    const msg = (typeof e === 'string' ? e : this.data.inputValue || '').trim()
    const img = this.data.image
    if ((!msg && !img) || this.data.sending) return

    this.setData({ sending: true })

    const userMsg = {
      id: Date.now(),
      role: 'user',
      content: msg || '',
      image: img ? img.url : ''
    }
    const loadingId = Date.now() + 1
    const loadingMsg = { id: loadingId, role: 'assistant', content: '', links: [], tables: [], status: 'waiting', md: [] }
    this.setData({
      messages: [...this.data.messages, userMsg, loadingMsg],
      inputValue: '',
      image: null,
      scrollToId: 'msg-' + loadingId
    })
    this._loadingId = loadingId
    this._reply = ''
    this._toolUsed = 'chat'
    this._links = []
    this._tables = []
    this._sseBuf = ''
    this._canceled = false
    this._task = null

    const imageUrls = img ? [img.filename] : []
    // 只发图不打字时，得替用户把话说清楚。以前固定发「请帮我看看这张图片」，
    // 于是拍支付截图给理财管家，它老老实实把截图**描述**了一遍却没入账——
    // 因为没人叫它记账。按当前专家给不同的默认指令。
    const ask = msg || (IMAGE_ASK[this.data.currentAgent] || IMAGE_ASK.coupon)
    // 失败重试要用：重发同一句问法 + 同一张图（图片文件已传到服务端，重试只传文件名）
    this._lastAsk = { ask: ask, imageUrls: imageUrls }
    try {
      await this.streamChat(ask, imageUrls)
    } catch (err) {
      this._failLoading(err)
    } finally {
      this.setData({ sending: false })
    }
  },

  // 发送/停止二合一：生成中按钮变「停止」，点它真取消请求
  onTapSend() {
    if (this.data.sending) return this.cancelSend()
    this.sendMessage()
  },

  // 用户取消生成：中断流，已生成的部分保留并如实标注
  cancelSend() {
    if (!this.data.sending) return
    this._canceled = true
    try { if (this._task) this._task.abort() } catch (e) {}
    wx.showToast({ title: '已停止生成', icon: 'none' })
  },

  // 流式失败/断线：把占位消息定格成「失败可重试」状态，错误原因原样亮出来。
  // 用户主动取消的走 canceled 状态，不算失败，也不给重试按钮。
  _failLoading(err) {
    const msgs = this.data.messages
    const i = msgs.length - 1
    if (!msgs[i] || msgs[i].id !== this._loadingId) return
    const canceled = this._canceled
    const next = withMd({
      ...msgs[i],
      content: canceled
        ? (this._reply || '')
        : 'AI助手暂时无法响应：' + (err.message || '未知错误') + '\n请检查后端是否启动',
      toolUsed: canceled ? msgs[i].toolUsed : 'error',
      status: canceled ? 'canceled' : 'error'
    }, false)
    msgs[i] = next
    this.setData({ messages: msgs })
  },

  // 失败重试：把最后一条错误消息换回等待态，原样重发上一次的问法
  async retryLast() {
    if (this.data.sending || !this._lastAsk) return
    const msgs = this.data.messages
    const last = msgs[msgs.length - 1]
    if (!last || last.status !== 'error') return
    const loadingId = Date.now()
    msgs[msgs.length - 1] = {
      id: loadingId, role: 'assistant', content: '', links: [], tables: [], status: 'waiting', md: []
    }
    this.setData({ messages: msgs, sending: true, scrollToId: 'msg-' + loadingId })
    this._loadingId = loadingId
    this._reply = ''
    this._toolUsed = 'chat'
    this._links = []
    this._tables = []
    this._sseBuf = ''
    this._canceled = false
    this._task = null
    try {
      await this.streamChat(this._lastAsk.ask, this._lastAsk.imageUrls)
    } catch (err) {
      this._failLoading(err)
    } finally {
      this.setData({ sending: false })
    }
  },

  // 流式对话：enableChunked 逐片接收 SSE
  // 关键兜底：无论是否解析到 SSE 的 done 事件，请求结束（success 或 complete）都会强制收尾并 resolve，
  // 绝不让 promise 悬挂导致「一直思考」。
  streamChat(message, imageUrls) {
    return new Promise((resolve, reject) => {
      let settled = false // 是否已结束（resolve/reject 二选一，只执行一次）
      let gotChunk = false // 是否真的收到过分块（决定 success 里要不要整包兜底解析）
      const app = getApp()
      const baseUrl = (app && app.globalData && app.globalData.baseUrl) || 'http://localhost:8000'
      const token = (app && app.globalData && app.globalData.token) || ''
      const that = this

      // ArrayBuffer → UTF-8 字符串
      function ab2str(buf) {
        if (typeof buf === 'string') return buf
        if (typeof buf === 'undefined' || buf === null) return ''
        if (typeof TextDecoder !== 'undefined') {
          try { return new TextDecoder('utf-8').decode(buf) } catch (e) {}
        }
        const bytes = new Uint8Array(buf)
        let out = ''
        const CHUNK = 0x8000
        for (let i = 0; i < bytes.length; i += CHUNK) {
          out += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK))
        }
        try { return decodeURIComponent(escape(out)) } catch (e) { return out }
      }

      // 处理解析出来的一条 SSE 事件
      function handlePayload(payload) {
        let evt
        try { evt = JSON.parse(payload) } catch (e) { return }
        if (evt.type === 'chunk') {
          that._reply += evt.text
          that.updateLoading(evt.text, that._toolUsed)
        } else if (evt.type === 'meta') {
          that._toolUsed = evt.tool_used
        } else if (evt.type === 'links') {
          that.attachLinks(evt.items || [])
        } else if (evt.type === 'tables') {
          that.attachTables(evt.items || [])
        } else if (evt.type === 'done') {
          if (settled) return
          settled = true
          that.finishStream()
          resolve({ reply: that._reply, tool_used: that._toolUsed })
        }
      }

      // 把缓冲区里可解析的完整 SSE 块消费掉
      function flushBuffer() {
        let idx
        while ((idx = that._sseBuf.indexOf('\n\n')) >= 0) {
          const block = that._sseBuf.slice(0, idx)
          that._sseBuf = that._sseBuf.slice(idx + 2)
          const line = block.split('\n').find(l => l.indexOf('data:') === 0)
          if (!line) continue
          const payload = line.slice(5).trim()
          if (!payload || payload === '[DONE]') continue
          handlePayload(payload)
        }
      }

      // 收尾：即使没收到 done 事件，也强制把当前回复定格并 resolve
      function finish() {
        if (settled) return
        settled = true
        flushBuffer()
        that.finishStream()
        resolve({ reply: that._reply, tool_used: that._toolUsed })
      }

      const task = wx.request({
        url: baseUrl + '/agent/chat',
        method: 'POST',
        data: { message: message, image_urls: imageUrls || [], agent: that.data.currentAgent },
        header: {
          'Content-Type': 'application/json',
          'Authorization': token ? 'Bearer ' + token : ''
        },
        enableChunked: true,
        responseType: 'arraybuffer',
        timeout: 120000,        success(res) {
          if (res && res.statusCode && res.statusCode !== 200) {
            let msg = '请求失败(' + res.statusCode + ')'
            try {
              let raw = typeof res.data === 'string' ? res.data : (res.data ? ab2str(res.data) : '')
              const d = JSON.parse(raw) || {}
              if (d.detail) msg = d.detail
              else if (d.message) msg = d.message
            } catch (e) {}
            if (res.statusCode === 401) {
              msg = '登录已失效，请重新登录'
              if (app && app.globalData) { app.globalData.token = ''; app.globalData.userInfo = null }
              wx.removeStorageSync('token')
              wx.removeStorageSync('userInfo')
              wx.redirectTo({ url: '/pages/login/login' })
            }
            if (!settled) { settled = true; reject(new Error(msg)) }
            return
          }
          // 兜底：基础库不支持分块回调时，整包体就是一次性返回的，补进缓冲区再解析
          if (!gotChunk && res && res.data) {
            that._sseBuf += ab2str(res.data)
          }
          // 200：流式响应已结束，强制收尾（覆盖 done 事件未解析到的情况）
          finish()
        },
        fail(err) {
          if (!settled) { settled = true; reject(new Error((err && err.errMsg) || '网络错误')) }
        },
        complete() {
          // 线路必然结束标志：万一 success/fail 都没触发解析，兜底收尾
          finish()
        }
      })

      // 保存任务引用，「停止生成」靠它中断请求
      that._task = task

      // onChunkReceived 只能挂在 wx.request 返回的 RequestTask 上，
      // 写进上面的参数对象不会被调用（这是「一直思考不回答」的根因）
      if (task && typeof task.onChunkReceived === 'function') {
        task.onChunkReceived(function (res) {
          const ab = res && res.data
          if (!ab) return
          gotChunk = true
          that._sseBuf += ab2str(ab)
          flushBuffer()
        })
      }
    })
  },

  // 流式更新最后一条 AI 消息（打字效果）。首块到达即从「等待」转「生成中」
  updateLoading(text, toolUsed) {
    const msgs = this.data.messages
    const i = msgs.length - 1
    if (!msgs[i] || msgs[i].id !== this._loadingId) return
    msgs[i] = withMd({
      ...msgs[i], content: (msgs[i].content || '') + text, toolUsed: toolUsed, status: 'streaming'
    }, true)
    this.setData({ messages: msgs, scrollToId: 'msg-' + this._loadingId })
  },

  // 比价卡片：链接由后端结构化下发，不让模型在正文里复述 URL（会改写或编造）
  attachLinks(items) {
    const cards = toCards(items)
    this._links = cards
    const msgs = this.data.messages
    const last = msgs[msgs.length - 1]
    if (!last || last.id !== this._loadingId) return
    msgs[msgs.length - 1] = {
      ...last, links: cards, summary: priceSummaryOf(cards),
      acts: toActs('assistant', this._toolUsed, cards, productNameOf(cards, this._tables))
    }
    this.setData({ messages: msgs })
  },

  // 表格同理：数字对比由后端算好直接渲染，正文只留结论
  attachTables(items) {
    const tables = toTables(items)
    this._tables = tables
    const msgs = this.data.messages
    const last = msgs[msgs.length - 1]
    if (!last || last.id !== this._loadingId) return
    msgs[msgs.length - 1] = {
      ...last, tables,
      acts: toActs('assistant', this._toolUsed, this._links, productNameOf(this._links, tables))
    }
    this.setData({ messages: msgs, scrollToId: 'msg-' + this._loadingId })
  },

  // 小程序不能直接打开任意 https 链接，「打开商品页」的落点是复制链接，
  // 复制是机制不是卖点，所以按钮上只说「打开」，说明放在弹窗里
  copyLink(e) {
    const url = e.currentTarget.dataset.url
    const label = e.currentTarget.dataset.label || '链接'
    if (!url) return
    wx.setClipboardData({
      data: url,
      success() {
        wx.showModal({
          title: label + ' 链接已复制',
          content: '小程序无法直接打开外部网址。打开手机浏览器或对应 App，粘贴到地址栏/搜索框即可。',
          showCancel: false, confirmText: '知道了'
        })
      },
      fail() { wx.showToast({ title: '复制失败', icon: 'none' }) }
    })
  },

  // 「价格从哪来的」要经得起点：来源 + 更新时间 + 局限，一次说清
  tapSource(e) {
    const d = e.currentTarget.dataset
    const live = d.live
    const when = d.recordedAt
    wx.showModal({
      title: '价格来源',
      content: live
        ? '该价格来自比价服务的实时查询（京东/天猫），是你提问那一刻的快照。下单前请在商品页确认实际价格，价格可能随时变动。'
        : ('该价格来自站内价格记录' + (when ? '，最近更新于 ' + when : '') +
           '。不是实时价，可能已过期，仅供对比参考，下单前请以商品页实际价格为准。'),
      showCancel: false, confirmText: '知道了'
    })
  },

  // 回复下方的动作条：q 直接发出去（生成省钱方案 / 出预算方案）；
  // action=save 走弹窗收金额，POST /checkin/do 记入省钱成果
  askAct(e) {
    const d = e.currentTarget.dataset
    if (d.action === 'save') return this.saveFromAI()
    const q = d.q
    if (!q || this.data.sending) return
    this.sendMessage(q)
  },

  // 「记一笔今天的省钱」：只收用户确认的实际金额，不拿 AI 预测充数
  saveFromAI() {
    const that = this
    wx.showModal({
      title: '记一笔省钱',
      editable: true,
      placeholderText: '实际省了多少元？',
      confirmText: '记下来',
      success(res) {
        if (!res.confirm) return
        const v = parseFloat(res.content)
        if (!(v > 0)) {
          wx.showToast({ title: '请填写大于 0 的金额', icon: 'none' })
          return
        }
        request('/checkin/do', 'POST', {
          saved_amount: Math.round(v * 100) / 100,
          note: '照 AI 方案执行后记的',
          source: 'AI方案'
        }).then(() => {
          wx.showToast({ title: '已记入省钱成果', icon: 'none' })
        }).catch(err => {
          wx.showToast({ title: err.message || '记录失败', icon: 'none' })
        })
      }
    })
  },

  finishStream() {
    const hasBody = !!(this._reply && this._reply.trim())
    const hasData = this._links.length > 0 || this._tables.length > 0
    // 收尾状态：有正文/数据 = 成功；什么都没有 = 无结果；
    // 比价工具跑完却一张卡片都没有 = 数据不完整（AI 结论里不会掺进未核实的价格）
    let status = 'done'
    if (!hasBody && !hasData) {
      status = this._toolUsed === 'price_compare' ? 'partial' : 'empty'
    }
    const msgs = this.data.messages
    msgs[msgs.length - 1] = withMd({
      ...msgs[msgs.length - 1],
      content: hasBody ? this._reply : '',
      toolUsed: this._toolUsed,
      status: status,
      summary: priceSummaryOf(this._links),
      // 工具名是流末尾才定稿的：账单分析类的「出预算方案」入口在这里补挂
      acts: toActs('assistant', this._toolUsed, this._links, productNameOf(this._links, this._tables))
    }, false)
    this.setData({ messages: msgs, scrollToId: 'msg-' + this._loadingId })
  },

  // 点击推荐问题
  askQuick(e) {
    const q = e.currentTarget.dataset.q
    this.setData({ inputValue: q })
    this.sendMessage(q)
  },

  // 能力入口条：普通项直接把问法发出去，「拍照记账」这项走图片选择
  askCap(e) {
    const i = e.currentTarget.dataset.i
    const cap = (this.data.caps || [])[i]
    if (!cap) return
    if (cap.action === 'image') {
      if (this.data.sending) return
      this.onChooseImage()
      return
    }
    if (this.data.sending) {
      wx.showToast({ title: '正在回答中', icon: 'none' })
      return
    }
    this.setData({ inputValue: cap.q })
    this.sendMessage(cap.q)
  }
})
