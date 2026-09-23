// 帖子详情逻辑
const { request } = require('../../utils/request')
const app = getApp()

Page({
  data: {
    post: {},
    comments: [],
    commentText: '',
    favorited: false,
    liked: false
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
      this.setData({
        post: post || {},
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
