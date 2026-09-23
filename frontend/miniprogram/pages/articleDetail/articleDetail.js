// 文章详情逻辑
const { request } = require('../../utils/request')
const app = getApp()

Page({
  data: {
    article: {},
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
