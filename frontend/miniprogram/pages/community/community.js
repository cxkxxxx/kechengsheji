// 社区页逻辑
const { request } = require('../../utils/request')

Page({
  data: { posts: [] },

  onLoad() { this.loadPosts() },

  async loadPosts() {
    try {
      const data = await request('/posts')
      this.setData({ posts: data || [] })
    } catch (e) { console.error(e) }
  },

  goPostDetail(e) {
    wx.navigateTo({ url: '/pages/postDetail/postDetail?id=' + e.currentTarget.dataset.id })
  },

  goCreatePost() {
    wx.navigateTo({ url: '/pages/postCreate/postCreate' })
  }
})
