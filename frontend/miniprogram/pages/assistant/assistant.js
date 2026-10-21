// AI助手页逻辑：与省钱Agent对话（流式 + 图片上传 + 多智能体）
const { request } = require('../../utils/request')

// 卡片数据（后端下发 / 历史回显）→ 渲染用的形状，两处共用一份
function toCards(items) {
  return (items || []).map((x, i) => ({
    key: (x.kind || 'link') + '-' + i,
    label: x.label || x.platform || '查看商品',
    platform: x.platform || '',
    url: x.url || '',
    priceText: (x.price || x.price === 0) ? ('¥' + x.price) : ''
  })).filter(x => x.url)
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

const QUICK = {
  coupon: ['小米15 手机哪个平台便宜？', '最近有什么优惠活动？',
           '冰箱有土豆青椒鸡蛋，怎么做最省？', '超市几点去打折最划算？'],
  budget: ['分析一下我这月账单', '我的省钱目标达成了吗？',
           '昨晚外卖 18 块，帮我记上', '话费什么时候充最划算？']
}
const PLACEHOLDER = {
  coupon: '比到手价、问优惠活动，或报食材让我出省钱菜谱…',
  budget: '说消费让我记账、问本月账单，或问怎么省…'
}
// 只发图不打字时替用户补的那句指令。必须按专家分开，否则「看图片」这种含糊说法
// 会让模型照着图片复述一遍，而不是去记账/比价。
const IMAGE_ASK = {
  budget: '把这张支付截图/小票里的消费记入账本，逐笔列出金额、分类和日期后写入，不要只描述图片内容。',
  coupon: '识别这张图里的商品名称、品牌和型号，复制成可搜索的商品标题发给我，然后帮我比价。'
}
// 能力入口条（专家切换下面那一行）。每个 chip 都对应后端一个真实注册的工具，
// 点一下就是把对应的问法发出去——不挂只做样子的空按钮。
// 图标一律用 app.wxss 里已有的 ic-* 类，写错类名会渲染成空白方块。
const CAPS = {
  coupon: [
    { ic: 'ic-search',  name: '比价',     q: '小米15 手机哪个平台便宜？' },
    { ic: 'ic-gift',    name: '优惠活动', q: '最近有什么优惠活动？' },
    { ic: 'ic-doc',     name: '省钱菜谱', q: '冰箱有土豆青椒鸡蛋，怎么做最省？' },
    { ic: 'ic-spark',   name: '省钱攻略', q: '超市几点去打折最划算？' },
    { ic: 'ic-refresh', name: '平替建议', q: '我打车花得有点多，有什么更省的办法？' }
  ],
  budget: [
    { ic: 'ic-camera',  name: '拍照记账', action: 'image' },
    { ic: 'ic-chart',   name: '账单分析', q: '分析一下我这月账单' },
    { ic: 'ic-wallet',  name: '月末预测', q: '照现在这个速度，这个月底会花多少？会不会超支？' },
    { ic: 'ic-clock',   name: '固定扣费', q: '有没有我忘掉的每月固定扣费？' },
    { ic: 'ic-copy',    name: '月度复盘', q: '帮我做个本月省钱复盘' },
    { ic: 'ic-target',  name: '省钱目标', q: '我的省钱目标达成了吗？' }
  ]
}
const DEFAULT_AGENT = 'coupon'

Page({
  data: {
    agents: [
      { key: 'coupon', name: '优惠情报员', emoji: '🧧', tag: '比价 · 优惠 · 菜谱 · 攻略 · 平替' },
      { key: 'budget', name: '理财管家', emoji: '📊', tag: '记账 · 分析 · 预测 · 复盘' }
    ],
    currentAgent: DEFAULT_AGENT,
    placeholder: PLACEHOLDER[DEFAULT_AGENT],
    caps: CAPS[DEFAULT_AGENT],
    messages: [],
    inputValue: '',
    image: null,        // 当前待发送的图片 { url, filename }
    uploading: false,
    sending: false,
    scrollToId: '',
    quickQuestions: QUICK[DEFAULT_AGENT]
  },

  onPullDownRefresh() {
    wx.stopPullDownRefresh()
    wx.showToast({ title: '对话已保持', icon: 'none' })
  },

  onLoad() { this.loadHistory(this.data.currentAgent) },

  // 拉回该智能体的历史对话：小程序重进后界面能接着上次看
  // 记忆本来就存着，只是界面上看不见，会让人觉得「它怎么突然知道我在说什么」
  async loadHistory(agent) {
    const key = agent || this.data.currentAgent
    try {
      const data = await request('/agent/history?agent=' + key + '&limit=40')
      if (this.data.sending || this._skipRestore || key !== this.data.currentAgent) return
      const msgs = ((data && data.messages) || []).map(m => ({
        id: m.id, role: m.role, content: m.content, toolUsed: m.tool_used,
        links: m.role === 'assistant' ? toCards(m.links) : [],
        tables: m.role === 'assistant' ? toTables(m.tables) : []
      }))
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
          that.setData({ messages: [] })
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
    const key = pending.agent && QUICK[pending.agent] ? pending.agent : DEFAULT_AGENT
    this.setData({
      currentAgent: key,
      messages: [],
      quickQuestions: QUICK[key],
      caps: CAPS[key] || CAPS[DEFAULT_AGENT],
      placeholder: PLACEHOLDER[key]
    })
    this.sendMessage(pending.question)
  },

  // 切换智能体（专家）
  switchAgent(e) {
    const key = e.currentTarget.dataset.key
    if (key === this.data.currentAgent) return
    this.setData({
      currentAgent: key,
      messages: [],
      quickQuestions: QUICK[key] || QUICK[DEFAULT_AGENT],
      caps: CAPS[key] || CAPS[DEFAULT_AGENT],
      placeholder: PLACEHOLDER[key] || PLACEHOLDER[DEFAULT_AGENT]
    })
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
    const loadingMsg = { id: loadingId, role: 'assistant', content: '', links: [], tables: [] }
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

    const imageUrls = img ? [img.filename] : []
    // 只发图不打字时，得替用户把话说清楚。以前固定发「请帮我看看这张图片」，
    // 于是拍支付截图给理财管家，它老老实实把截图**描述**了一遍却没入账——
    // 因为没人叫它记账。按当前专家给不同的默认指令。
    const ask = msg || (IMAGE_ASK[this.data.currentAgent] || IMAGE_ASK.coupon)
    try {
      await this.streamChat(ask, imageUrls)
    } catch (err) {
      const msgs = this.data.messages
      msgs[msgs.length - 1] = {
        id: loadingId,
        role: 'assistant',
        content: 'AI助手暂时无法响应：' + (err.message || '未知错误') + '\n请检查后端是否启动'
      }
      this.setData({ messages: msgs })
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
        timeout: 120000,
        success(res) {
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

  // 流式更新最后一条 AI 消息（打字效果）
  updateLoading(text, toolUsed) {
    const msgs = this.data.messages
    const i = msgs.length - 1
    if (!msgs[i] || msgs[i].id !== this._loadingId) return
    msgs[i] = { ...msgs[i], content: (msgs[i].content || '') + text, toolUsed: toolUsed }
    this.setData({ messages: msgs, scrollToId: 'msg-' + this._loadingId })
  },

  // 比价卡片：链接由后端结构化下发，不让模型在正文里复述 URL（会改写或编造）
  attachLinks(items) {
    const cards = toCards(items)
    this._links = cards
    const msgs = this.data.messages
    const last = msgs[msgs.length - 1]
    if (!last || last.id !== this._loadingId) return
    msgs[msgs.length - 1] = { ...last, links: cards }
    this.setData({ messages: msgs })
  },

  // 表格同理：数字对比由后端算好直接渲染，正文只留结论
  attachTables(items) {
    const tables = toTables(items)
    this._tables = tables
    const msgs = this.data.messages
    const last = msgs[msgs.length - 1]
    if (!last || last.id !== this._loadingId) return
    msgs[msgs.length - 1] = { ...last, tables }
    this.setData({ messages: msgs, scrollToId: 'msg-' + this._loadingId })
  },

  // 小程序不能直接打开任意 https 链接，复制到剪贴板让用户去浏览器/对应 App 打开
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

  finishStream() {
    const msgs = this.data.messages
    msgs[msgs.length - 1] = {
      ...msgs[msgs.length - 1],
      content: this._reply || 'AI 暂无回复',
      toolUsed: this._toolUsed
    }
    if (this._toolUsed !== 'chat') {
      msgs[msgs.length - 1].toolUsed = this._toolUsed
    }
    this.setData({ messages: msgs, scrollToId: 'msg-' + this._loadingId })
  },

  // 点击快捷问题
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