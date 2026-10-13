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
    liked: false
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
  }
})
