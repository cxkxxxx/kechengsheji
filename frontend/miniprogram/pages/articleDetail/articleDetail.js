// 文章详情逻辑
const { request } = require('../../utils/request')
const app = getApp()

const MAX_GALLERY = 9   // .imgs 九宫格最多 9 张，再多就看不清了

// 后端图片存的是 /static/xxx，小程序的 image 组件不认相对路径，得拼上接口域名
function fullUrl(raw) {
  const s = String(raw || '').trim()
  if (!s) return ''
  if (s.indexOf('http://') === 0 || s.indexOf('https://') === 0) return s
  const baseUrl = (getApp() && getApp().globalData && getApp().globalData.baseUrl)
    || (app && app.globalData && app.globalData.baseUrl) || ''
  return baseUrl + (s.charAt(0) === '/' ? s : '/' + s)
}

// 正文配图：接口对外给数组，这里顺带兼容还没解开的 JSON 字符串和脏数据
function parseImages(raw) {
  let list = raw
  if (typeof list === 'string') {
    try { list = JSON.parse(list) } catch (e) { list = [] }
  }
  if (!Array.isArray(list)) return []
  return list.map(fullUrl).filter(Boolean).slice(0, MAX_GALLERY)
}

Page({
  data: {
    article: {},
    cover: '',
    gallery: [],
    comments: [],
    commentText: '',
    favorited: false,
    liked: false,
    showSaveDialog: false,
    saveForm: { amount: '', note: '' },
    execLoading: false
  },

  onLoad(options) {
    this.articleId = options.id
    this.loadData()
  },

  async loadData() {
    try {
      const [article, comments] = await Promise.all([
        request('/articles/' + this.articleId),
        request('/comments?target_type=article&target_id=' + this.articleId)
      ])
      this.setData({
        article: article || {},
        // 封面与正文配图单独出字段：WXML 里没法拼域名，也没法 JSON.parse
        cover: fullUrl(article && article.cover),
        gallery: parseImages(article && article.images),
        comments: comments || []
      })
      // 检查收藏状态（需登录）
      if (app.globalData.token) {
        try {
          const fav = await request('/favorites/check?target_type=article&target_id=' + this.articleId)
          this.setData({ favorited: fav.favorited })
        } catch (e) {}
      }
    } catch (e) { console.error(e) }
  },

  async likeArticle() {
    try {
      await request('/articles/' + this.articleId + '/like', 'POST')
      const liked = !this.data.liked
      this.setData({
        liked,
        'article.likes': (this.data.article.likes || 0) + (liked ? 1 : 0)
      })
    } catch (e) { console.error(e) }
  },

  async toggleFavorite() {
    try {
      const res = await request('/favorites/toggle?target_type=article&target_id=' + this.articleId, 'POST')
      this.setData({ favorited: res.favorited })
      wx.showToast({ title: res.favorited ? '已收藏' : '已取消', icon: 'none' })
    } catch (e) { console.error(e) }
  },

  // AI 帮我执行：把这条攻略拆成执行计划，生成后跳到计划页勾进度
  async makeExecPlan() {
    if (this.data.execLoading) return
    if (!app.globalData.token) {
      wx.showToast({ title: '先登录再生成执行计划', icon: 'none' })
      return
    }
    this.setData({ execLoading: true })
    try {
      const d = await request('/ai/exec-plan', 'POST', { article_id: parseInt(this.articleId) }, true)
      this.setData({ execLoading: false })
      wx.navigateTo({ url: '/pages/plan/plan?id=' + d.id })
    } catch (e) {
      this.setData({ execLoading: false })
    }
  },

  onCommentInput(e) {
    this.setData({ commentText: e.detail.value })
  },

  async submitComment() {
    if (!this.data.commentText.trim()) {
      wx.showToast({ title: '请输入评论', icon: 'none' })
      return
    }
    try {
      const comment = await request('/comments', 'POST', {
        target_type: 'article',
        target_id: parseInt(this.articleId),
        content: this.data.commentText,
        parent_id: 0
      })
      const comments = [comment, ...this.data.comments]
      this.setData({ comments, commentText: '' })
      wx.showToast({ title: '评论成功', icon: 'none' })
    } catch (e) { console.error(e) }
  },

  // 问 AI：把攻略标题和正文要点带过去，用户不用重新复制粘贴
  askAI() {
    const a = this.data.article || {}
    const brief = (a.content || '').replace(/\s+/g, ' ').slice(0, 120)
    app.globalData.pendingAsk = {
      agent: 'coupon',
      question: '我在看攻略《' + (a.title || '') + '》' + (brief ? '，内容大意：' + brief : '') +
                '。帮我把它变成可执行的步骤和购物清单，按我的情况调整方案。'
    }
    wx.switchTab({ url: '/pages/assistant/assistant' })
  },

  // —— 记一笔实际省钱（写入 checkins，来源=攻略，关联本文） ——
  openSaveDialog() {
    this.setData({
      showSaveDialog: true,
      saveForm: { amount: '', note: '' }
    })
  },

  closeSaveDialog() { this.setData({ showSaveDialog: false }) },

  onSaveInput(e) {
    this.setData({ ['saveForm.' + e.currentTarget.dataset.field]: e.detail.value })
  },

  async submitSave() {
    const value = parseFloat(this.data.saveForm.amount)
    if (!(value > 0)) {
      wx.showToast({ title: '请输入大于 0 的金额', icon: 'none' })
      return
    }
    try {
      await request('/checkin/do', 'POST', {
        saved_amount: Math.round(value * 100) / 100,
        note: this.data.saveForm.note || '',
        source: '攻略', ref_type: 'article', ref_id: parseInt(this.articleId)
      })
      this.setData({ showSaveDialog: false })
      wx.showToast({ title: '已记入省钱成果', icon: 'success' })
    } catch (e) { console.error(e) }
  }
})
