// 发帖：标题 + 正文 + 标签 + 最多 9 张图
const { request } = require('../../utils/request')
const { pickAndUpload } = require('../../utils/upload')
const { fullUrl } = require('../../utils/util')

const MAX_IMAGES = 9
const MAX_TITLE = 50
const MAX_CONTENT = 2000

Page({
  data: {
    title: '', content: '', tags: '',
    images: [],            // 已上传的 /static/ 相对地址，提交用
    shown: [],             // 绝对地址，渲染用
    maxImages: MAX_IMAGES,
    uploading: false,
    progress: '',
    // AI 创作助手
    aiOpen: false,
    aiModes: [
      { k: 'generate', name: '生成全文' },
      { k: 'polish', name: '润色' },
      { k: 'reorganize', name: '重新组织' },
    ],
    aiMode: 'generate',
    aiForm: { topic: '', experience: '' },
    aiBusy: false,
    aiResult: null,
  },
  back() { wx.navigateBack() },

  onLoad() {
    // 执行计划页「分享经验」带来的草稿：只预填，发布仍由用户自己点
    const app = getApp()
    const p = app && app.globalData && app.globalData.pendingPost
    if (p && (p.title || p.content)) {
      this.setData({ title: p.title || '', content: p.content || '', tags: p.tags || '' })
      app.globalData.pendingPost = null
      wx.showToast({ title: '已带入草稿，可修改后发布', icon: 'none' })
    }
  },

  onTitle(e) { this.setData({ title: e.detail.value }) },
  onContent(e) { this.setData({ content: e.detail.value }) },
  onTags(e) { this.setData({ tags: e.detail.value }) },

  // ---------- AI 创作助手（社区帖版，scene=post）----------
  openAI() { this.setData({ aiOpen: true }) },
  closeAI() { this.setData({ aiOpen: false }) },
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
      wx.showToast({ title: '先写点内容，AI 才有原料', icon: 'none' }); return
    }
    this.setData({ aiBusy: true })
    try {
      const d = await request('/ai/create-assist', 'POST', {
        scene: 'post', mode,
        topic: f.topic, experience: f.experience, scene_desc: '',
        title: this.data.title, content: this.data.content,
      })
      this.setData({ aiResult: d.result, aiBusy: false })
    } catch (e) {
      this.setData({ aiBusy: false })
    }
  },

  applyResult() {
    const r = this.data.aiResult
    if (!r) return
    const patch = { title: r.title || this.data.title, content: r.content || this.data.content, aiOpen: false }
    if (r.tags && r.tags.length && !this.data.tags) patch.tags = r.tags.join(',')
    this.setData(patch)
    wx.showToast({ title: '已填入草稿，检查后再发布', icon: 'none' })
  },

  async addImages() {
    if (this.data.uploading) return
    const remain = MAX_IMAGES - this.data.images.length
    if (remain <= 0) {
      wx.showToast({ title: '最多 ' + MAX_IMAGES + ' 张', icon: 'none' })
      return
    }
    this.setData({ uploading: true })
    try {
      const urls = await pickAndUpload(remain, (done, total) => {
        this.setData({ progress: total > 1 ? '上传中 ' + (done + 1) + '/' + total : '' })
      })
      if (urls.length) this._setImages(this.data.images.concat(urls))
    } finally {
      this.setData({ uploading: false, progress: '' })
    }
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

  async submitPost() {
    const { title, content, tags, images } = this.data
    if (!title.trim() || !content.trim()) {
      wx.showToast({ title: '请填写标题和内容', icon: 'none' })
      return
    }
    if (this.data.uploading) {
      wx.showToast({ title: '图片还在上传，稍等一下', icon: 'none' })
      return
    }
    try {
      await request('/posts', 'POST', {
        title: title.slice(0, MAX_TITLE),
        content: content.slice(0, MAX_CONTENT),
        tags,
        images,
      })
      wx.showToast({ title: '发布成功', icon: 'success' })
      setTimeout(() => wx.navigateBack(), 1200)
    } catch (e) { console.error(e) }
  }
})
