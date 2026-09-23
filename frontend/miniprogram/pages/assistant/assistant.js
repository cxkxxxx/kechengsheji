// AI助手页逻辑：与省钱Agent对话（流式 + 图片上传 + 多智能体）
const QUICK = {
  default: ['冰箱有西红柿鸡蛋，能做啥？', '2000元扫地机器人推荐', '帮我分析这组账单', '超市什么时候最便宜？'],
  coupon: ['最近有什么优惠活动？', '扫地机器人哪个平台便宜？', '现在薅什么羊毛最划算？'],
  budget: ['分析一下我这月账单', '我的省钱目标达成了吗？', '帮我管管这个月预算']
}
const PLACEHOLDER = {
  default: '问我任何省钱问题...',
  coupon: '输入商品/想问的优惠活动...',
  budget: '输入你的消费/预算问题...'
}

Page({
  data: {
    agents: [
      { key: 'default', name: '抠门达人', emoji: '✨', tag: '全科' },
      { key: 'coupon', name: '优惠情报员', emoji: '🧧', tag: '薅羊毛' },
      { key: 'budget', name: '理财管家', emoji: '📊', tag: '管钱' }
    ],
    currentAgent: 'default',
    placeholder: PLACEHOLDER.default,
    messages: [],
    inputValue: '',
    image: null,        // 当前待发送的图片 { url, filename }
    uploading: false,
    sending: false,
    scrollToId: '',
    quickQuestions: QUICK.default
  },

  onPullDownRefresh() {
    wx.stopPullDownRefresh()
    wx.showToast({ title: '对话已保持', icon: 'none' })
  },

  // 从账单页「让 AI 分析」跳过来时，自动切到对应专家并把问题发出去
  onShow() {
    const app = getApp()
    const pending = app && app.globalData && app.globalData.pendingAsk
    if (!pending || !pending.question) return
    app.globalData.pendingAsk = null
    const key = pending.agent && QUICK[pending.agent] ? pending.agent : 'default'
    this.setData({
      currentAgent: key,
      messages: [],
      quickQuestions: QUICK[key],
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
      quickQuestions: QUICK[key] || QUICK.default,
      placeholder: PLACEHOLDER[key] || PLACEHOLDER.default
    })
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
      url: baseUrl + '/agent/upload',
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
          wx.showToast({ title: (data && data.message) || '上传失败', icon: 'none' })
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
    const loadingMsg = { id: loadingId, role: 'assistant', content: '' }
    this.setData({
      messages: [...this.data.messages, userMsg, loadingMsg],
      inputValue: '',
      image: null,
      scrollToId: 'msg-' + loadingId
    })
    this._loadingId = loadingId
    this._reply = ''
    this._toolUsed = 'chat'
    this._sseBuf = ''

    const imageUrls = img ? [img.filename] : []
    try {
      await this.streamChat(msg || '请帮我看看这张图片', imageUrls)
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
  }
})