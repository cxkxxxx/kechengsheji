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
      })
      wx.showModal({
        title: '提交成功', showCancel: false, confirmText: '知道了',
        content: '攻略已进入待审核队列，管理员通过后会出现在攻略列表里。',
        success: () => {
          this.setData({ title: '', content: '', images: [], shown: [], submitting: false })
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
