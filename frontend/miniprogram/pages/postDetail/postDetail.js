// 帖子详情逻辑
const { request } = require('../../utils/request')
const { imageGrid } = require('../../utils/util')
const app = getApp()

Page({
  data: {
    post: {},
    gridCls: 'imgs',
    gridList: [],
    comments: [],
    commentText: '',
    favorited: false,
    liked: false,
    showSaveDialog: false,
    saveForm: { amount: '', note: '' }
  },

  onLoad(options) {
    this.postId = options.id
    this.loadData()
  },

  async loadData() {
    try {
      const [post, comments] = await Promise.all([
        request('/posts/' + this.postId),
        request('/comments?target_type=post&target_id=' + this.postId)
      ])
      const grid = imageGrid((post && post.images) || [], 9)
      this.setData({
        post: post || {},
        gridCls: grid.cls,
        gridList: grid.list,
        comments: comments || []
      })
      if (app.globalData.token) {
        try {
          const fav = await request('/favorites/check?target_type=post&target_id=' + this.postId)
          this.setData({ favorited: fav.favorited })
        } catch (e) {}
      }
    } catch (e) { console.error(e) }
  },

  previewImage(e) {
    const i = e.currentTarget.dataset.i
    wx.previewImage({ current: this.data.gridList[i], urls: this.data.gridList })
  },

  // 问AI：把帖子内容带过去，让「优惠情报员」把它变成可执行步骤
  askAI() {
    const content = String(this.data.post.content || '')
    app.globalData.pendingAsk = {
      agent: 'coupon',
      question: '我在看社区帖子《' + this.data.post.title + '》，内容大意：'
        + content.slice(0, 120)
        + '。帮我把它变成可执行的步骤和购物清单，按我的情况调整方案。'
    }
    wx.switchTab({ url: '/pages/assistant/assistant' })
  },

  openSaveDialog() {
    this.setData({ showSaveDialog: true, saveForm: { amount: '', note: '' } })
  },

  closeSaveDialog() {
    this.setData({ showSaveDialog: false })
  },

  onSaveInput(e) {
    const field = e.currentTarget.dataset.field
    this.setData({ ['saveForm.' + field]: e.detail.value })
  },

  // 记省钱：来源是这条帖子，走后端 /checkin/do，source=社区经验 用来追溯
  async submitSave() {
    const amount = parseFloat(this.data.saveForm.amount)
    if (!amount || amount <= 0) {
      wx.showToast({ title: '请填写实际省下的金额', icon: 'none' })
      return
    }
    try {
      await request('/checkin/do', 'POST', {
        saved_amount: Math.round(amount * 100) / 100,
        note: this.data.saveForm.note || '',
        source: '社区经验',
        ref_type: 'post',
        ref_id: parseInt(this.postId)
      })
      this.setData({ showSaveDialog: false })
      wx.showToast({ title: '已记入省钱成果', icon: 'none' })
    } catch (e) { console.error(e) }
  },

  async likePost() {
    try {
      const res = await request('/posts/' + this.postId + '/like', 'POST')
      this.setData({
        liked: res.liked,
        'post.likes': res.likes
      })
    } catch (e) { console.error(e) }
  },

  async toggleFavorite() {
    try {
      const res = await request('/favorites/toggle?target_type=post&target_id=' + this.postId, 'POST')
      this.setData({ favorited: res.favorited })
      wx.showToast({ title: res.favorited ? '已收藏' : '已取消', icon: 'none' })
    } catch (e) { console.error(e) }
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
        target_type: 'post',
        target_id: parseInt(this.postId),
        content: this.data.commentText,
        parent_id: 0
      })
      const comments = [comment, ...this.data.comments]
      this.setData({
        comments,
        commentText: '',
        'post.comments_count': (this.data.post.comments_count || 0) + 1
      })
      wx.showToast({ title: '评论成功', icon: 'none' })
    } catch (e) { console.error(e) }
  }
})
