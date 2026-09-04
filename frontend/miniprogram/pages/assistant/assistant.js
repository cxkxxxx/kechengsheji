// AI助手页逻辑：与省钱Agent对话
const { request } = require('../../utils/request')

Page({
  data: {
    messages: [],
    inputValue: '',
    scrollToId: '',
    quickQuestions: [
      '冰箱有西红柿鸡蛋，能做啥？',
      '2000元扫地机器人推荐',
      '帮我分析这组账单',
      '超市什么时候最便宜？'
    ]
  },

  onInput(e) {
    this.setData({ inputValue: e.detail.value })
  },

  // 发送消息
  async sendMessage() {
    const text = this.data.inputValue.trim()
    if (!text) return

    // 添加用户消息到列表
    const userMsg = { id: Date.now(), role: 'user', content: text }
    const loadingMsg = { id: Date.now() + 1, role: 'assistant', content: '正在思考...' }
    this.setData({
      messages: [...this.data.messages, userMsg, loadingMsg],
      inputValue: '',
      scrollToId: 'msg-' + (Date.now() + 1)
    })

    try {
      // 调用后端 Agent 接口
      const data = await request('/agent/chat', 'POST', { message: text })
      // 替换加载消息为真实回复
      const msgs = this.data.messages
      msgs[msgs.length - 1] = {
        id: Date.now() + 1,
        role: 'assistant',
        content: data.reply,
        toolUsed: data.tool_used
      }
      this.setData({ messages: msgs })
    } catch (e) {
      const msgs = this.data.messages
      msgs[msgs.length - 1] = { id: Date.now() + 1, role: 'assistant', content: 'AI助手休息中，请稍后再试' }
      this.setData({ messages: msgs })
    }
  },

  // 点击快捷问题
  askQuick(e) {
    this.setData({ inputValue: e.currentTarget.dataset.q })
    this.sendMessage()
  }
})
