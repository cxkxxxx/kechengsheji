// 投稿攻略：分类 + 标题 + 正文 + 封面/配图（最多 4 张），提交后进待审核队列
const { request } = require('../../utils/request')
const { pickAndUpload } = require('../../utils/upload')
const { fullUrl } = require('../../utils/util')

const MAX_IMAGES = 4          // 与后端 ARTICLE_MAX_IMAGES 一致
const CATS = ['餐饮', '购物', '生活', '羊毛', '交通', '综合']

Page({
  data: {
    title: '', content: '', category: '综合',
    cats: CATS,
    images: [], shown: [],
    maxImages: MAX_IMAGES,
    uploading: false,
    submitting: false,
    mine: [],
    // AI 创作助手
    aiOpen: false,
    aiModes: [
      { k: 'generate', name: '生成全文' },
      { k: 'title', name: '只出标题' },
      { k: 'polish', name: '润色' },
      { k: 'reorganize', name: '重新组织' },
    ],
    aiMode: 'generate',
    aiForm: { topic: '', experience: '', scene_desc: '' },
    aiBusy: false,
    aiResult: null,
    aiHistory: [],
    // 本稿对应的 AI 创作记录 id：提交时带给后端回填 article_id。
    // 已经关联过攻略的历史草稿不再传（重复提交会覆盖原来的关联）
    aiCreationId: 0,
  },

  onLoad() { this.loadMine() },

  // 我投过的：状态一目了然，不然用户提交完就再也找不着了
  async loadMine() {
    try {
      const data = await request('/articles/mine', 'GET', {}, true) || {}
      // WXML 里调不了函数，状态文案在这里算好
      const STATUS = { pending: ['审核中', 'chip-warn'], approved: ['已发布', 'chip-ok'], rejected: ['未通过', 'chip-danger'] }
      this.setData({
        mine: (data.items || []).map(r => {
          const s = STATUS[r.status] || [r.status || '', 'chip-grey']
          return Object.assign({}, r, { statusText: s[0], statusCls: s[1] })
        }),
      })
    } catch (e) { console.error(e) }
  },

  onTitle(e) { this.setData({ title: e.detail.value }) },
  onContent(e) { this.setData({ content: e.detail.value }) },
  pickCat(e) { this.setData({ category: CATS[e.currentTarget.dataset.i] }) },

  // ---------- AI 创作助手 ----------
  // 后端 /ai/create-assist 返回结构化草稿，这里只负责展示和回填；
  // 草稿必须经过「用这版填入 → 用户再手动提交」两步，AI 永远不会自己发布。
  openAI() { this.setData({ aiOpen: true }); this.loadAIHistory() },
  closeAI() { this.setData({ aiOpen: false }) },

  loadAIHistory() {
    request('/ai/creations?scene=article', 'GET').then(d => {
      // 区分未发布草稿和已发布攻略，WXML 直接用 publishedText 展示
      this.setData({ aiHistory: (d.items || []).slice(0, 10).map(it => {
        const pub = it.article_id > 0
        return Object.assign({}, it, {
          published: pub,
          publishedText: pub ? '已发布攻略' : '未发布草稿',
        })
      }) })
    }).catch(e => console.error(e))
  },

  restoreHistory(e) {
    const it = this.data.aiHistory[e.currentTarget.dataset.i]
    if (!it || !it.result) return
    // 已发布的记录再拿出来改、再投稿算新的攻略，不再挂回原创作记录
    this.setData({ aiOpen: true, aiResult: it.result, aiCreationId: it.article_id > 0 ? 0 : it.id })
  },

  // 历史条目点击：已发布的跳攻略详情，草稿调回弹窗继续改
  tapHistoryItem(e) {
    const it = this.data.aiHistory[e.currentTarget.dataset.i]
    if (!it) return
    if (it.published && it.article_id) {
      // 攻略还在待审核时详情接口不出内容，页面会提示文章不存在，
      // 真实状态以「我的投稿」列表为准
      wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + it.article_id })
      return
    }
    this.restoreHistory(e)
  },

  pickAIMode(e) { this.setData({ aiMode: e.currentTarget.dataset.k, aiResult: null }) },

  onAIInput(e) {
    this.setData({ ['aiForm.' + e.currentTarget.dataset.field]: e.detail.value })
  },

  async runAI() {
    if (this.data.aiBusy) return
    const mode = this.data.aiMode
    const f = this.data.aiForm
    if (mode === 'generate' && !f.topic.trim()) {
      wx.showToast({ title: '先填主题', icon: 'none' }); return
    }
    if (mode !== 'generate' && this.data.content.trim().length < 10) {
      wx.showToast({ title: '先在正文里写点内容，AI 才有原料', icon: 'none' }); return
    }
    this.setData({ aiBusy: true })
    try {
      const d = await request('/ai/create-assist', 'POST', {
        scene: 'article', mode,
        topic: f.topic, experience: f.experience, scene_desc: f.scene_desc,
        title: this.data.title, content: this.data.content,
      })
      this.setData({ aiResult: d.result, aiCreationId: d.id || 0, aiBusy: false })
      this.loadAIHistory()
    } catch (e) {
      this.setData({ aiBusy: false })
    }
  },

  // 把 AI 草稿填进表单。步骤/注意事项拼进正文，分类只在候选里才回填
  applyResult() {
    const r = this.data.aiResult
    if (!r) return
    let content = r.content || ''
    if (r.steps && r.steps.length) {
      content += '\n\n【操作步骤】\n' + r.steps.map((s, i) => (i + 1) + '. ' + s).join('\n')
    }
    if (r.notes && r.notes.length) {
      content += '\n\n【注意事项】\n' + r.notes.map(n => '· ' + n).join('\n')
    }
    const patch = { title: r.title || this.data.title, content, aiOpen: false }
    if (r.category && CATS.indexOf(r.category) >= 0) patch.category = r.category
    this.setData(patch)
    wx.showToast({ title: '已填入草稿，请检查后提交', icon: 'none' })
  },

  async addImages() {
    if (this.data.uploading) return
    const remain = MAX_IMAGES - this.data.images.length
    if (remain <= 0) {
      wx.showToast({ title: '最多 ' + MAX_IMAGES + ' 张（1 封面 + 3 配图）', icon: 'none' })
      return
    }
    this.setData({ uploading: true })
    try {
      const urls = await pickAndUpload(remain)
      if (urls.length) this._setImages(this.data.images.concat(urls))
    } finally {
      this.setData({ uploading: false })
    }
  },

  // 第一张默认当封面，也可以手动指定某张为封面
  setCover(e) {
    const i = e.currentTarget.dataset.i
    const images = this.data.images.slice()
    images.unshift(images.splice(i, 1)[0])
    this._setImages(images)
    wx.showToast({ title: '已设为封面', icon: 'none' })
  },

  _setImages(images) {
    this.setData({ images, shown: images.map(fullUrl) })
  },

  removeImage(e) {
    const images = this.data.images.slice()
    images.splice(e.currentTarget.dataset.i, 1)
    this._setImages(images)
  },

  previewImage(e) {
    const i = e.currentTarget.dataset.i
    wx.previewImage({ current: this.data.shown[i], urls: this.data.shown })
  },

  async submit() {
    const { title, content, category, images } = this.data
    if (!title.trim()) { wx.showToast({ title: '写个标题吧', icon: 'none' }); return }
    if (content.trim().length < 10) { wx.showToast({ title: '正文至少写 10 个字', icon: 'none' }); return }
    if (this.data.uploading) { wx.showToast({ title: '图片还在上传', icon: 'none' }); return }
    this.setData({ submitting: true })
    try {
      await request('/articles', 'POST', {
        title, content, category,
        cover: images[0] || '',
        images,
        creation_id: this.data.aiCreationId || undefined,
      })
      wx.showModal({
        title: '提交成功', showCancel: false, confirmText: '知道了',
        content: '攻略已进入待审核队列，管理员通过后会出现在攻略列表里。',
        success: () => {
          this.setData({ title: '', content: '', images: [], shown: [], submitting: false, aiCreationId: 0 })
          this.loadMine()
        },
      })
    } catch (e) {
      this.setData({ submitting: false })
    }
  },

  goDetail(e) {
    const id = e.currentTarget.dataset.id
    if (e.currentTarget.dataset.status !== 'approved') {
      wx.showToast({ title: '这篇还没通过审核，暂不可见', icon: 'none' })
      return
    }
    wx.navigateTo({ url: '/pages/articleDetail/articleDetail?id=' + id })
  },
})
